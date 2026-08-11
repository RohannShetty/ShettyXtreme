"""Tests for the market router (/api/market/bars, /api/market/ltp).

Follows the wave9 fake-state pattern: the shared app's state is set
directly per test (no lifespan), mirroring wave3's setup_projections.
The Fyers data adapter contract: ``get_intraday_bars(symbol, tf, days,
exchange) -> list[Bar]``, ``get_ohlc(symbol) -> dict``, ``get_ltp(symbol)
-> float``; a missing data entitlement surfaces as
:class:`FyersDataEntitlementError` (403/-373) or an ``entitlement_error``
flag on the adapter.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, AsyncIterator
from zoneinfo import ZoneInfo

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.market_router as market_router_mod
from shettyxtreme.core.interfaces.market_data_stream import Bar
from shettyxtreme.integration.fyers.client import (
    FyersDataEntitlementError,
    FyersRateLimitError,
    FyersTokenExpired,
)
from shettyxtreme.terminal.api.app import app

_TS = datetime(2026, 8, 4, 5, 30, tzinfo=UTC)


def _bars(*prices: tuple[float, float, float, float]) -> list[Bar]:
    """Build Bar rows from (open, high, low, close) tuples at 1-minute spacing."""
    return [
        Bar(
            symbol="NIFTY",
            exchange="NSE_FNO",
            timeframe="1min",
            open=o, high=h, low=l, close=c,
            volume=1000 + i,
            timestamp=datetime.fromtimestamp(_TS.timestamp() + i * 60, tz=UTC),
        )
        for i, (o, h, l, c) in enumerate(prices)
    ]


class FakeDataAdapter:
    """AsyncMock-style adapter recording call args and returning canned bars."""

    def __init__(
        self,
        bars: list[Bar] | None = None,
        ohlc: dict[str, Any] | None = None,
        ltp: float | None = None,
        entitlement_error: bool = False,
    ) -> None:
        self.bars = bars
        self.ohlc = ohlc
        self.ltp = ltp
        self.entitlement_error = entitlement_error
        self.calls: list[tuple] = []

    async def get_intraday_bars(
        self, symbol: str, tf: str, days: int, exchange: str
    ) -> list[Bar]:
        self.calls.append(("bars", symbol, tf, days, exchange))
        return self.bars or []

    async def get_ohlc(self, symbol: str) -> dict[str, Any]:
        self.calls.append(("ohlc", symbol))
        return self.ohlc or {}

    async def get_ltp(self, symbol: str) -> float:
        self.calls.append(("ltp", symbol))
        return self.ltp or 0.0


class RaisingEntitlementAdapter(FakeDataAdapter):
    async def get_intraday_bars(self, symbol, tf, days, exchange):
        raise FyersDataEntitlementError("403")


class RaisingAdapter(FakeDataAdapter):
    """Adapter that raises a fixed exception from every data verb —
    exercises the router's transport-error classification (F-TERM-005)."""

    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self.exc = exc

    async def get_intraday_bars(self, *args: Any, **kwargs: Any) -> list[Bar]:
        raise self.exc

    async def get_ohlc(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise self.exc

    async def get_ltp(self, *args: Any, **kwargs: Any) -> float:
        raise self.exc


class RaisingAdapter(FakeDataAdapter):
    """Adapter that raises a fixed exception from every data verb —
    exercises the router's transport-error classification (F-TERM-005)."""

    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self.exc = exc

    async def get_intraday_bars(self, *args: Any, **kwargs: Any) -> list[Bar]:
        raise self.exc

    async def get_ohlc(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise self.exc

    async def get_ltp(self, *args: Any, **kwargs: Any) -> float:
        raise self.exc


class FakeSymbolResolver:
    """Stand-in for FyersSymbolResolver: to_fyers succeeds for known symbols."""

    def __init__(self) -> None:
        self.known = {"NIFTY", "BANKNIFTY", "RELIANCE", "TATAMOTORS"}

    def to_fyers(self, symbol: str, exchange: str, instrument_type: str) -> str:
        if symbol.upper() in self.known:
            return f"NSE:{symbol.upper()}-INDEX"
        raise ValueError(f"unknown symbol {symbol}")


@pytest_asyncio.fixture(autouse=True)
async def reset_state() -> AsyncIterator[None]:
    """Ensure the shared app starts every test with no adapter/resolver."""
    app.state.data_adapter = None
    app.state.symbol_resolver = None
    yield
    app.state.data_adapter = None
    app.state.symbol_resolver = None


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_bars_adapter_unavailable_503(client: AsyncClient) -> None:
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "market data adapter not available — check credentials / Fyers feed"


@pytest.mark.asyncio
async def test_bars_happy_path_maps_bars(client: AsyncClient) -> None:
    adapter = FakeDataAdapter(bars=_bars((22550.0, 22560.0, 22540.0, 22555.0)))
    app.state.data_adapter = adapter
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO&tf=1&days=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "NIFTY"
    assert body["exchange"] == "NSE_FNO"
    bars = body["bars"]
    assert len(bars) == 1
    assert bars[0]["open"] == 22550.0
    assert bars[0]["high"] == 22560.0
    assert bars[0]["low"] == 22540.0
    assert bars[0]["close"] == 22555.0
    assert bars[0]["volume"] == 1000
    kind, symbol, tf, days, exchange = adapter.calls[0]
    assert kind == "bars"
    assert symbol == "NIFTY"
    assert tf == "1"
    assert days == 1
    assert exchange == "NSE_FNO"


@pytest.mark.asyncio
async def test_bars_sorts_and_caps(client: AsyncClient) -> None:
    # 400 bars for a 1-day request must be capped to 375.
    bars = _bars(*[(22550.0 + i, 22560.0, 22540.0, 22555.0) for i in range(400)])
    app.state.data_adapter = FakeDataAdapter(bars=bars)
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO&days=1")
    assert resp.status_code == 200
    assert len(resp.json()["bars"]) == 375


@pytest.mark.asyncio
async def test_bars_entitlement_flag_503(client: AsyncClient) -> None:
    app.state.data_adapter = FakeDataAdapter(entitlement_error=True)
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    assert resp.json()["detail"] == (
        "Data API entitlement missing — subscribe to Data APIs (Fyers 403/-373)"
    )


@pytest.mark.asyncio
async def test_bars_entitlement_exception_503(client: AsyncClient) -> None:
    app.state.data_adapter = RaisingEntitlementAdapter()
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    assert "subscribe to Data APIs" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_bars_symbol_resolution_via_resolver(client: AsyncClient) -> None:
    adapter = FakeDataAdapter(bars=_bars((100.0, 101.0, 99.0, 100.5)))
    app.state.data_adapter = adapter
    app.state.symbol_resolver = FakeSymbolResolver()
    resp = await client.get("/api/market/bars?symbol=RELIANCE&exchange=NSE")
    assert resp.status_code == 200
    kind, symbol, *_ = adapter.calls[0]
    assert symbol == "RELIANCE"


@pytest.mark.asyncio
async def test_bars_fyers_ticker_passthrough(client: AsyncClient) -> None:
    adapter = FakeDataAdapter(bars=_bars((100.0, 101.0, 99.0, 100.5)))
    app.state.data_adapter = adapter
    resp = await client.get("/api/market/bars?symbol=NSE:NIFTY50-INDEX&exchange=NSE_FNO")
    assert resp.status_code == 200
    kind, symbol, *_ = adapter.calls[0]
    assert symbol == "NSE:NIFTY50-INDEX"


@pytest.mark.asyncio
async def test_bars_rejects_unsupported_interval(client: AsyncClient) -> None:
    app.state.data_adapter = FakeDataAdapter()
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO&tf=7")
    assert resp.status_code == 422
    assert resp.json()["detail"] == "tf must be one of 1, 5, 15, 25, 60"


@pytest.mark.asyncio
async def test_bars_unknown_symbol_404(client: AsyncClient) -> None:
    app.state.data_adapter = FakeDataAdapter()
    app.state.symbol_resolver = FakeSymbolResolver()
    resp = await client.get("/api/market/bars?symbol=NOSUCHSYMBOL&exchange=NSE_FNO")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Symbol not found"


@pytest.mark.asyncio
async def test_ltp_happy_path(client: AsyncClient) -> None:
    adapter = FakeDataAdapter(
        ohlc={"open": 22500.0, "high": 22600.0, "low": 22400.0, "close": 22450.0, "ltp": 22555.5},
    )
    app.state.data_adapter = adapter
    resp = await client.get("/api/market/ltp?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "NIFTY"
    assert body["exchange"] == "NSE_FNO"
    assert body["ltp"] == 22555.5
    assert body["prev_close"] == 22450.0
    assert adapter.calls[0] == ("ohlc", "NIFTY")


@pytest.mark.asyncio
async def test_ltp_falls_back_to_get_ltp_when_ohlc_missing(client: AsyncClient) -> None:
    adapter = FakeDataAdapter(ohlc={}, ltp=22555.5)
    app.state.data_adapter = adapter
    resp = await client.get("/api/market/ltp?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 200
    assert resp.json()["ltp"] == 22555.5
    assert adapter.calls == [("ohlc", "NIFTY"), ("ltp", "NIFTY")]


@pytest.mark.asyncio
async def test_ltp_missing_price_502(client: AsyncClient) -> None:
    app.state.data_adapter = FakeDataAdapter(ohlc={}, ltp=0.0)
    resp = await client.get("/api/market/ltp?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 502
    assert resp.json()["detail"] == "LTP not found in response"


@pytest.mark.asyncio
async def test_ltp_adapter_unavailable_503(client: AsyncClient) -> None:
    resp = await client.get("/api/market/ltp?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "market data adapter not available — check credentials / Fyers feed"


@pytest.mark.asyncio
async def test_ltp_entitlement_503(client: AsyncClient) -> None:
    app.state.data_adapter = FakeDataAdapter(entitlement_error=True)
    resp = await client.get("/api/market/ltp?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    assert resp.json()["detail"] == (
        "Data API entitlement missing — subscribe to Data APIs (Fyers 403/-373)"
    )


# ── F-TERM-005: adapter transport failures → structured errors ─────────────

@pytest.mark.asyncio
async def test_bars_network_timeout_503_structured(client: AsyncClient) -> None:
    """Network timeout is transient → 503 with an error code; the raw
    httpx exception text must not leak into the response."""
    app.state.data_adapter = RaisingAdapter(httpx.ConnectTimeout("connect timed out"))
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    body = resp.json()["detail"]
    assert body["error_code"] == "upstream_unavailable"
    assert "Fyers" in body["message"]
    assert "connect timed out" not in str(resp.json())


@pytest.mark.asyncio
async def test_bars_asyncio_timeout_503_structured(client: AsyncClient) -> None:
    app.state.data_adapter = RaisingAdapter(asyncio.TimeoutError("slow"))
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error_code"] == "upstream_unavailable"


@pytest.mark.asyncio
async def test_bars_rate_limit_503_structured(client: AsyncClient) -> None:
    """Rate limit is transient → 503."""
    app.state.data_adapter = RaisingAdapter(
        FyersRateLimitError("Fyers rate limit exceeded", code=-429, status_code=429)
    )
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    body = resp.json()["detail"]
    assert body["error_code"] == "rate_limited"
    assert "retry" in body["message"].lower()


@pytest.mark.asyncio
async def test_bars_auth_failure_500_structured(client: AsyncClient) -> None:
    """Auth failure is permanent → 500 with error code; raw exception hidden."""
    app.state.data_adapter = RaisingAdapter(FyersTokenExpired("HTTP 401"))
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 500
    body = resp.json()["detail"]
    assert body["error_code"] == "auth_failed"
    assert "HTTP 401" not in str(resp.json())


@pytest.mark.asyncio
async def test_bars_generic_adapter_error_500_structured(client: AsyncClient) -> None:
    """Unknown adapter failure → structured 500, never the raw exception."""
    app.state.data_adapter = RaisingAdapter(RuntimeError("boom detail"))
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 500
    body = resp.json()["detail"]
    assert body["error_code"] == "adapter_error"
    assert "boom detail" not in str(resp.json())


@pytest.mark.asyncio
async def test_ltp_transport_timeout_503_structured(client: AsyncClient) -> None:
    """The /ltp path classifies transport failures the same way."""
    app.state.data_adapter = RaisingAdapter(httpx.ReadTimeout("read timed out"))
    resp = await client.get("/api/market/ltp?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error_code"] == "upstream_unavailable"
