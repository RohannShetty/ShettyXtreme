"""Tests for research brief export (S1)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.research_router as rr
from shettyxtreme.research.briefs import ResearchBrief
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
async def _restore_research_globals(tmp_path):  # type: ignore[no-untyped-def]
    rr.LEARNING_DB_PATH = str(tmp_path / "learning.db")
    rr.RESEARCH_DB_PATH = str(tmp_path / "research.db")
    rr._ORCHESTRATOR = None
    rr.init_research(broadcast_fn=None, scheduler=None)
    yield
    rr.RESEARCH_DB_PATH, rr._ORCHESTRATOR = _IMPORT_STATE
    rr.LEARNING_DB_PATH = _IMPORT_LEARNING_DB
    rr.init_research(broadcast_fn=None, scheduler=None)


def _make_brief(
    brief_id: str | None = None,
    *,
    as_of: str | None = None,
    status: str = "proposed",
) -> ResearchBrief:
    now = datetime.now(UTC).isoformat()
    return ResearchBrief(
        brief_id=brief_id or str(uuid.uuid4()),
        lens="oi_iv_flow",
        as_of=as_of or now,
        instruments=["NIFTY"],
        direction=1,
        confidence=0.73,
        thesis="NIFTY shows bullish momentum with IV expansion.",
        rationale="Rationale " + "x" * 310,
        evidence=[{"item": "PCR 1.4", "source": "oi_tracker"}, {"item": "IV rank 80%", "source": "iv_engine"}],
        risks=["Gap down", "Event risk"],
        validity_window_minutes=240,
        status=status,  # type: ignore[arg-type]
    )


def _insert_brief(tmp_path, brief: ResearchBrief) -> ResearchBrief:  # type: ignore[no-untyped-def]
    store = ResearchStore(str(tmp_path / "research.db"))
    rr.RESEARCH_DB_PATH = str(tmp_path / "research.db")
    try:
        # store.insert uses model_dump_json which carries status
        store.insert(brief)
    finally:
        store.close()
    return brief


@pytest.mark.asyncio
async def test_export_markdown_success(client: AsyncClient, tmp_path) -> None:  # type: ignore[no-untyped-def]
    brief = _insert_brief(tmp_path, _make_brief(brief_id="brief-md-1"))
    resp = await client.get(f"/api/research/briefs/{brief.brief_id}/export?format=md")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert f'brief-{brief.brief_id}.md' in resp.headers["content-disposition"]
    text = resp.text
    assert "Research Brief: brief-md-1" in text
    assert brief.thesis in text
    assert brief.rationale in text
    assert "PCR 1.4" in text
    assert "Gap down" in text
    assert "## Evidence" in text
    assert "## Risks" in text
    assert "## Metadata" in text


@pytest.mark.asyncio
async def test_export_pdf_success(client: AsyncClient, tmp_path) -> None:  # type: ignore[no-untyped-def]
    brief = _insert_brief(tmp_path, _make_brief(brief_id="brief-pdf-1"))
    resp = await client.get(f"/api/research/briefs/{brief.brief_id}/export?format=pdf")
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]
    assert f'brief-{brief.brief_id}.pdf' in resp.headers["content-disposition"]
    data = resp.content
    assert data[:5] == b"%PDF-"
    assert len(data) > 200


@pytest.mark.asyncio
async def test_export_not_found(client: AsyncClient, tmp_path) -> None:  # type: ignore[no-untyped-def]
    rr.RESEARCH_DB_PATH = str(tmp_path / "research.db")
    # ensure DB exists but empty
    s = ResearchStore(str(tmp_path / "research.db"))
    s.close()
    resp = await client.get("/api/research/briefs/nope/export?format=md")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_unsupported_format(client: AsyncClient, tmp_path) -> None:  # type: ignore[no-untyped-def]
    brief = _insert_brief(tmp_path, _make_brief(brief_id="brief-badfmt"))
    resp = await client.get(f"/api/research/briefs/{brief.brief_id}/export?format=docx")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_export_stale_brief(client: AsyncClient, tmp_path) -> None:  # type: ignore[no-untyped-def]
    stale_as_of = (datetime.now(UTC) - timedelta(hours=5)).isoformat()
    brief = _insert_brief(tmp_path, _make_brief(brief_id="brief-stale-1", as_of=stale_as_of))
    resp = await client.get(f"/api/research/briefs/{brief.brief_id}/export?format=md")
    # Export allowed even if expired; UI disables button, API still serves
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
