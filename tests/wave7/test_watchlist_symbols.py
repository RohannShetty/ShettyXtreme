"""Tests for watchlist hardening (P1-2.1) and symbol search endpoint (P1-2.3).

Covers:
- Symbol search prefix/substring match, alias resolution, 503 without master
- Watchlist add with suffix normalization, 404 on unresolvable
- Dynamic subscribe/unsubscribe on add/remove
- Futures nearest-monthly resolution
- Watchlist persistence round-trip
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from shettyxtreme.terminal.api import watchlist_router
from shettyxtreme.terminal.api.app import app
from shettyxtreme.terminal.projections import WatchlistProjection


# ── Fakes ─────────────────────────────────────────────────────────────────

class FakeInstrumentMaster:
    """Minimal instrument master backed by an in-memory list of dicts."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def search(
        self,
        internal_symbol: str,
        exchange: str | None = None,
        instrument_type: str | None = None,
        expiry: Any = None,
        strike: float | None = None,
        option_type: str | None = None,
    ) -> list[dict[str, Any]]:
        result = []
        for r in self._rows:
            if r["internal_symbol"] != internal_symbol:
                continue
            if exchange and r["exchange"] != exchange.upper():
                continue
            if instrument_type and r["instrument_type"] != instrument_type.upper():
                continue
            if expiry is not None:
                exp_str = expiry.isoformat() if hasattr(expiry, "isoformat") else str(expiry)
                if r.get("expiry") != exp_str:
                    continue
            if strike is not None and r.get("strike") != float(strike):
                continue
            if option_type and r.get("option_type") != option_type.upper():
                continue
            result.append(r)
        return result

    def search_prefix(
        self,
        query: str,
        exchange: str | None = None,
        instrument_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        q = query.strip().upper()
        result = []
        for r in self._rows:
            if r["instrument_type"] == "UNKNOWN":
                continue
            if exchange and r["exchange"] != exchange.upper():
                continue
            if instrument_type and r["instrument_type"] != instrument_type.upper():
                continue
            sym = r["internal_symbol"].upper()
            if sym.startswith(q) or q in sym:
                result.append(r)
                if len(result) >= limit:
                    break
        return result

    def lookup(self, fyers_symbol: str) -> dict[str, Any] | None:
        for r in self._rows:
            if r["fyers_symbol"] == fyers_symbol:
                return r
        return None

    def get_lot_size(
        self,
        internal_symbol: str,
        exchange: str = "NSE",
        instrument_type: str = "INDEX",
    ) -> int | None:
        rows = self.search(internal_symbol, exchange=exchange, instrument_type=instrument_type)
        if not rows:
            rows = self.search(internal_symbol, exchange=exchange)
        for r in rows:
            lot = r.get("lot_size")
            if lot is not None:
                return int(lot)
        return None


class FakeSymbolResolver:
    """Symbol resolver that validates against the fake master."""

    def __init__(self, master: FakeInstrumentMaster) -> None:
        self.master = master

    def to_fyers(
        self,
        internal_symbol: str,
        exchange: str,
        instrument_type: str,
        expiry: Any = None,
        strike: Any = None,
        option_type: str | None = None,
        series: str = "EQ",
        is_monthly: bool | None = None,
    ) -> str:
        s = str(internal_symbol).strip().upper()
        prefix = "NSE" if exchange in ("NSE", "NSE_FNO", "NFO") else exchange
        if instrument_type == "INDEX":
            ticker_map = {"NIFTY": "NIFTY50-INDEX", "BANKNIFTY": "NIFTYBANK-INDEX", "FINNIFTY": "FINNIFTY-INDEX"}
            ticker_name = ticker_map.get(s, f"{s}-INDEX")
            ticker = f"{prefix}:{ticker_name}"
        elif instrument_type == "EQUITY":
            ticker = f"{prefix}:{s}-EQ"
        elif instrument_type in ("FUTURES", "FUTURE", "FUT"):
            if expiry:
                exp = date.fromisoformat(str(expiry)) if isinstance(expiry, str) else expiry
                ticker = f"{prefix}:{s}{exp.year % 100:02d}{exp.strftime('%b').upper()}FUT"
            else:
                ticker = f"{prefix}:{s}FUT"
        else:
            ticker = f"{prefix}:{s}-EQ"

        # Validate against master
        if self.master.lookup(ticker) is None:
            raise ValueError(f"Symbol not found: {ticker}")
        return ticker


class FakeDataAdapter:
    """Records subscribe/unsubscribe calls for assertion."""

    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []

    async def subscribe_ticks(self, symbols: list[str], callback: Any) -> bool:
        self.subscribed.extend(symbols)
        return True

    async def unsubscribe(self, symbol: str) -> bool:
        self.unsubscribed.append(symbol)
        return True

    async def get_quotes(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        return {}


def _make_master() -> FakeInstrumentMaster:
    """Create a master with test data for NIFTY, BANKNIFTY, RELIANCE."""
    today = date.today()
    # Nearest monthly expiry: last Thursday of current month
    import calendar
    year, month = today.year, today.month
    last_day = calendar.monthrange(year, month)[1]
    nearest_monthly = date(year, month, last_day)
    while nearest_monthly.weekday() != 3:  # Thursday
        nearest_monthly = nearest_monthly.replace(day=nearest_monthly.day - 1)
    # If in the past, use next month
    if nearest_monthly < today:
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        last_day = calendar.monthrange(year, month)[1]
        nearest_monthly = date(year, month, last_day)
        while nearest_monthly.weekday() != 3:
            nearest_monthly = nearest_monthly.replace(day=nearest_monthly.day - 1)

    monthly_str = nearest_monthly.isoformat()
    month_abbr = nearest_monthly.strftime("%b").upper()
    yr = nearest_monthly.year % 100

    return FakeInstrumentMaster(rows=[
        # NIFTY INDEX
        {
            "fyers_symbol": "NSE:NIFTY50-INDEX",
            "internal_symbol": "NIFTY",
            "exchange": "NSE_FNO",
            "instrument_type": "INDEX",
            "expiry": None,
            "strike": None,
            "option_type": None,
            "lot_size": 75,
            "tick_size": 0.05,
            "isin": None,
            "raw_json": "{}",
        },
        # NIFTY FUTURES (monthly)
        {
            "fyers_symbol": f"NSE:NIFTY{yr:02d}{month_abbr}FUT",
            "internal_symbol": "NIFTY",
            "exchange": "NSE_FNO",
            "instrument_type": "FUTURES",
            "expiry": monthly_str,
            "strike": None,
            "option_type": None,
            "lot_size": 75,
            "tick_size": 0.05,
            "isin": None,
            "raw_json": "{}",
        },
        # BANKNIFTY INDEX
        {
            "fyers_symbol": "NSE:NIFTYBANK-INDEX",
            "internal_symbol": "BANKNIFTY",
            "exchange": "NSE_FNO",
            "instrument_type": "INDEX",
            "expiry": None,
            "strike": None,
            "option_type": None,
            "lot_size": 30,
            "tick_size": 0.05,
            "isin": None,
            "raw_json": "{}",
        },
        # RELIANCE EQUITY
        {
            "fyers_symbol": "NSE:RELIANCE-EQ",
            "internal_symbol": "RELIANCE",
            "exchange": "NSE",
            "instrument_type": "EQUITY",
            "expiry": None,
            "strike": None,
            "option_type": None,
            "lot_size": None,
            "tick_size": 0.05,
            "isin": None,
            "raw_json": "{}",
        },
        # NIFTY OPTION (weekly)
        {
            "fyers_symbol": f"NSE:NIFTY{yr:02d}C{nearest_monthly.day:02d}24000CE",
            "internal_symbol": "NIFTY",
            "exchange": "NSE_FNO",
            "instrument_type": "OPTION",
            "expiry": monthly_str,
            "strike": 24000.0,
            "option_type": "CE",
            "lot_size": 75,
            "tick_size": 0.05,
            "isin": None,
            "raw_json": "{}",
        },
    ])


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def reset_state(tmp_path: Path) -> AsyncIterator[None]:
    """Fresh projection + fake master/adapter for every test."""
    master = _make_master()
    resolver = FakeSymbolResolver(master)
    adapter = FakeDataAdapter()

    app.state.watchlist_projection = WatchlistProjection()
    app.state.instrument_master = master
    app.state.symbol_resolver = resolver
    app.state.data_adapter = adapter
    app.state._publish_market_tick = None
    watchlist_router._hydration_cache.clear()

    # Patch the JSON persistence path to use a temp file
    persist_path = tmp_path / "watchlist.json"
    original_path = watchlist_router._WATCHLIST_JSON
    watchlist_router._WATCHLIST_JSON = persist_path

    yield

    watchlist_router._WATCHLIST_JSON = original_path
    watchlist_router._hydration_cache.clear()
    app.state.data_adapter = None
    app.state.instrument_master = None
    app.state.symbol_resolver = None


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Symbol Search Tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_symbol_search_prefix_match(client: AsyncClient) -> None:
    """Search for 'REL' should return RELIANCE."""
    resp = await client.get("/api/symbols/search?q=REL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "REL"
    assert len(data["hits"]) > 0
    assert any(h["internal_symbol"] == "RELIANCE" for h in data["hits"])


@pytest.mark.asyncio
async def test_symbol_search_alias_resolution(client: AsyncClient) -> None:
    """Search for 'BNF' (alias for BANKNIFTY) should return BANKNIFTY rows."""
    resp = await client.get("/api/symbols/search?q=BNF")
    assert resp.status_code == 200
    data = resp.json()
    assert data["canonical"] == "BANKNIFTY"
    assert len(data["hits"]) > 0
    assert any(h["internal_symbol"] == "BANKNIFTY" for h in data["hits"])


@pytest.mark.asyncio
async def test_symbol_search_no_master_503(client: AsyncClient) -> None:
    """When instrument_master is None, search returns 503."""
    app.state.instrument_master = None
    resp = await client.get("/api/symbols/search?q=NIFTY")
    assert resp.status_code == 503
    assert "not available" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_symbol_search_empty_query(client: AsyncClient) -> None:
    """Empty query returns empty hits."""
    resp = await client.get("/api/symbols/search?q=")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hits"] == []


@pytest.mark.asyncio
async def test_symbol_search_nifty_returns_index_and_futures(client: AsyncClient) -> None:
    """NIFTY search should return INDEX and FUTURES rows."""
    resp = await client.get("/api/symbols/search?q=NIFTY")
    assert resp.status_code == 200
    hits = resp.json()["hits"]
    types = {h["instrument_type"] for h in hits}
    assert "INDEX" in types
    assert "FUTURES" in types


# ── Watchlist Hardening Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_watchlist_add_with_suffix_normalization(client: AsyncClient) -> None:
    """Adding 'RELIANCE-EQ' should strip the -EQ suffix and resolve."""
    resp = await client.post("/api/watchlist/RELIANCE-EQ?exchange=NSE")
    assert resp.status_code == 200
    data = resp.json()
    assert data["security_id"] == "RELIANCE"
    assert data["exchange"] == "NSE"


@pytest.mark.asyncio
async def test_watchlist_add_unresolvable_404(client: AsyncClient) -> None:
    """Adding an unknown symbol returns 404, not silent 200."""
    resp = await client.post("/api/watchlist/FAKESYMBOL123?exchange=NSE")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_watchlist_add_plain_symbol(client: AsyncClient) -> None:
    """Adding 'RELIANCE' (plain) should resolve via master."""
    resp = await client.post("/api/watchlist/RELIANCE?exchange=NSE")
    assert resp.status_code == 200
    data = resp.json()
    assert data["security_id"] == "RELIANCE"


@pytest.mark.asyncio
async def test_watchlist_add_index(client: AsyncClient) -> None:
    """Adding 'NIFTY' should resolve as INDEX."""
    resp = await client.post("/api/watchlist/NIFTY?exchange=NSE_FNO")
    assert resp.status_code == 200
    data = resp.json()
    assert data["security_id"] == "NIFTY"


@pytest.mark.asyncio
async def test_watchlist_add_already_fyers_ticker(client: AsyncClient) -> None:
    """Adding 'NSE:RELIANCE-EQ' (already a Fyers ticker) should pass through."""
    resp = await client.post("/api/watchlist/NSE%3ARELIANCE-EQ?exchange=NSE")
    assert resp.status_code == 200
    data = resp.json()
    assert data["security_id"] == "NSE:RELIANCE-EQ"


@pytest.mark.asyncio
async def test_watchlist_dynamic_subscribe_on_add(client: AsyncClient) -> None:
    """After adding a symbol, the data adapter should have subscribed it."""
    adapter = app.state.data_adapter
    assert isinstance(adapter, FakeDataAdapter)

    # Set a fake tick callback so subscribe is triggered
    async def fake_tick(tick: Any) -> None:
        pass
    app.state._publish_market_tick = fake_tick

    resp = await client.post("/api/watchlist/RELIANCE?exchange=NSE")
    assert resp.status_code == 200
    assert "RELIANCE" in adapter.subscribed


@pytest.mark.asyncio
async def test_watchlist_dynamic_unsubscribe_on_remove(client: AsyncClient) -> None:
    """After removing a symbol, the data adapter should have unsubscribed it."""
    adapter = app.state.data_adapter
    assert isinstance(adapter, FakeDataAdapter)

    # Set a fake tick callback so subscribe is triggered
    async def fake_tick(tick: Any) -> None:
        pass
    app.state._publish_market_tick = fake_tick

    # Add first
    await client.post("/api/watchlist/RELIANCE?exchange=NSE")
    assert "RELIANCE" in adapter.subscribed

    # Remove
    resp = await client.delete("/api/watchlist/RELIANCE")
    assert resp.status_code == 204
    assert "RELIANCE" in adapter.unsubscribed


@pytest.mark.asyncio
async def test_watchlist_futures_nearest_monthly(client: AsyncClient) -> None:
    """Adding 'NIFTY-FO' should resolve to the nearest monthly FUT contract."""
    resp = await client.post("/api/watchlist/NIFTY-FO?exchange=NSE_FNO")
    assert resp.status_code == 200
    data = resp.json()
    # security_id should be the Fyers ticker for the nearest monthly FUT
    assert data["security_id"] is not None
    assert "NIFTY" in data["security_id"]
    assert "FUT" in data["security_id"]
    assert data["expiry"] is not None
    assert data["lot_size"] == 75


@pytest.mark.asyncio
async def test_watchlist_persistence_round_trip(client: AsyncClient, tmp_path: Path) -> None:
    """Added symbols should persist to JSON and survive a 'restart'."""
    # Add a symbol
    resp = await client.post("/api/watchlist/RELIANCE?exchange=NSE")
    assert resp.status_code == 200

    # Verify the JSON file was written
    persist_path = watchlist_router._WATCHLIST_JSON
    assert persist_path.exists()
    with open(persist_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "RELIANCE" in data
    assert data["RELIANCE"]["exchange"] == "NSE"
    assert data["RELIANCE"]["security_id"] == "RELIANCE"

    # Simulate restart: load the persisted data
    loaded = watchlist_router._load_persisted_watchlist()
    assert "RELIANCE" in loaded
    assert loaded["RELIANCE"]["security_id"] == "RELIANCE"


@pytest.mark.asyncio
async def test_watchlist_persistence_survives_remove(client: AsyncClient) -> None:
    """Removing a symbol updates the persisted JSON."""
    # Add then remove
    await client.post("/api/watchlist/RELIANCE?exchange=NSE")
    await client.delete("/api/watchlist/RELIANCE")

    persist_path = watchlist_router._WATCHLIST_JSON
    with open(persist_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "RELIANCE" not in data


@pytest.mark.asyncio
async def test_watchlist_get_returns_expiry_and_lot_size(client: AsyncClient) -> None:
    """GET /api/watchlist should return expiry and lot_size for futures."""
    resp = await client.post("/api/watchlist/NIFTY-FO?exchange=NSE_FNO")
    assert resp.status_code == 200

    resp2 = await client.get("/api/watchlist")
    items = resp2.json()
    nifty_items = [i for i in items if "NIFTY" in i["symbol"] and i.get("expiry")]
    assert len(nifty_items) > 0
    assert nifty_items[0]["lot_size"] == 75


@pytest.mark.asyncio
async def test_watchlist_add_alias_bnf(client: AsyncClient) -> None:
    """Adding 'BNF' (alias for BANKNIFTY) should resolve."""
    resp = await client.post("/api/watchlist/BNF?exchange=NSE_FNO")
    assert resp.status_code == 200
    data = resp.json()
    assert data["security_id"] == "BANKNIFTY"


@pytest.mark.asyncio
async def test_symbol_search_unknown_returns_empty(client: AsyncClient) -> None:
    """Searching for a non-existent symbol returns empty hits, not 500."""
    resp = await client.get("/api/symbols/search?q=ZZZZZNOTEXIST")
    assert resp.status_code == 200
    assert resp.json()["hits"] == []


# ── Suffix normalization unit tests ──────────────────────────────────────

def test_strip_suffix_eq() -> None:
    assert watchlist_router._strip_suffix("RELIANCE-EQ") == "RELIANCE"


def test_strip_suffix_be() -> None:
    assert watchlist_router._strip_suffix("YESBANK-BE") == "YESBANK"


def test_strip_suffix_index() -> None:
    assert watchlist_router._strip_suffix("NIFTY-INDEX") == "NIFTY"


def test_strip_suffix_fo() -> None:
    assert watchlist_router._strip_suffix("NIFTY-FO") == "NIFTY"


def test_strip_suffix_fut() -> None:
    assert watchlist_router._strip_suffix("NIFTY-FUT") == "NIFTY"


def test_strip_suffix_plain() -> None:
    assert watchlist_router._strip_suffix("RELIANCE") == "RELIANCE"


def test_infer_type_index() -> None:
    assert watchlist_router._infer_instrument_type_from_input("NIFTY-INDEX") == "INDEX"


def test_infer_type_futures() -> None:
    assert watchlist_router._infer_instrument_type_from_input("NIFTY-FO") == "FUTURES"


def test_infer_type_option() -> None:
    assert watchlist_router._infer_instrument_type_from_input("NIFTY24000CE") == "OPTION"


def test_infer_type_equity() -> None:
    assert watchlist_router._infer_instrument_type_from_input("RELIANCE") is None


def test_infer_type_option_with_digits() -> None:
    assert watchlist_router._infer_instrument_type_from_input("NIFTY24000CE") == "OPTION"


def test_infer_type_not_option_without_digits() -> None:
    """RELIANCE ends with 'CE' but has no digits before it — not an option."""
    assert watchlist_router._infer_instrument_type_from_input("RELIANCE") is None
