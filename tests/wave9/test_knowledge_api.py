"""Knowledge API tests (spec 4A §3.6, §6)."""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.knowledge_router as kr
from shettyxtreme.knowledge.schemas import KnowledgeDoc
from shettyxtreme.knowledge.store import KnowledgeStore
from shettyxtreme.terminal.api.app import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
def kstore(tmp_path) -> KnowledgeStore:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    kr._STORE = store
    return store


@pytest.mark.asyncio
async def test_status_empty(client: AsyncClient, kstore) -> None:
    resp = await client.get("/api/knowledge/status")
    assert resp.status_code == 200
    assert resp.json() == {"docs": 0, "proposed": 0, "activated": 0, "tags": 0}


@pytest.mark.asyncio
async def test_sync_and_search(client: AsyncClient, kstore, tmp_path) -> None:
    from shettyxtreme.research.briefs import ResearchBrief
    from shettyxtreme.research.store import ResearchStore

    rstore = ResearchStore(str(tmp_path / "research.db"))
    kr.RESEARCH_DB_PATH = str(tmp_path / "research.db")
    brief = ResearchBrief(
        brief_id="b1",
        lens="oi_iv_flow",
        as_of="t",
        direction=1,
        confidence=0.6,
        thesis="NIFTY trending up",
        rationale="r" * 320,
        evidence=[],
        risks=[],
    )
    rstore.insert(brief)
    rstore.decide("b1", "approved")
    rstore.close()

    resp = await client.post("/api/knowledge/sync")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ingested"] == 1 and body["skipped_undecided"] == 0

    resp2 = await client.get("/api/knowledge/search", params={"q": "trending"})
    assert resp2.status_code == 200
    hits = resp2.json()["hits"]
    assert len(hits) == 1 and hits[0]["source_ref"] == "b1"


@pytest.mark.asyncio
async def test_activate_flow(client: AsyncClient, kstore) -> None:
    kstore.ingest(
        KnowledgeDoc(
            doc_id="d1", kind="research_brief", source_ref="b1", payload={"thesis": "x"}
        )
    )
    resp = await client.post("/api/knowledge/docs/d1/activate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "activated"
    resp2 = await client.post("/api/knowledge/docs/nope/activate")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_sync_missing_research_db(client: AsyncClient, kstore, tmp_path) -> None:
    kr.RESEARCH_DB_PATH = str(tmp_path / "missing.db")
    resp = await client.post("/api/knowledge/sync")
    assert resp.status_code == 200  # degraded, never 500
    assert resp.json()["ingested"] == 0


@pytest.mark.asyncio
async def test_broadcast_on_activate(client: AsyncClient, kstore) -> None:
    events: list[dict] = []
    kr.init_knowledge(store=kstore, broadcast_fn=events.append)
    kstore.ingest(
        KnowledgeDoc(
            doc_id="d1", kind="research_brief", source_ref="b1", payload={"thesis": "x"}
        )
    )
    await client.post("/api/knowledge/docs/d1/activate")
    assert any(e["event"] == "activated" for e in events)
    kr.init_knowledge(store=None, broadcast_fn=None)


@pytest.mark.asyncio
async def test_create_note_ingests_proposed(client: AsyncClient, kstore) -> None:
    resp = await client.post("/api/knowledge/notes", json={
        "title": "NIFTY setup", "body": "NIFTY trending up, elevated iv",
    })
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["kind"] == "operator_note"
    assert doc["status"] == "proposed"
    tags = {t["tag"] for t in doc["tags"]}
    assert "NIFTY" in tags and "trending_up" in tags


@pytest.mark.asyncio
async def test_create_note_empty_title_422(client: AsyncClient) -> None:
    resp = await client.post("/api/knowledge/notes", json={"title": "", "body": "x"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_note_activate_flow(client: AsyncClient, kstore) -> None:
    created = (await client.post("/api/knowledge/notes", json={
        "title": "T", "body": "range bound NIFTY",
    })).json()
    activated = await client.post(f"/api/knowledge/docs/{created['doc_id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "activated"
