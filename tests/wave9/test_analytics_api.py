"""Analytics API tests (spec 4B §4.3, §6)."""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.analytics_router as ar
from shettyxtreme.execution.ledger import TradeLedger
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
    monkeypatch.setattr(ar, "LEDGER_DB_PATH", str(tmp_path / "ledger.db"))
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


@pytest.mark.asyncio
async def test_ledger_empty_and_populated(client, tmp_path, monkeypatch) -> None:
    db = str(tmp_path / "ledger.db")
    monkeypatch.setattr(ar, "LEDGER_DB_PATH", db)
    resp = await client.get("/api/analytics/ledger")
    assert resp.status_code == 200
    assert resp.json()["fills"] == []
    store = TradeLedger(db)
    store.record_fill({"fill_id": "O1:paper", "order_id": "O1", "session_id": "S1",
                       "symbol": "NIFTY", "side": "BUY", "quantity": 75,
                       "price": 100.0, "product": None, "source": "paper",
                       "recorded_at": "2026-08-02T10:00:00Z"})
    store.record_fill({"fill_id": "O2:paper", "order_id": "O2", "session_id": "S1",
                       "symbol": "NIFTY", "side": "SELL", "quantity": 75,
                       "price": 110.0, "product": None, "source": "paper",
                       "recorded_at": "2026-08-02T11:00:00Z"})
    store.close()
    resp2 = await client.get("/api/analytics/ledger")
    body = resp2.json()
    assert len(body["fills"]) == 2
    assert body["sessions"][0]["session_id"] == "S1"
    assert body["sessions"][0]["realized_pnl"] == 750.0


@pytest.mark.asyncio
async def test_scorecard_net_ev_metrics(client, tmp_path, monkeypatch) -> None:
    db = str(tmp_path / "ledger.db")
    monkeypatch.setattr(ar, "LEDGER_DB_PATH", db)
    store = TradeLedger(db)
    store.record_fill({"fill_id": "O1:paper", "order_id": "O1", "session_id": "S1",
                       "symbol": "NIFTY", "side": "BUY", "quantity": 75,
                       "price": 100.0, "product": None, "source": "paper",
                       "recorded_at": "2026-08-02T10:00:00Z"})
    store.record_fill({"fill_id": "O2:paper", "order_id": "O2", "session_id": "S1",
                       "symbol": "NIFTY", "side": "SELL", "quantity": 75,
                       "price": 110.0, "product": None, "source": "paper",
                       "recorded_at": "2026-08-02T11:00:00Z"})
    store.close()
    resp = await client.get("/api/analytics/scorecard")
    metrics = {m["key"]: m for m in resp.json()["metrics"]}
    assert metrics["fills"]["value"] == 2
    assert metrics["fills"]["available"] is True
    assert metrics["net_ev_per_session"]["available"] is True
    assert metrics["net_ev_per_session"]["value"] == 750.0 - 2 * 25.0


@pytest.mark.asyncio
async def test_scorecard_net_ev_unavailable_empty(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ar, "LEDGER_DB_PATH", str(tmp_path / "empty_ledger.db"))
    resp = await client.get("/api/analytics/scorecard")
    metrics = {m["key"]: m for m in resp.json()["metrics"]}
    assert metrics["fills"]["available"] is False
    assert metrics["net_ev_per_session"]["available"] is False


class _FakeProjection:
    """Minimal double for app.state.intelligence_projection (get_regime only)."""

    def __init__(self, regime: str) -> None:
        self._regime = regime

    def get_regime(self) -> dict:
        return {"regime": self._regime}


@pytest.mark.asyncio
async def test_scorecard_current_regime_null_without_projection(
    client, tmp_path, monkeypatch
) -> None:
    """No intelligence projection wired → current_regime is None (never 500)."""
    from shettyxtreme.terminal.api.app import app

    monkeypatch.setattr(ar, "RESEARCH_DB_PATH", str(tmp_path / "research.db"))
    monkeypatch.setattr(ar, "SESSIONS_DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.setattr(ar, "LEARNING_DB_PATH", str(tmp_path / "learning.db"))
    monkeypatch.setattr(ar, "LEDGER_DB_PATH", str(tmp_path / "ledger.db"))
    # Guarantee absence regardless of leftovers from lifespan-wiring tests.
    monkeypatch.delattr(app.state, "intelligence_projection", raising=False)
    resp = await client.get("/api/analytics/scorecard")
    assert resp.status_code == 200
    assert resp.json()["current_regime"] is None


@pytest.mark.asyncio
async def test_scorecard_carries_current_regime(client, tmp_path, monkeypatch) -> None:
    """Scorecard reflects the projection's current regime (phase6 #11)."""
    from shettyxtreme.terminal.api.app import app

    monkeypatch.setattr(ar, "RESEARCH_DB_PATH", str(tmp_path / "research.db"))
    monkeypatch.setattr(ar, "SESSIONS_DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.setattr(ar, "LEARNING_DB_PATH", str(tmp_path / "learning.db"))
    monkeypatch.setattr(ar, "LEDGER_DB_PATH", str(tmp_path / "ledger.db"))
    monkeypatch.setattr(
        app.state, "intelligence_projection", _FakeProjection("trending_up"), raising=False
    )
    resp = await client.get("/api/analytics/scorecard")
    assert resp.status_code == 200
    assert resp.json()["current_regime"] == "trending_up"


@pytest.mark.asyncio
async def test_scorecard_regime_lookup_failure_degrades_to_null(
    client, tmp_path, monkeypatch
) -> None:
    """A broken projection (get_regime raises) → None, response still 200."""
    from shettyxtreme.terminal.api.app import app

    monkeypatch.setattr(ar, "RESEARCH_DB_PATH", str(tmp_path / "research.db"))
    monkeypatch.setattr(ar, "SESSIONS_DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.setattr(ar, "LEARNING_DB_PATH", str(tmp_path / "learning.db"))
    monkeypatch.setattr(ar, "LEDGER_DB_PATH", str(tmp_path / "ledger.db"))

    class _BrokenProjection:
        def get_regime(self) -> dict:
            raise RuntimeError("boom")

    monkeypatch.setattr(app.state, "intelligence_projection", _BrokenProjection(), raising=False)
    resp = await client.get("/api/analytics/scorecard")
    assert resp.status_code == 200
    assert resp.json()["current_regime"] is None
