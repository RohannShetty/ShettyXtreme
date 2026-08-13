"""Tests for the PCR history endpoint + OITracker.get_pcr_history (3A.3)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shettyxtreme.options.oi_tracker import OISnapshot, OITracker
from shettyxtreme.terminal.api.analytics_router import router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest_asyncio.fixture
async def app_client() -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield app, ac


# ── Tracker-level ────────────────────────────────────────────────────────────


def test_get_pcr_history_from_chain_poll() -> None:
    tracker = OITracker()
    tracker.update_from_chain("NIFTY", "28AUG", [
        {"strike": 24500, "option_type": "CE", "oi": 2000},
        {"strike": 24500, "option_type": "PE", "oi": 4000},
        {"strike": 24600, "option_type": "CE", "oi": 1000},
        {"strike": 24600, "option_type": "PE", "oi": 1000},
    ])

    history = tracker.get_pcr_history("NIFTY", days=30)
    assert len(history) == 1  # one poll → one bucket
    entry = history[0]
    assert set(entry.keys()) == {"timestamp", "pcr", "total_call_oi", "total_put_oi"}
    assert entry["total_call_oi"] == 3000
    assert entry["total_put_oi"] == 5000
    assert entry["pcr"] == pytest.approx(1.6667, abs=0.001)
    datetime.fromisoformat(entry["timestamp"])  # ISO-8601, parseable


def test_get_pcr_history_buckets_separate_polls_and_orders() -> None:
    tracker = OITracker()
    t1 = datetime.now(UTC) - timedelta(days=2)
    t2 = t1 + timedelta(minutes=5)
    tracker._snapshots.extend([
        OISnapshot(symbol="NIFTY", expiry="28AUG", strike=24500.0,
                   option_type="CE", oi=1000, timestamp=t1),
        OISnapshot(symbol="NIFTY", expiry="28AUG", strike=24500.0,
                   option_type="PE", oi=1500, timestamp=t1),
        OISnapshot(symbol="NIFTY", expiry="28AUG", strike=24600.0,
                   option_type="CE", oi=500, timestamp=t2),
        OISnapshot(symbol="NIFTY", expiry="28AUG", strike=24600.0,
                   option_type="PE", oi=500, timestamp=t2),
    ])

    history = tracker.get_pcr_history("NIFTY", days=30)
    assert len(history) == 2  # two polls → two buckets, oldest first
    assert history[0]["pcr"] == 1.5
    assert history[0]["timestamp"] == t1.replace(microsecond=0).isoformat()
    assert history[1]["pcr"] == 1.0
    assert history[1]["total_call_oi"] == 500
    assert history[1]["total_put_oi"] == 500


def test_get_pcr_history_filters_symbol_and_days() -> None:
    tracker = OITracker()
    now = datetime.now(UTC)
    old = now - timedelta(days=60)
    tracker._snapshots.extend([
        OISnapshot(symbol="NIFTY", expiry="28AUG", strike=24500.0,
                   option_type="CE", oi=1000, timestamp=now),
        OISnapshot(symbol="NIFTY", expiry="28AUG", strike=24500.0,
                   option_type="PE", oi=2000, timestamp=now),
        OISnapshot(symbol="BANKNIFTY", expiry="28AUG", strike=50000.0,
                   option_type="CE", oi=999, timestamp=now),
        OISnapshot(symbol="NIFTY", expiry="28AUG", strike=24500.0,
                   option_type="CE", oi=100, timestamp=old),
    ])

    history = tracker.get_pcr_history("NIFTY", days=30)
    assert len(history) == 1  # BANKNIFTY + 60-day-old NIFTY rows excluded
    assert history[0]["total_call_oi"] == 1000
    assert history[0]["pcr"] == 2.0

    # days=1 keeps the recent poll but still filters the 60-day-old row.
    recent = tracker.get_pcr_history("NIFTY", days=1)
    assert len(recent) == 1
    assert recent[0]["total_call_oi"] == 1000


def test_get_pcr_history_empty_without_snapshots() -> None:
    assert OITracker().get_pcr_history("NIFTY", days=30) == []


# ── Endpoint-level ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pcr_history_endpoint(app_client, monkeypatch) -> None:
    app, client = app_client
    tracker = OITracker()
    tracker.update_from_chain("NIFTY", "28AUG", [
        {"strike": 24500, "option_type": "CE", "oi": 2000},
        {"strike": 24500, "option_type": "PE", "oi": 4000},
    ])
    monkeypatch.setattr(app.state, "oi_tracker", tracker, raising=False)

    resp = await client.get("/api/analytics/pcr-history?symbol=NIFTY&days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert set(body[0].keys()) == {"timestamp", "pcr", "total_call_oi", "total_put_oi"}
    assert body[0]["pcr"] == 2.0


@pytest.mark.asyncio
async def test_pcr_history_endpoint_degrades_without_tracker(app_client) -> None:
    _, client = app_client
    resp = await client.get("/api/analytics/pcr-history?symbol=NIFTY&days=30")
    assert resp.status_code == 200
    assert resp.json() == []
