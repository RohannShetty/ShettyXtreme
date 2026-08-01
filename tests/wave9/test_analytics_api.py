"""Analytics API tests (spec 4B §4.3, §6)."""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.analytics_router as ar
from shettyxtreme.learning.sessions import SessionLog
from shettyxtreme.terminal.api.app import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_scorecard_empty(client: AsyncClient, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ar, "RESEARCH_DB_PATH", str(tmp_path / "research.db"))
    monkeypatch.setattr(ar, "SESSIONS_DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.setattr(ar, "LEARNING_DB_PATH", str(tmp_path / "learning.db"))
    resp = await client.get("/api/analytics/scorecard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metrics"] != []
    assert all(m["available"] is False for m in body["metrics"])
    assert body["by_regime"] == []
    assert body["calibration"] == []


@pytest.mark.asyncio
async def test_scorecard_with_data(client: AsyncClient, tmp_path, monkeypatch) -> None:
    from shettyxtreme.research.briefs import ResearchBrief
    from shettyxtreme.research.store import ResearchStore

    rstore = ResearchStore(str(tmp_path / "research.db"))
    cases = [
        ("approved", "WIN", "trending_up"),
        ("approved", "LOSS", "trending_up"),
        ("rejected", None, "range_bound"),
    ]
    for i, (status, outcome, regime) in enumerate(cases):
        b = ResearchBrief(
            brief_id=f"b{i}",
            lens="oi_iv_flow",
            as_of="t",
            direction=1,
            confidence=0.6,
            thesis="t",
            rationale="r" * 320,
            evidence=[],
            risks=[],
        )
        rstore.insert(b)
        rstore.decide(b.brief_id, status, regime=regime)
        if outcome:
            rstore.set_outcome(b.brief_id, outcome)
    rstore.close()

    log = SessionLog(str(tmp_path / "s.db"))
    sid = log.start("OBSERVER")
    log.end(sid)
    log.close()

    monkeypatch.setattr(ar, "RESEARCH_DB_PATH", str(tmp_path / "research.db"))
    monkeypatch.setattr(ar, "SESSIONS_DB_PATH", str(tmp_path / "s.db"))
    resp = await client.get("/api/analytics/scorecard")
    assert resp.status_code == 200
    body = resp.json()
    by_key = {m["key"]: m for m in body["metrics"]}
    assert by_key["sessions_total"]["value"] == 1
    assert by_key["decisions"]["value"] == 3
    assert by_key["win_rate"]["value"] == 0.5
    rows = {r["regime"]: r for r in body["by_regime"]}
    assert rows["trending_up"]["win_rate"] == 0.5
    assert rows["range_bound"]["with_outcome"] == 0


@pytest.mark.asyncio
async def test_sessions_endpoint(client: AsyncClient, tmp_path, monkeypatch) -> None:
    log = SessionLog(str(tmp_path / "s.db"))
    log.start("LIVE")
    log.close()
    monkeypatch.setattr(ar, "SESSIONS_DB_PATH", str(tmp_path / "s.db"))
    resp = await client.get("/api/analytics/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["sessions"]) == 1
    assert body["counts"]["live"] == 1
