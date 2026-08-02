"""Tests for the research API endpoints (spec §3.2)."""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.research_router as rr
from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import SimulatedProvider
from shettyxtreme.research.store import ResearchStore
from shettyxtreme.terminal.api.app import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


_IMPORT_STATE = (rr.RESEARCH_DB_PATH, rr._ORCHESTRATOR)
_IMPORT_LEARNING_DB = rr.LEARNING_DB_PATH


@pytest_asyncio.fixture(autouse=True)
async def _restore_research_globals(tmp_path):
    rr.LEARNING_DB_PATH = str(tmp_path / "learning.db")
    yield
    rr.RESEARCH_DB_PATH, rr._ORCHESTRATOR = _IMPORT_STATE
    rr.LEARNING_DB_PATH = _IMPORT_LEARNING_DB
    rr.init_research(broadcast_fn=None, scheduler=None)


@pytest_asyncio.fixture
def orchestrator(tmp_path) -> ResearchOrchestrator:
    store = ResearchStore(str(tmp_path / "research.db"))
    rr.RESEARCH_DB_PATH = str(tmp_path / "research.db")
    rr._ORCHESTRATOR = ResearchOrchestrator(provider=SimulatedProvider(), store=store)
    return rr._ORCHESTRATOR


@pytest.mark.asyncio
async def test_lenses(client: AsyncClient) -> None:
    resp = await client.get("/api/research/lenses")
    assert resp.status_code == 200
    names = {l["name"] for l in resp.json()["lenses"]}
    assert names == {"oi_iv_flow", "directional_momentum", "tail_risk"}


@pytest.mark.asyncio
async def test_run_all_lenses(client: AsyncClient, orchestrator) -> None:
    resp = await client.post("/api/research/run", json={})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 3
    assert all(r["brief"] is not None for r in results)
    assert all(r["error"] is None for r in results)


@pytest.mark.asyncio
async def test_run_subset(client: AsyncClient, orchestrator) -> None:
    resp = await client.post("/api/research/run", json={"lenses": ["tail_risk"]})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["lens"] == "tail_risk"


@pytest.mark.asyncio
async def test_run_unknown_lens_400(client: AsyncClient, orchestrator) -> None:
    resp = await client.post("/api/research/run", json={"lenses": ["nope"]})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_run_with_context(client: AsyncClient, orchestrator) -> None:
    resp = await client.post(
        "/api/research/run",
        json={"lenses": ["oi_iv_flow"], "context": {"regime": "TRENDING_UP"}},
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["brief"] is not None


@pytest.mark.asyncio
async def test_run_503_without_key(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    rr._ORCHESTRATOR = None
    resp = await client.post("/api/research/run", json={})
    assert resp.status_code == 503
    assert "DEEPSEEK_API_KEY" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_briefs_list_and_get(client: AsyncClient, orchestrator) -> None:
    await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    resp = await client.get("/api/research/briefs")
    assert resp.status_code == 200
    briefs = resp.json()["briefs"]
    assert len(briefs) == 1
    brief_id = briefs[0]["brief_id"]
    got = await client.get(f"/api/research/briefs/{brief_id}")
    assert got.status_code == 200
    assert got.json()["brief_id"] == brief_id
    missing = await client.get("/api/research/briefs/nope")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_approve_reject_and_409(client: AsyncClient, orchestrator) -> None:
    await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief_id = (await client.get("/api/research/briefs")).json()["briefs"][0]["brief_id"]
    ok = await client.post(f"/api/research/briefs/{brief_id}/approve")
    assert ok.status_code == 200
    assert ok.json()["status"] == "approved"
    again = await client.post(f"/api/research/briefs/{brief_id}/approve")
    assert again.status_code == 409
    reject = await client.post(f"/api/research/briefs/{brief_id}/reject")
    assert reject.status_code == 409


@pytest.mark.asyncio
async def test_missing_db_returns_empty(client: AsyncClient, tmp_path) -> None:
    rr.RESEARCH_DB_PATH = str(tmp_path / "nonexistent" / "research.db")
    resp = await client.get("/api/research/briefs")
    assert resp.status_code == 200
    assert resp.json()["briefs"] == []


import shettyxtreme.terminal.api.research_router as rr
from shettyxtreme.research.provider import ToolCall
from shettyxtreme.research.scheduler import ResearchScheduler


@pytest.mark.asyncio
async def test_tools_listing(client: AsyncClient) -> None:
    resp = await client.get("/api/research/tools")
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["tools"]}
    assert names == {
        "chain_snapshot",
        "regime_snapshot",
        "scanner_alerts",
        "options_posture",
        "knowledge_search",
    }
    chain = next(t for t in resp.json()["tools"] if t["name"] == "chain_snapshot")
    assert chain["params_schema"]["required"] == ["symbol"]


@pytest.mark.asyncio
async def test_run_with_tools(client: AsyncClient, tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "research.db"))
    rr.RESEARCH_DB_PATH = str(tmp_path / "research.db")
    rr._ORCHESTRATOR = ResearchOrchestrator(
        provider=SimulatedProvider(
            script=[
                '{"instruments": [], "direction": 0, "confidence": 0.5, '
                '"thesis": "T", "rationale": "' + "r" * 320 + '", '
                '"evidence": [], "risks": []}'
            ],
            simulate_tool_calls=[
                ToolCall(name="regime_snapshot", arguments={}),
            ],
        ),
        store=store,
    )
    resp = await client.post(
        "/api/research/run",
        json={"lenses": ["oi_iv_flow"], "tools": ["regime_snapshot", "scanner_alerts"]},
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["brief"] is not None
    assert results[0]["error"] is None


@pytest.mark.asyncio
async def test_run_unknown_tool_400(client: AsyncClient, orchestrator) -> None:
    resp = await client.post(
        "/api/research/run", json={"lenses": ["oi_iv_flow"], "tools": ["nope"]}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_scheduler_status_disabled(client: AsyncClient) -> None:
    rr.init_research(broadcast_fn=None, scheduler=None)
    resp = await client.get("/api/research/scheduler")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["interval_minutes"] == 60.0


@pytest.mark.asyncio
async def test_scheduler_status_reflects_handle(client: AsyncClient, tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "research.db"))
    orch = ResearchOrchestrator(provider=SimulatedProvider(), store=store)
    sched = ResearchScheduler(orchestrator=orch, interval_minutes=30, lenses=["tail_risk"], tools=["regime_snapshot"])
    rr.init_research(broadcast_fn=None, scheduler=sched)
    resp = await client.get("/api/research/scheduler")
    body = resp.json()
    assert body["enabled"] is False
    assert body["interval_minutes"] == 30
    assert body["lenses"] == ["tail_risk"]
    assert body["tools"] == ["regime_snapshot"]
    rr.init_research(broadcast_fn=None, scheduler=None)


@pytest.mark.asyncio
async def test_outcome_flow(client: AsyncClient, orchestrator) -> None:
    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    assert brief is not None
    # outcome on proposed -> 409
    r409 = await client.post(
        f"/api/research/briefs/{brief['brief_id']}/outcome", json={"outcome": "WIN"}
    )
    assert r409.status_code == 409
    # decide then score
    r_ok = await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")
    assert r_ok.status_code == 200
    r_out = await client.post(
        f"/api/research/briefs/{brief['brief_id']}/outcome", json={"outcome": "WIN"}
    )
    assert r_out.status_code == 200
    assert r_out.json()["outcome"] == "WIN"
    # unknown brief -> 404
    r404 = await client.post(
        "/api/research/briefs/nope/outcome", json={"outcome": "WIN"}
    )
    assert r404.status_code == 404


@pytest.mark.asyncio
async def test_outcome_invalid_value_400(client: AsyncClient, orchestrator) -> None:
    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")
    r_bad = await client.post(
        f"/api/research/briefs/{brief['brief_id']}/outcome", json={"outcome": "DRAW"}
    )
    assert r_bad.status_code == 400


@pytest.mark.asyncio
async def test_scoring_empty_db(client: AsyncClient, tmp_path) -> None:
    rr.RESEARCH_DB_PATH = str(tmp_path / "scoring_empty.db")
    resp = await client.get("/api/research/scoring")
    assert resp.status_code == 200
    assert resp.json()["lenses"] == []


@pytest.mark.asyncio
async def test_scoring_after_decisions(client: AsyncClient, orchestrator) -> None:
    resp = await client.post(
        "/api/research/run", json={"lenses": ["oi_iv_flow", "tail_risk"]}
    )
    items = resp.json()["results"]
    briefs = [r["brief"] for r in items if r["brief"] is not None]
    assert len(briefs) == 2
    for b in briefs:
        await client.post(f"/api/research/briefs/{b['brief_id']}/approve")
        await client.post(
            f"/api/research/briefs/{b['brief_id']}/outcome", json={"outcome": "WIN"}
        )
    resp2 = await client.get("/api/research/scoring")
    lenses = {l["lens"]: l for l in resp2.json()["lenses"]}
    assert lenses["oi_iv_flow"]["total"] == 1
    assert lenses["oi_iv_flow"]["with_outcome"] == 1
    assert lenses["oi_iv_flow"]["win_rate"] == 1.0


@pytest.mark.asyncio
async def test_decided_at_in_brief_response(client: AsyncClient, orchestrator) -> None:
    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    assert brief is not None
    assert brief["decided_at"] is None
    await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")
    fetched = await client.get(f"/api/research/briefs/{brief['brief_id']}")
    assert fetched.json()["decided_at"] is not None


@pytest.mark.asyncio
async def test_broadcast_new_brief_and_decision(client: AsyncClient, tmp_path) -> None:
    events: list[dict] = []
    rr.init_research(broadcast_fn=events.append, scheduler=None)
    store = ResearchStore(str(tmp_path / "research.db"))
    rr.RESEARCH_DB_PATH = str(tmp_path / "research.db")
    rr._ORCHESTRATOR = ResearchOrchestrator(
        provider=SimulatedProvider(), store=store, on_brief=rr._on_brief
    )
    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    assert brief is not None
    await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")
    kinds = [e["event"] for e in events]
    assert "new_brief" in kinds
    assert "decision" in kinds
    decision = next(e for e in events if e["event"] == "decision")
    assert decision["data"]["brief_id"] == brief["brief_id"]
    assert decision["data"]["status"] == "approved"
    rr.init_research(broadcast_fn=None, scheduler=None)


@pytest.mark.asyncio
async def test_module_globals_restored() -> None:
    assert (rr.RESEARCH_DB_PATH, rr._ORCHESTRATOR) == _IMPORT_STATE


from shettyxtreme.terminal.api.research_router import _normalize_regime


def test_normalize_regime_maps_names_and_values() -> None:
    assert _normalize_regime("TRENDING_UP") == "trending_up"
    assert _normalize_regime("trending_up") == "trending_up"
    assert _normalize_regime("VOLATILE") == "volatile"
    assert _normalize_regime("nonsense") is None
    assert _normalize_regime(None) is None
    assert _normalize_regime("") is None


@pytest.mark.asyncio
async def test_regime_normalized_at_decision(client, orchestrator, monkeypatch) -> None:
    monkeypatch.setattr(rr, "_current_regime", lambda request: "TRENDING_UP")
    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")
    fetched = (await client.get(f"/api/research/briefs/{brief['brief_id']}")).json()
    assert fetched["regime_at_decision"] == "trending_up"


@pytest.mark.asyncio
async def test_approve_records_decision_into_learning_store(
    client, orchestrator, tmp_path
) -> None:
    """Approving a brief must populate learning.db (P4c outcome wiring)."""
    from shettyxtreme.learning.outcome_tracker import OutcomeTracker

    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    assert brief is not None
    await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")

    tracker = OutcomeTracker(rr.LEARNING_DB_PATH)
    decisions = tracker.get_all_decisions()
    tracker.close()
    assert len(decisions) == 1
    d = decisions[0]
    assert d.id == f"research:{brief['brief_id']}"
    assert d.signal.conviction == pytest.approx(brief["confidence"])
    assert d.strategy_hint["kind"] == "research"
    assert d.strategy_hint["lens"] == "oi_iv_flow"
    assert d.outcome is None


@pytest.mark.asyncio
async def test_outcome_records_into_learning_store(
    client, orchestrator, tmp_path
) -> None:
    """The outcome endpoint must link WIN/LOSS back to the recorded decision."""
    from shettyxtreme.learning.outcome_tracker import OutcomeLabel, OutcomeTracker

    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    assert brief is not None
    await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")
    r_out = await client.post(
        f"/api/research/briefs/{brief['brief_id']}/outcome", json={"outcome": "WIN"}
    )
    assert r_out.status_code == 200

    tracker = OutcomeTracker(rr.LEARNING_DB_PATH)
    d = tracker.get_decision(f"research:{brief['brief_id']}")
    tracker.close()
    assert d is not None
    assert d.outcome == OutcomeLabel.WIN


@pytest.mark.asyncio
async def test_rejected_brief_not_recorded(client, orchestrator, tmp_path) -> None:
    """Rejected briefs produce no trade — nothing enters the learning store."""
    from shettyxtreme.learning.outcome_tracker import OutcomeTracker

    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    assert brief is not None
    await client.post(f"/api/research/briefs/{brief['brief_id']}/reject")

    tracker = OutcomeTracker(rr.LEARNING_DB_PATH)
    decisions = tracker.get_all_decisions()
    tracker.close()
    assert decisions == []
