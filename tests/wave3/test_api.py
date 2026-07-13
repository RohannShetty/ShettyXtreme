"""Tests for the FastAPI terminal API."""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from shettyxtreme.terminal.api.app import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Fixture providing an async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Root ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_root_returns_info(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert "ShettyXtreme" in data["name"]


# ── Watchlist ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_empty_watchlist(client: AsyncClient) -> None:
    resp = await client.get("/api/watchlist")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_add_and_get_watchlist(client: AsyncClient) -> None:
    resp = await client.post("/api/watchlist/NIFTY?exchange=NSE")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "NIFTY"

    resp2 = await client.get("/api/watchlist")
    items = resp2.json()
    assert len(items) >= 1
    symbols = [i["symbol"] for i in items]
    assert "NIFTY" in symbols


@pytest.mark.asyncio
async def test_remove_from_watchlist(client: AsyncClient) -> None:
    await client.post("/api/watchlist/RELIANCE")
    resp = await client.delete("/api/watchlist/RELIANCE")
    assert resp.status_code == 204

    resp2 = await client.get("/api/watchlist")
    symbols = [i["symbol"] for i in resp2.json()]
    assert "RELIANCE" not in symbols


# ── Intelligence ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_regime(client: AsyncClient) -> None:
    resp = await client.get("/api/intelligence/regime")
    assert resp.status_code == 200
    data = resp.json()
    assert "regime" in data
    assert "confidence" in data
    assert 0 <= data["confidence"] <= 1


@pytest.mark.asyncio
async def test_get_signal(client: AsyncClient) -> None:
    resp = await client.get("/api/intelligence/signal")
    assert resp.status_code == 200
    data = resp.json()
    assert data["direction"] in ("UP", "DOWN", "NEUTRAL")
    assert "conviction" in data
    assert "voters" in data


@pytest.mark.asyncio
async def test_get_voters(client: AsyncClient) -> None:
    resp = await client.get("/api/intelligence/voters")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_options(client: AsyncClient) -> None:
    resp = await client.get("/api/intelligence/options?symbol=NIFTY")
    assert resp.status_code == 200
    data = resp.json()
    assert data["underlying"] == "NIFTY"
    assert "contracts" in data


@pytest.mark.asyncio
async def test_get_strategy_hint(client: AsyncClient) -> None:
    resp = await client.get("/api/intelligence/strategy-hint")
    assert resp.status_code == 200
    data = resp.json()
    assert "direction" in data
    assert "rationale" in data


# ── Execution ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_positions(client: AsyncClient) -> None:
    resp = await client.get("/api/execution/positions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_risk(client: AsyncClient) -> None:
    resp = await client.get("/api/execution/risk")
    assert resp.status_code == 200
    data = resp.json()
    assert "daily_pnl" in data
    assert "margin_available" in data


@pytest.mark.asyncio
async def test_get_mode(client: AsyncClient) -> None:
    resp = await client.get("/api/execution/mode")
    assert resp.status_code == 200
    data = resp.json()
    assert "mode" in data


@pytest.mark.asyncio
async def test_set_mode(client: AsyncClient) -> None:
    resp = await client.post("/api/execution/mode?mode=LIVE")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "LIVE"


@pytest.mark.asyncio
async def test_kill_switch(client: AsyncClient) -> None:
    resp = await client.get("/api/execution/kill-switch")
    assert resp.status_code == 200
    data = resp.json()
    assert "active" in data


# ── Scanner ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_gaps(client: AsyncClient) -> None:
    resp = await client.get("/api/scanner/gaps")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_clusters(client: AsyncClient) -> None:
    resp = await client.get("/api/scanner/clusters")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_alerts(client: AsyncClient) -> None:
    resp = await client.get("/api/scanner/alerts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_logs(client: AsyncClient) -> None:
    resp = await client.get("/api/scanner/logs?limit=10")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_logs_invalid_limit(client: AsyncClient) -> None:
    resp = await client.get("/api/scanner/logs?limit=9999")
    assert resp.status_code == 422  # validation error


# ── Health ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_health(client: AsyncClient) -> None:
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "components" in data
    assert "overall" in data
    assert len(data["components"]) >= 1


@pytest.mark.asyncio
async def test_get_session(client: AsyncClient) -> None:
    resp = await client.get("/api/health/session")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] in ("pre_open", "open", "post_close", "closed")
