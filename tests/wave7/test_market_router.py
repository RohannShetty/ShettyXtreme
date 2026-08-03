"""Tests for the market router (/api/market/bars, /api/market/ltp).

Follows the wave9 fake-state pattern: the shared app's state is set
directly per test (no lifespan), mirroring wave3's setup_projections.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from shettyxtreme.terminal.api.app import app

# Real dhanhq /charts/intraday success body is columnar: parallel arrays
# keyed open/high/low/close/volume/timestamp (epoch s)/open_interest.
INTRAday_SUCCESS = {
    "status": "success",
    "data": {
        "open": [22550.0, 22545.0, 22560.0],
        "high": [22560.0, 22555.0, 22575.0],
        "low": [22540.0, 22535.0, 22550.0],
        "close": [22555.0, 22550.0, 22570.0],
        "volume": [1200, 900, 1500],
        "timestamp": [2, 1, 3],
    },
}

ENTITLEMENT_BODY = {
    "status": "error",
    "entitlement": True,
    "message": "subscribe to Data APIs — Dhan error 806",
}

ERROR_BODY = {"status": "error", "message": "something broke"}

LTP_SUCCESS = {
    "status": "success",
    "data": {"NSE_FNO": {"13": {"last_price": 22555.5}}},
}


class FakeDataAdapter:
    """AsyncMock-style adapter recording call args and returning canned bodies."""

    def __init__(
        self,
        intraday_body: dict[str, Any] | None = None,
        ltp_body: dict[str, Any] | None = None,
    ) -> None:
        self.intraday_body = intraday_body or INTRAday_SUCCESS
        self.ltp_body = ltp_body or LTP_SUCCESS
        self.calls: list[tuple] = []

    async def get_intraday_bars(
        self, security_id, exchange_segment, instrument_type,
        from_date, to_date, interval=1, oi=False,
    ) -> dict[str, Any]:
        self.calls.append(("bars", security_id, exchange_segment, instrument_type, from_date, to_date, interval, oi))
        return self.intraday_body

    async def get_ltp(self, securities) -> dict[str, Any]:
        self.calls.append(("ltp", securities))
        return self.ltp_body


class FakeInstrumentMaster:
    def resolve_symbol(self, symbol: str, exchange: str = "NSE") -> str | None:
        table = {("RELIANCE", "NSE"): "2885", ("TATAMOTORS", "NSE"): "3456"}
        return table.get((symbol.upper(), exchange.upper()))


@pytest_asyncio.fixture(autouse=True)
async def reset_state() -> AsyncIterator[None]:
    """Ensure the shared app starts every test with no adapter/master."""
    app.state.data_adapter = None
    app.state.instrument_master = None
    yield
    app.state.data_adapter = None
    app.state.instrument_master = None


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_bars_adapter_unavailable_503(client: AsyncClient) -> None:
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "market data adapter not available — check credentials / Dhan feed"


@pytest.mark.asyncio
async def test_bars_happy_path_maps_columnar_body(client: AsyncClient) -> None:
    adapter = FakeDataAdapter()
    app.state.data_adapter = adapter
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO&tf=1&days=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "NIFTY"
    assert body["exchange"] == "NSE_FNO"
    bars = body["bars"]
    assert [b["timestamp"] for b in bars] == sorted(b["timestamp"] for b in bars)
    assert bars[0]["timestamp"] == "1970-01-01T00:00:01+00:00"
    assert bars[0]["open"] == 22545.0
    assert bars[0]["high"] == 22555.0
    assert bars[0]["low"] == 22535.0
    assert bars[0]["close"] == 22550.0
    assert bars[0]["volume"] == 900
    assert len(bars) == 3
    kind, sid, seg, itype, frm, to, interval, oi = adapter.calls[0]
    assert kind == "bars"
    assert sid == "13"
    assert seg == "NSE_FNO"
    assert itype == "INDEX"
    assert interval == 1
    assert frm == to


@pytest.mark.asyncio
async def test_bars_drops_malformed_row_with_none_ohlc(client: AsyncClient) -> None:
    body = {
        "status": "success",
        "data": {
            "open": [22550.0, None, 22560.0],
            "high": [22560.0, 22555.0, 22575.0],
            "low": [22540.0, 22535.0, 22550.0],
            "close": [22555.0, 22550.0, 22570.0],
            "volume": [1200, 900, 1500],
            "timestamp": [1, 2, 3],
        },
    }
    app.state.data_adapter = FakeDataAdapter(intraday_body=body)
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 200
    bars = resp.json()["bars"]
    assert [b["timestamp"] for b in bars] == [
        "1970-01-01T00:00:01+00:00",
        "1970-01-01T00:00:03+00:00",
    ]


@pytest.mark.asyncio
async def test_bars_entitlement_503(client: AsyncClient) -> None:
    app.state.data_adapter = FakeDataAdapter(intraday_body=ENTITLEMENT_BODY)
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Data API entitlement missing — subscribe to Data APIs (Dhan 806)"


@pytest.mark.asyncio
async def test_bars_other_failure_502(client: AsyncClient) -> None:
    app.state.data_adapter = FakeDataAdapter(intraday_body=ERROR_BODY)
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 502
    assert resp.json()["detail"] == "something broke"


@pytest.mark.asyncio
async def test_bars_symbol_resolution_via_instrument_master(client: AsyncClient) -> None:
    adapter = FakeDataAdapter()
    app.state.data_adapter = adapter
    app.state.instrument_master = FakeInstrumentMaster()
    resp = await client.get("/api/market/bars?symbol=RELIANCE&exchange=NSE")
    assert resp.status_code == 200
    kind, sid, seg, itype, *_ = adapter.calls[0]
    assert sid == "2885"
    assert seg == "NSE_EQ"
    assert itype == "EQUITY"


@pytest.mark.asyncio
async def test_bars_numeric_symbol_passthrough(client: AsyncClient) -> None:
    adapter = FakeDataAdapter()
    app.state.data_adapter = adapter
    resp = await client.get("/api/market/bars?symbol=13&exchange=NSE_FNO")
    assert resp.status_code == 200
    assert adapter.calls[0][1] == "13"
    assert adapter.calls[0][2] == "NSE_FNO"
    assert adapter.calls[0][3] == "INDEX"


@pytest.mark.asyncio
async def test_bars_rejects_unsupported_interval(client: AsyncClient) -> None:
    app.state.data_adapter = FakeDataAdapter()
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO&tf=7")
    assert resp.status_code == 422
    assert resp.json()["detail"] == "tf must be one of 1, 5, 15, 25, 60"


@pytest.mark.asyncio
async def test_bars_unknown_symbol_404(client: AsyncClient) -> None:
    app.state.data_adapter = FakeDataAdapter()
    resp = await client.get("/api/market/bars?symbol=NOSUCHSYMBOL&exchange=NSE_FNO")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Symbol not found"


@pytest.mark.asyncio
async def test_bars_caps_bar_count(client: AsyncClient) -> None:
    body = {
        "status": "success",
        "data": {
            "open": [22550.0] * 400,
            "high": [22560.0] * 400,
            "low": [22540.0] * 400,
            "close": [22555.0] * 400,
            "volume": [1200] * 400,
            "timestamp": list(range(400)),
        },
    }
    app.state.data_adapter = FakeDataAdapter(intraday_body=body)
    resp = await client.get("/api/market/bars?symbol=NIFTY&exchange=NSE_FNO&days=1")
    assert resp.status_code == 200
    assert len(resp.json()["bars"]) == 375


@pytest.mark.asyncio
async def test_ltp_happy_path(client: AsyncClient) -> None:
    adapter = FakeDataAdapter()
    app.state.data_adapter = adapter
    resp = await client.get("/api/market/ltp?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "NIFTY"
    assert body["exchange"] == "NSE_FNO"
    assert body["ltp"] == 22555.5
    assert adapter.calls[0] == ("ltp", {"NSE_FNO": ["13"]})


@pytest.mark.asyncio
async def test_ltp_missing_price_502(client: AsyncClient) -> None:
    app.state.data_adapter = FakeDataAdapter(
        ltp_body={
            "status": "success",
            "data": {"NSE_FNO": {"13": {"last_price": None}}},
        }
    )
    resp = await client.get("/api/market/ltp?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 502
    assert resp.json()["detail"] == "LTP not found in response"


@pytest.mark.asyncio
async def test_ltp_adapter_unavailable_503(client: AsyncClient) -> None:
    resp = await client.get("/api/market/ltp?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "market data adapter not available — check credentials / Dhan feed"


@pytest.mark.asyncio
async def test_ltp_entitlement_503(client: AsyncClient) -> None:
    app.state.data_adapter = FakeDataAdapter(ltp_body=ENTITLEMENT_BODY)
    resp = await client.get("/api/market/ltp?symbol=NIFTY&exchange=NSE_FNO")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Data API entitlement missing — subscribe to Data APIs (Dhan 806)"
