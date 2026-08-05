"""Tests for watchlist REST hydration (live wins, REST backfills zeros).

Follows the wave9 fake-state pattern: the shared app's state is set
directly per test (no lifespan), mirroring test_market_router.py.
Fyers contract: hydration calls ``adapter.get_ohlc(symbol) -> dict``
(with open/high/low/close/ltp) per symbol, falling back to
``adapter.get_ltp(symbol) -> float`` when the OHLC payload lacks an ltp.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from shettyxtreme.terminal.api.app import app
from shettyxtreme.terminal.projections import WatchlistProjection


class FakeDataAdapter:
    """AsyncMock-style adapter recording call args and returning canned bodies."""

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


def _ohlc(ltp: float, close: float, open_: float = 2850.0) -> dict[str, Any]:
    return {"open": open_, "high": max(open_, ltp) + 10.0, "low": min(open_, ltp) - 10.0,
            "close": close, "ltp": ltp}


@pytest.mark.asyncio
async def test_hydrates_zero_ltp_rows_with_ohlc(client: AsyncClient) -> None:
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
async def test_ohlc_without_ltp_falls_back_to_get_ltp(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    # OHLC payload present but no ltp key -> fall back to get_ltp.
    app.state.data_adapter = FakeDataAdapter(
        ohlc_map={"RELIANCE": {"open": 2850.0, "close": 2840.25, "ltp": 0}},
        ltp_map={"RELIANCE": 2901.35},
    )

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 2901.35
    assert row["change_pct"] == pytest.approx(2.15)
    assert ("ltp", "RELIANCE") in adapter_calls(client)


def adapter_calls(client: AsyncClient) -> list[tuple]:
    return app.state.data_adapter.calls


@pytest.mark.asyncio
async def test_halted_security_no_data_leaves_row_unchanged(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    app.state.data_adapter = FakeDataAdapter()  # halted -> no OHLC/ltp

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0


@pytest.mark.asyncio
async def test_adapter_raising_never_breaks_response(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")

    class RaisingAdapter(FakeDataAdapter):
        async def get_ohlc(self, symbol: str) -> dict[str, Any]:
            raise RuntimeError("boom")

    app.state.data_adapter = RaisingAdapter()

    resp = await client.get("/api/watchlist")

    assert resp.status_code == 200
    (row,) = resp.json()
    assert row["ltp"] == 0.0
    assert row["change_pct"] == 0.0


@pytest.mark.asyncio
async def test_mixed_symbols_hydrated_individually(client: AsyncClient) -> None:
    proj = app.state.watchlist_projection
    proj.add("RELIANCE", "NSE", security_id="RELIANCE")
    proj.add("NIFTY", "NFO", security_id="NIFTY")
    app.state.data_adapter = FakeDataAdapter(
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
