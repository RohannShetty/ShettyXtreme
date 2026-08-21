"""Phase 4 lifespan wiring tests (spec 4A §3.6, 4B §4.1, P4a pipeline wiring)."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.research_router as rr
from shettyxtreme.core.data_models.market_data import Tick
from shettyxtreme.core.event_bus import Event, Topic
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
        def has_data(self) -> bool:
            return True

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


@pytest.mark.asyncio
async def test_lifespan_wires_shadow_loop() -> None:
    """The real lifespan must register shadow voters and bind the loop."""
    async with app.router.lifespan_context(app):
        loop = getattr(app.state, "shadow_loop", None)
        assert loop is not None
        names = loop.shadow_names
        assert set(names) == {
            "shadow_dpg_vote",
            "shadow_orb_decay",
            "shadow_signal_drift_ev",
            "shadow_time_bucketed_oi",
        }


@pytest.mark.asyncio
async def test_lifespan_wires_intelligence_pipeline() -> None:
    """The real lifespan must instantiate the pipeline and register live voters."""
    async with app.router.lifespan_context(app):
        assert getattr(app.state, "feature_engine", None) is not None
        assert getattr(app.state, "signal_engine", None) is not None
        assert app.state.intelligence_pipeline == "started"
        voter_names = set(app.state.signal_engine.voters)
        assert {"options_flow_voter", "micro_voter", "breadth_voter"} <= voter_names
        # F-INTEL-001: stub voters (orb / iv_rank) must not be registered —
        # they voted constant directions on features that are never computed.
        assert not {"orb", "iv_rank"} & voter_names
        # Ticks published on the real bus flow through the wiring end-to-end.
        bus = app.state.event_bus
        now = datetime.now(UTC)
        for i in range(40):
            tick = Tick(
                symbol="NIFTY", exchange="NSE",
                ltp=100.0 + i, volume=100,
                high=101.0 + i, low=99.0 + i,
                timestamp=now,
            )
            await bus.publish(Event(Topic.MARKET_DATA_TICK, tick, source="test"))
        for _ in range(200):
            if app.state.intelligence_projection.get_regime().get("adx") is not None:
                break
            await asyncio.sleep(0.05)
        regime = app.state.intelligence_projection.get_regime()
        assert regime["adx"] is not None, "regime bridge never received features"
        signal = app.state.intelligence_projection.get_signal()
        assert signal["direction"] in ("UP", "DOWN", "NEUTRAL")
