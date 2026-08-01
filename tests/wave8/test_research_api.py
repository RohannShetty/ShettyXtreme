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
