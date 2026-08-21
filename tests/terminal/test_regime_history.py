"""Tests for regime history: AnalyticsStore + IntelligenceProjection hook + endpoint (3A.3)."""
from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shettyxtreme.core.event_bus.event_bus import Event, Topic
from shettyxtreme.terminal.api.analytics_store import AnalyticsStore
from shettyxtreme.terminal.api.analytics_router import router
from shettyxtreme.terminal.projections import IntelligenceProjection


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


# ── Store-level ──────────────────────────────────────────────────────────────


def test_record_and_get_regime_history(tmp_path) -> None:
    store = AnalyticsStore(str(tmp_path / "analytics.db"))
    try:
        store.record_regime("trending_up", 0.75, adx=28.0, di_plus=24.0, di_minus=20.0)
        store.record_regime("range_bound", 0.6, adx=15.0)

        history = store.get_regime_history(days=30)
        assert len(history) == 2
        assert list(history[0].keys()) == ["timestamp", "regime", "confidence", "adx"]
        datetime.fromisoformat(history[0]["timestamp"])
        assert history[0]["regime"] == "trending_up"
        assert history[0]["confidence"] == 0.75
        assert history[0]["adx"] == 28.0
        assert history[1]["regime"] == "range_bound"
        assert history[1]["adx"] == 15.0
    finally:
        store.close()


# ── Projection hook ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_regime_changed_records_regime(tmp_path) -> None:
    store = AnalyticsStore(str(tmp_path / "analytics.db"))
    proj = IntelligenceProjection(analytics_store=store)
    try:
        await proj.on_regime_changed(Event(
            topic=Topic.REGIME_CHANGED,
            data={
                "regime": "trending_up",
                "confidence": 0.8,
                "transition": True,
                "adx": 26.0,
                "di_plus": 22.0,
                "di_minus": 18.0,
            },
            source="test",
        ))

        history = store.get_regime_history(days=30)
        assert len(history) == 1
        assert history[0]["regime"] == "trending_up"
        assert history[0]["confidence"] == 0.8
        assert history[0]["adx"] == 26.0
        # Projection state itself is still the live view.
        assert proj.get_regime()["regime"] == "trending_up"
    finally:
        store.close()


@pytest.mark.asyncio
async def test_on_regime_changed_records_null_indicators(tmp_path) -> None:
    """Regime change without adx/di values records NULLs, not a crash."""
    store = AnalyticsStore(str(tmp_path / "analytics.db"))
    proj = IntelligenceProjection(analytics_store=store)
    try:
        await proj.on_regime_changed(Event(
            topic=Topic.REGIME_CHANGED,
            data={"regime": "range_bound", "confidence": 0.5},
            source="test",
        ))

        history = store.get_regime_history(days=30)
        assert len(history) == 1
        assert history[0]["adx"] is None
    finally:
        store.close()


@pytest.mark.asyncio
async def test_on_regime_changed_without_store_does_not_raise() -> None:
    proj = IntelligenceProjection()
    await proj.on_regime_changed(Event(
        topic=Topic.REGIME_CHANGED,
        data={"regime": "trending_up", "confidence": 0.8},
        source="test",
    ))


# ── Endpoint-level ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regime_history_endpoint(app_client, monkeypatch, tmp_path) -> None:
    app, client = app_client
    store = AnalyticsStore(str(tmp_path / "analytics.db"))
    monkeypatch.setattr(app.state, "analytics_store", store, raising=False)
    try:
        store.record_regime("trending_up", 0.75, adx=28.0)

        resp = await client.get("/api/analytics/regime-history?days=30")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert set(body[0].keys()) == {"timestamp", "regime", "confidence", "adx"}
        assert body[0]["regime"] == "trending_up"
        assert body[0]["confidence"] == 0.75
        assert body[0]["adx"] == 28.0
    finally:
        store.close()


@pytest.mark.asyncio
async def test_regime_history_endpoint_degrades_without_store(app_client) -> None:
    _, client = app_client
    resp = await client.get("/api/analytics/regime-history?days=30")
    assert resp.status_code == 200
    assert resp.json() == []
