"""Tests for max pain history: AnalyticsStore + IntelligenceProjection hook + endpoint (3A.3)."""
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

# Two strikes, weighted so max pain lands at 24500 (see options.max_pain).
_CONTRACTS = [
    {"strike": 24400, "oi": 100, "option_type": "CE"},
    {"strike": 24400, "oi": 200, "option_type": "PE"},
    {"strike": 24500, "oi": 300, "option_type": "CE"},
    {"strike": 24500, "oi": 400, "option_type": "PE"},
]


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


def test_record_and_get_max_pain_history(tmp_path) -> None:
    store = AnalyticsStore(str(tmp_path / "analytics.db"))
    try:
        store.record_max_pain("NIFTY", "28AUG", 24500.0, 24550.0)
        store.record_max_pain("NIFTY", "28AUG", 24550.0, 24600.0)

        history = store.get_max_pain_history("NIFTY", days=30)
        assert len(history) == 2
        assert list(history[0].keys()) == ["timestamp", "max_pain", "spot_price"]
        datetime.fromisoformat(history[0]["timestamp"])
        assert history[0]["max_pain"] == 24500.0
        assert history[0]["spot_price"] == 24550.0
        assert history[1]["max_pain"] == 24550.0
    finally:
        store.close()


def test_get_max_pain_history_filters_symbol(tmp_path) -> None:
    store = AnalyticsStore(str(tmp_path / "analytics.db"))
    try:
        store.record_max_pain("NIFTY", "28AUG", 24500.0, 24550.0)
        store.record_max_pain("BANKNIFTY", "28AUG", 50000.0, 50100.0)

        history = store.get_max_pain_history("NIFTY", days=30)
        assert len(history) == 1
        assert history[0]["max_pain"] == 24500.0
    finally:
        store.close()


# ── Projection hook ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_market_data_records_max_pain(tmp_path) -> None:
    store = AnalyticsStore(str(tmp_path / "analytics.db"))
    proj = IntelligenceProjection(analytics_store=store)
    try:
        await proj.on_market_data(Event(
            topic=Topic.MARKET_DATA_BAR,
            data={
                "symbol": "NIFTY",
                "expiry": "28AUG",
                "spot": 24550.0,
                "contracts": _CONTRACTS,
            },
            source="test",
        ))

        history = store.get_max_pain_history("NIFTY", days=30)
        assert len(history) == 1
        assert history[0]["max_pain"] == 24500.0
        assert history[0]["spot_price"] == 24550.0
    finally:
        store.close()


@pytest.mark.asyncio
async def test_on_market_data_ignores_non_chain_payloads(tmp_path) -> None:
    store = AnalyticsStore(str(tmp_path / "analytics.db"))
    proj = IntelligenceProjection(analytics_store=store)
    try:
        # A plain bar dict without contracts must not record anything.
        await proj.on_market_data(Event(
            topic=Topic.MARKET_DATA_BAR,
            data={"symbol": "NIFTY", "oi": 12345, "ltp": 24550.0},
            source="test",
        ))
        assert store.get_max_pain_history("NIFTY", days=30) == []
    finally:
        store.close()


@pytest.mark.asyncio
async def test_on_market_data_without_store_does_not_raise() -> None:
    proj = IntelligenceProjection()
    await proj.on_market_data(Event(
        topic=Topic.MARKET_DATA_BAR,
        data={"symbol": "NIFTY", "expiry": "28AUG", "contracts": _CONTRACTS},
        source="test",
    ))


# ── Endpoint-level ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_max_pain_history_endpoint(app_client, monkeypatch, tmp_path) -> None:
    app, client = app_client
    store = AnalyticsStore(str(tmp_path / "analytics.db"))
    monkeypatch.setattr(app.state, "analytics_store", store, raising=False)
    try:
        store.record_max_pain("NIFTY", "28AUG", 24500.0, 24550.0)

        resp = await client.get("/api/analytics/max-pain-history?symbol=NIFTY&days=30")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert set(body[0].keys()) == {"timestamp", "max_pain", "spot_price"}
        assert body[0]["max_pain"] == 24500.0
    finally:
        store.close()


@pytest.mark.asyncio
async def test_max_pain_history_endpoint_degrades_without_store(app_client) -> None:
    _, client = app_client
    resp = await client.get("/api/analytics/max-pain-history?symbol=NIFTY&days=30")
    assert resp.status_code == 200
    assert resp.json() == []
