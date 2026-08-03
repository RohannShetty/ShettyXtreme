"""Tests for watchlist REST hydration (live wins, REST backfills zeros).

Follows the wave9 fake-state pattern: the shared app's state is set
directly per test (no lifespan), mirroring test_market_router.py.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from shettyxtreme.terminal.api.app import app
from shettyxtreme.terminal.projections import WatchlistProjection

# Real dhanhq /marketfeed/ohlc success body per security:
#   data[segment][id] = {"last_price": float, "ohlc": {open, close, high, low}}
OHLC_SUCCESS = {
    "status": "success",
    "data": {
        "NSE_EQ": {
            "2885": {
                "last_price": 2901.35,
                "ohlc": {"open": 2850.0, "close": 2840.25, "high": 2910.0, "low": 2840.0},
            },
        },
    },
}

LTP_ONLY_SUCCESS = {
    "status": "success",
    "data": {"NSE_EQ": {"2885": {"last_price": 2901.35}}},
}

FAILURE_BODY = {"status": "error", "message": "rate limited"}

HALTED_BODY = {
    "status": "success",
    "data": {"NSE_EQ": {"2885": {"last_price": None}}},
}


class FakeDataAdapter:
    """AsyncMock-style adapter recording call args and returning canned bodies."""

    def __init__(
        self,
        ohlc_body: dict[str, Any] | None = None,
        ltp_body: dict[str, Any] | None = None,
    ) -> None:
        self.ohlc_body = ohlc_body if ohlc_body is not None else OHLC_SUCCESS
        self.ltp_body = ltp_body if ltp_body is not None else LTP_ONLY_SUCCESS
        self.calls: list[tuple] = []

    async def get_ohlc(self, securities) -> dict[str, Any]:
        self.calls.append(("ohlc", securities))
        return self.ohlc_body

    async def get_ltp(self, securities) -> dict[str, Any]:
        self.calls.append(("ltp", securities))
        return self.ltp_body


@pytest_asyncio.fixture(autouse=True)
async def reset_state() -> AsyncIterator[None]:
    """Fresh watchlist projection and no adapter for every test."""
    app.state.watchlist_projection = WatchlistProjection()
    app.state.data_adapter = None
    yield
    app.state.data_adapter = None


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_hydrates_zero_ltp_rows_with_ohlc(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="2885")
    app.state.data_adapter = FakeDataAdapter()

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["symbol"] == "RELIANCE"
    assert row["ltp"] == 2901.35
    assert row["change_pct"] == pytest.approx(2.15)
    assert row["security_id"] == "2885"


@pytest.mark.asyncio
async def test_live_ltp_wins_rest_not_called(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="2885")
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
    proj.add("RELIANCE", "NSE", security_id="2885")

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0
    assert row["change_pct"] == 0.0


@pytest.mark.asyncio
async def test_rest_failure_leaves_rows_unchanged(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="2885")
    app.state.data_adapter = FakeDataAdapter(ohlc_body=FAILURE_BODY, ltp_body=FAILURE_BODY)

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0
    assert row["change_pct"] == 0.0


@pytest.mark.asyncio
async def test_ohlc_failure_falls_back_to_ltp_only(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="2885")
    app.state.data_adapter = FakeDataAdapter(ohlc_body=FAILURE_BODY)

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 2901.35
    assert row["change_pct"] == 0.0


@pytest.mark.asyncio
async def test_halted_security_last_price_null_leaves_row_unchanged(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="2885")
    app.state.data_adapter = FakeDataAdapter(ohlc_body=HALTED_BODY)

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0


@pytest.mark.asyncio
async def test_halted_security_empty_string_price_leaves_row_unchanged(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="2885")
    app.state.data_adapter = FakeDataAdapter(
        ohlc_body={
            "status": "success",
            "data": {"NSE_EQ": {"2885": {"last_price": ""}}},
        }
    )

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0


@pytest.mark.asyncio
async def test_adapter_raising_never_breaks_response(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="2885")

    class RaisingAdapter(FakeDataAdapter):
        async def get_ohlc(self, securities) -> dict[str, Any]:
            raise RuntimeError("boom")

    app.state.data_adapter = RaisingAdapter()

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0
    assert row["change_pct"] == 0.0


@pytest.mark.asyncio
async def test_mixed_segments_grouped_correctly(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="2885")
    proj.add("NIFTY", "NFO", security_id="13")
    adapter = FakeDataAdapter(
        ohlc_body={
            "status": "success",
            "data": {
                "NSE_EQ": {
                    "2885": {
                        "last_price": 2901.35,
                        "ohlc": {"open": 2850.0, "close": 2840.25, "high": 2910.0, "low": 2840.0},
                    },
                },
                "NSE_FNO": {
                    "13": {
                        "last_price": 22555.5,
                        "ohlc": {"open": 22500.0, "close": 22450.0, "high": 22600.0, "low": 22400.0},
                    },
                },
            },
        }
    )
    app.state.data_adapter = adapter

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    rows = {r["symbol"]: r for r in resp.json()}
    assert rows["RELIANCE"]["ltp"] == 2901.35
    assert rows["NIFTY"]["ltp"] == 22555.5
    assert adapter.calls == [("ohlc", {"NSE_EQ": ["2885"], "NSE_FNO": ["13"]})]
