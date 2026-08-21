"""Knowledge export tests (S2) - markdown/PDF download, 404/400 guards."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.knowledge_router as kr
from shettyxtreme.knowledge.schemas import KnowledgeDoc
from shettyxtreme.knowledge.store import KnowledgeStore
from shettyxtreme.terminal.api.app import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def kstore(tmp_path):
    store = KnowledgeStore(str(tmp_path / "k.db"))
    old = kr._STORE
    kr._STORE = store
    yield store
    kr._STORE = old
    try:
        store.close()
    except Exception:
        pass


def _doc(doc_id: str = "doc1") -> KnowledgeDoc:
    return KnowledgeDoc(
        doc_id=doc_id,
        kind="research_brief",
        source_ref=f"src-{doc_id}",
        payload={
            "thesis": "NIFTY trending up",
            "rationale": "Elevated IV, call skew",
            "evidence": [{"item": "PCR 0.8", "source": "NSE"}],
        },
        tags=[{"tag": "NIFTY", "kind": "symbol"}, {"tag": "trending_up", "kind": "regime"}],
    )


@pytest.mark.asyncio
async def test_export_markdown_success(client: AsyncClient, kstore: KnowledgeStore) -> None:
    kstore.ingest(_doc("d1"))
    resp = await client.get("/api/knowledge/docs/d1/export", params={"format": "md"})
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers.get("content-type", "")
    assert "doc-d1.md" in resp.headers.get("content-disposition", "")
    text = resp.text
    assert "NIFTY trending up" in text
    assert "Elevated IV" in text
    assert "PCR 0.8" in text
    assert "NIFTY (symbol)" in text
    assert "# Knowledge Document:" in text
    assert "## Tags" in text
    assert "## Content" in text
    assert "## Evidence" in text
    assert "## Metadata" in text


@pytest.mark.asyncio
async def test_export_pdf_success(client: AsyncClient, kstore: KnowledgeStore) -> None:
    kstore.ingest(_doc("d2"))
    resp = await client.get("/api/knowledge/docs/d2/export", params={"format": "pdf"})
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers.get("content-type", "")
    assert "doc-d2.pdf" in resp.headers.get("content-disposition", "")
    assert resp.content.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_export_not_found(client: AsyncClient, kstore: KnowledgeStore) -> None:
    resp = await client.get("/api/knowledge/docs/nope/export", params={"format": "md"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_unsupported_format(client: AsyncClient, kstore: KnowledgeStore) -> None:
    kstore.ingest(_doc("d3"))
    resp = await client.get("/api/knowledge/docs/d3/export", params={"format": "docx"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_export_stale_doc(client: AsyncClient, kstore: KnowledgeStore) -> None:
    kstore.ingest(_doc("d-stale"))
    old_ts = "2020-01-01T00:00:00+00:00"
    kstore._conn.execute("UPDATE docs SET created_at = ? WHERE doc_id = ?", (old_ts, "d-stale"))
    kstore._conn.commit()
    resp = await client.get("/api/knowledge/docs/d-stale/export", params={"format": "md"})
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers.get("content-type", "")
