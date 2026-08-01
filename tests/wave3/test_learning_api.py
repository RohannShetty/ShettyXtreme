"""Tests for the learning status endpoints (spec §3.7)."""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import shettyxtreme.terminal.api.learning_router as lr
from shettyxtreme.learning.outcome_tracker import OutcomeLabel, OutcomeTracker
from shettyxtreme.terminal.api.app import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Fixture providing an async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_calibration_empty_without_db(client: AsyncClient) -> None:
    lr.LEARNING_DB_PATH = "C:/nonexistent/learning.db"
    resp = await client.get("/api/learning/calibration")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reliable"] is False
    assert data["points"] == []


@pytest.mark.asyncio
async def test_shadows_empty_without_db(client: AsyncClient) -> None:
    lr.SHADOW_DB_PATH = "C:/nonexistent/shadow.db"
    resp = await client.get("/api/learning/shadows")
    assert resp.status_code == 200
    assert resp.json()["shadows"] == []


@pytest.mark.asyncio
async def test_calibration_with_populated_db(client: AsyncClient, tmp_path) -> None:
    db = tmp_path / "learning.db"
    tracker = OutcomeTracker(str(db))
    from datetime import UTC, datetime
    from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection, Vote

    def decision(conviction: float):
        sig = Signal(direction=SignalDirection.UP, conviction=conviction,
                     voters=[Vote(1.0, conviction, 1.0, "v")], timestamp=datetime.now(UTC))
        return sig

    for _ in range(40):
        did = tracker.record_signal_decision(decision(0.8), {})
        tracker.record_outcome(did, OutcomeLabel.WIN)
    tracker.close()
    lr.LEARNING_DB_PATH = str(db)
    resp = await client.get("/api/learning/calibration")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reliable"] is True
    assert len(data["points"]) > 0
    assert data["points"][0]["sample_size"] >= 0


@pytest.mark.asyncio
async def test_shadows_with_populated_db(client: AsyncClient, tmp_path) -> None:
    from tests.wave6.session_simulator import (
        SimulatedSession, SimulatedSignal, make_shadow_manager, run_sessions,
    )
    from shettyxtreme.learning.outcome_tracker import OutcomeLabel as OL

    db = tmp_path / "shadow.db"
    mgr = make_shadow_manager(str(db))
    sessions = [
        SimulatedSession(
            date=f"2026-02-{i+1:02d}",
            signals=[SimulatedSignal(features={}, regime=None, options_context={},
                                     live_direction=1.0, outcome=OL.WIN)],
        )
        for i in range(21)
    ]
    run_sessions(mgr, sessions)
    mgr.close()
    lr.SHADOW_DB_PATH = str(db)
    resp = await client.get("/api/learning/shadows")
    assert resp.status_code == 200
    shadows = resp.json()["shadows"]
    names = {s["name"]: s for s in shadows}
    assert names["good_voter"]["sessions"] == 21
    assert names["good_voter"]["evaluated"] == 21
    assert names["good_voter"]["hit_rate"] > 0.55
    assert names["good_voter"]["graduated"] is False  # not graduated yet
    assert names["poor_voter"]["hit_rate"] < 0.55
