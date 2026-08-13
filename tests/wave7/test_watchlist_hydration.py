"""Tests for watchlist REST hydration (live wins, REST backfills zeros).

Follows the wave9 fake-state pattern: the shared app's state is set
directly per test (no lifespan), mirroring test_market_router.py.
Fyers contract: hydration calls ``adapter.get_quotes(symbols: list[str])
-> dict[str, dict]`` once for all idle symbols (the adapter groups them
into <=50-ticker REST requests). Each value carries
open/high/low/close/ltp with ltp already folded from the top-level quote
field when ``fp.ltp`` is absent — no second call. Outcomes are TTL-cached
(``_hydration_cache``), so a repeat GET within the TTL does not re-trigger
the loop. Adapters that predate batching (no ``get_quotes``) fall back to
the per-symbol ``get_ohlc`` / ``get_ltp`` pair.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from shettyxtreme.terminal.api import watchlist_router
from shettyxtreme.terminal.api.app import app
from shettyxtreme.terminal.projections import WatchlistProjection


class FakeDataAdapter:
    """Batched adapter: records the full batch per get_quotes call."""

    def __init__(
        self,
        ohlc_map: dict[str, dict[str, Any]] | None = None,
        ltp_map: dict[str, float] | None = None,
    ) -> None:
        self.ohlc_map = ohlc_map or {}
        self.ltp_map = ltp_map or {}
        self.calls: list[tuple] = []

    async def get_quotes(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        self.calls.append(("quotes", tuple(symbols)))
        return {s: self.ohlc_map[s] for s in symbols if s in self.ohlc_map}

    async def get_ohlc(self, symbol: str) -> dict[str, Any]:
        self.calls.append(("ohlc", symbol))
        return self.ohlc_map.get(symbol, {})

    async def get_ltp(self, symbol: str) -> float:
        self.calls.append(("ltp", symbol))
        return self.ltp_map.get(symbol, 0.0)


class LegacyFakeDataAdapter:
    """Pre-batching adapter: get_ohlc/get_ltp only — no get_quotes.

    Exercises the router's per-symbol fallback path.
    """

    def __init__(
        self,
        ohlc_map: dict[str, dict[str, Any]] | None = None,
        ltp_map: dict[str, float] | None = None,
    ) -> None:
        self.ohlc_map = ohlc_map or {}
        self.ltp_map = ltp_map or {}
        self.calls: list[tuple] = []

    async def get_ohlc(self, symbol: str) -> dict[str, Any]:
        self.calls.append(("ohlc", symbol))
        return self.ohlc_map.get(symbol, {})

    async def get_ltp(self, symbol: str) -> float:
        self.calls.append(("ltp", symbol))
        return self.ltp_map.get(symbol, 0.0)


@pytest_asyncio.fixture(autouse=True)
async def reset_state() -> AsyncIterator[None]:
    """Fresh projection, no adapter, and an empty hydration cache for every test."""
    app.state.watchlist_projection = WatchlistProjection()
    app.state.data_adapter = None
    watchlist_router._hydration_cache.clear()
    yield
    app.state.data_adapter = None
    watchlist_router._hydration_cache.clear()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _ohlc(ltp: float, close: float, open_: float = 2850.0) -> dict[str, Any]:
    return {"open": open_, "high": max(open_, ltp) + 10.0, "low": min(open_, ltp) - 10.0,
            "close": close, "ltp": ltp}


def adapter_calls(client: AsyncClient) -> list[tuple]:
    return app.state.data_adapter.calls


@pytest.mark.asyncio
async def test_hydrates_zero_ltp_rows_with_quotes(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    app.state.data_adapter = FakeDataAdapter(
        ohlc_map={"RELIANCE": _ohlc(2901.35, 2840.25)},
    )

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["symbol"] == "RELIANCE"
    assert row["ltp"] == 2901.35
    assert row["change_pct"] == pytest.approx(2.15)
    assert row["security_id"] == "RELIANCE"


@pytest.mark.asyncio
async def test_live_ltp_wins_rest_not_called(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    app.state.watchlist_projection.get_item("RELIANCE")["ltp"] = 2950.0
    adapter = FakeDataAdapter()
    app.state.data_adapter = adapter

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 2950.0
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_adapter_none_leaves_rows_unchanged(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0
    assert row["change_pct"] == 0.0


@pytest.mark.asyncio
async def test_rest_failure_leaves_rows_unchanged(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    app.state.data_adapter = FakeDataAdapter()  # empty maps -> no data

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0
    assert row["change_pct"] == 0.0


@pytest.mark.asyncio
async def test_all_idle_symbols_fetched_in_one_batched_call(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    proj.add("NIFTY", "NFO", security_id="NIFTY")
    proj.add("SBIN", "NSE", security_id="SBIN")
    app.state.data_adapter = FakeDataAdapter(
        ohlc_map={
            "RELIANCE": _ohlc(2901.35, 2840.25),
            "NIFTY": _ohlc(22555.5, 22450.0, open_=22500.0),
            "SBIN": _ohlc(480.5, 479.0, open_=479.5),
        },
    )

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    # One batched call carrying every idle symbol — not one call per symbol.
    assert adapter_calls(client) == [
        ("quotes", ("RELIANCE", "NIFTY", "SBIN")),
    ]
    rows = {r["symbol"]: r for r in resp.json()}
    assert rows["RELIANCE"]["ltp"] == 2901.35
    assert rows["NIFTY"]["ltp"] == 22555.5
    assert rows["SBIN"]["ltp"] == 480.5


@pytest.mark.asyncio
async def test_quote_without_ltp_leaves_row_unchanged_no_second_call(
    client: AsyncClient,
) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    # Quotes payload present but no ltp -> row stays at stored values; the
    # folded batched contract does NOT issue a second get_ltp call.
    app.state.data_adapter = FakeDataAdapter(
        ohlc_map={"RELIANCE": {"open": 2850.0, "close": 2840.25, "ltp": 0}},
    )

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0
    assert adapter_calls(client) == [("quotes", ("RELIANCE",))]
    assert not any(call[0] == "ltp" for call in adapter_calls(client))


@pytest.mark.asyncio
async def test_cached_miss_not_refetched_within_ttl(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    adapter = FakeDataAdapter()  # halted -> miss, ltp stays 0
    app.state.data_adapter = adapter

    resp1 = await client.get("/api/watchlist")
    resp2 = await client.get("/api/watchlist")

    assert resp1.status_code == resp2.status_code == 200
    # One REST fetch for the first GET; the cached miss short-circuits the second.
    assert adapter_calls(client) == [("quotes", ("RELIANCE",))]
    assert watchlist_router._hydration_cache["RELIANCE"][1:] == (0.0, 0.0)


@pytest.mark.asyncio
async def test_cache_expiry_rehydrates(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    # A halted security stays at ltp 0.0 — its miss is what gets cached.
    app.state.data_adapter = FakeDataAdapter()

    resp1 = await client.get("/api/watchlist")
    assert adapter_calls(client) == [("quotes", ("RELIANCE",))]

    # Backdate the cached stamp past the TTL; a GET must re-fetch.
    stamp, ltp, change = watchlist_router._hydration_cache["RELIANCE"]
    watchlist_router._hydration_cache["RELIANCE"] = (
        stamp - watchlist_router._HYDRATION_TTL - 1.0,
        ltp,
        change,
    )
    resp2 = await client.get("/api/watchlist")

    assert resp1.status_code == resp2.status_code == 200
    assert adapter_calls(client) == [("quotes", ("RELIANCE",))] * 2


@pytest.mark.asyncio
async def test_legacy_adapter_falls_back_to_per_symbol_calls(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    proj.add("NIFTY", "NFO", security_id="NIFTY")
    app.state.data_adapter = LegacyFakeDataAdapter(
        ohlc_map={
            "RELIANCE": _ohlc(2901.35, 2840.25),
            "NIFTY": _ohlc(22555.5, 22450.0, open_=22500.0),
        },
    )

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    rows = {r["symbol"]: r for r in resp.json()}
    assert rows["RELIANCE"]["ltp"] == 2901.35
    assert rows["NIFTY"]["ltp"] == 22555.5
    assert ("ohlc", "RELIANCE") in adapter_calls(client)
    assert ("ohlc", "NIFTY") in adapter_calls(client)


@pytest.mark.asyncio
async def test_legacy_ohlc_without_ltp_falls_back_to_get_ltp(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    # OHLC payload present but no ltp key -> fall back to get_ltp (legacy path).
    app.state.data_adapter = LegacyFakeDataAdapter(
        ohlc_map={"RELIANCE": {"open": 2850.0, "close": 2840.25, "ltp": 0}},
        ltp_map={"RELIANCE": 2901.35},
    )

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 2901.35
    assert row["change_pct"] == pytest.approx(2.15)
    assert ("ltp", "RELIANCE") in adapter_calls(client)


@pytest.mark.asyncio
async def test_halted_security_no_data_leaves_row_unchanged(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    app.state.data_adapter = FakeDataAdapter()  # halted -> no quotes

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0


@pytest.mark.asyncio
async def test_hydration_stamps_refresh_timestamp(client: AsyncClient) -> None:
    """A REST-hydrated row reports when its price was refreshed.

    Task 2.1: without a stamp the API returns timestamp=None for every row
    whose feed is idle, and the frontend STALE chip (which keys on data
    freshness) paints a freshly-hydrated watchlist as fully stale.
    """
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    app.state.data_adapter = FakeDataAdapter(
        ohlc_map={"RELIANCE": _ohlc(2901.35, 2840.25)},
    )

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 2901.35
    assert row["timestamp"] is not None


@pytest.mark.asyncio
async def test_halted_row_keeps_null_timestamp(client: AsyncClient) -> None:
    """Rows with no data are NOT stamped — an honest null, never freshness."""
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    app.state.data_adapter = FakeDataAdapter()  # halted -> no quotes

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0
    assert row["timestamp"] is None


@pytest.mark.asyncio
async def test_no_adapter_rows_keep_null_timestamp(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0
    assert row["timestamp"] is None


@pytest.mark.asyncio
async def test_adapter_raising_never_breaks_response(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")

    class RaisingAdapter(FakeDataAdapter):
        async def get_quotes(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
            raise RuntimeError("boom")

    app.state.data_adapter = RaisingAdapter()

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0
    assert row["change_pct"] == 0.0
