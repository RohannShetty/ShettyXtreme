"""Phase 4 lifespan wiring tests (spec 4A §3.6, 4B §4.1)."""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.research_router as rr
from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import SimulatedProvider
from shettyxtreme.research.store import ResearchStore
from shettyxtreme.terminal.api import app as app_module
from shettyxtreme.terminal.api.app import app


def test_knowledge_router_importable() -> None:
    from shettyxtreme.terminal.api.knowledge_router import router

    assert router.prefix == "/api/knowledge"


def test_analytics_router_importable() -> None:
    from shettyxtreme.terminal.api.analytics_router import router

    assert router.prefix == "/api/analytics"


def test_app_imports_clean() -> None:
    assert app_module.app is not None


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
def orchestrator(tmp_path) -> ResearchOrchestrator:
    store = ResearchStore(str(tmp_path / "research.db"))
    rr.RESEARCH_DB_PATH = str(tmp_path / "research.db")
    rr._ORCHESTRATOR = ResearchOrchestrator(provider=SimulatedProvider(), store=store)
    return rr._ORCHESTRATOR


@pytest.mark.asyncio
async def test_decide_records_regime_from_projection(
    client: AsyncClient, orchestrator
) -> None:
    """approve/reject record the current regime via the intelligence projection."""

    class FakeProj:
        def get_regime(self) -> dict:
            return {"regime": "trending_up"}

    app.state.intelligence_projection = FakeProj()
    try:
        resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
        brief = resp.json()["results"][0]["brief"]
        assert brief is not None
        await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")
        fetched = await client.get(f"/api/research/briefs/{brief['brief_id']}")
        assert fetched.json()["regime_at_decision"] == "trending_up"
    finally:
        del app.state.intelligence_projection


@pytest.mark.asyncio
async def test_lifespan_wires_trade_ledger() -> None:
    async with app.router.lifespan_context(app):
        assert hasattr(app.state, "trade_ledger")
        assert getattr(app.state, "current_session_id", None) is not None
