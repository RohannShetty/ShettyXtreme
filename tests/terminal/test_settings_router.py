"""Tests for the settings API endpoints (Phase 7 Wave 3)."""
from __future__ import annotations

from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shettyxtreme.core.settings import get_settings_store, init_settings_store, reset_settings_store
import shettyxtreme.terminal.api.research_router as rr
import shettyxtreme.terminal.api.settings_router as settings_router_module
from shettyxtreme.terminal.api.settings_router import init_settings, router


@pytest_asyncio.fixture
async def client(tmp_path) -> AsyncIterator[AsyncClient]:
    init_settings_store(tmp_path / "settings.db")
    app = FastAPI()
    app.include_router(router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _restore_globals():
    yield
    settings_router_module._scheduler = None
    rr.init_research(broadcast_fn=None, scheduler=None)
    reset_settings_store()


class _FakeScheduler:
    """Duck-typed ResearchScheduler stand-in with call counters."""

    def __init__(self, interval_minutes: float = 30.0) -> None:
        self.enabled = False
        self.interval_minutes = interval_minutes
        self.lenses: list[str] | None = None
        self.tools: list[str] | None = None
        self.next_run_at: str | None = None
        self.last_run_at: str | None = None
        self.last_result: str | None = None
        self.stops = 0
        self.starts = 0

    def start(self) -> None:
        self.starts += 1
        self.enabled = True

    def stop(self) -> None:
        self.stops += 1
        self.enabled = False


class TestSettings:
    @pytest.mark.asyncio
    async def test_get_settings_defaults(self, client: AsyncClient) -> None:
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["loss_limit"] == -5000.0
        assert body["max_positions"] == 5
        assert body["theme"] == "dark"
        assert body["scheduler"]["enabled"] is False
        assert body["scheduler"]["interval_minutes"] == 60.0
        assert body["scheduler"]["running"] is False

    @pytest.mark.asyncio
    async def test_put_settings_persists(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/settings",
            json={"loss_limit": -3000.0, "max_positions": 3, "theme": "light"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["loss_limit"] == -3000.0
        assert body["max_positions"] == 3
        assert body["theme"] == "light"
        # Persisted — a fresh GET reflects the update.
        again = await client.get("/api/settings")
        assert again.json()["loss_limit"] == -3000.0
        assert again.json()["max_positions"] == 3

    @pytest.mark.asyncio
    async def test_put_settings_invalid_value_400(self, client: AsyncClient) -> None:
        resp = await client.put("/api/settings", json={"loss_limit": 1000.0})
        assert resp.status_code == 400
        assert "loss_limit" in resp.json()["detail"]
        # Store untouched.
        got = await client.get("/api/settings")
        assert got.json()["loss_limit"] == -5000.0

    @pytest.mark.asyncio
    async def test_put_settings_empty_body_400(self, client: AsyncClient) -> None:
        resp = await client.put("/api/settings", json={})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_put_settings_unknown_field_400(self, client: AsyncClient) -> None:
        resp = await client.put("/api/settings", json={"bogus": 1})
        assert resp.status_code == 400


class TestSettingsEvents:
    @pytest.mark.asyncio
    async def test_risk_change_publishes_risk_decision(self, tmp_path) -> None:
        """A loss-limit change must refresh RiskProjection via RISK_DECISION."""
        init_settings_store(tmp_path / "settings.db")

        class FakeBus:
            def __init__(self) -> None:
                self.events = []

            async def publish(self, event) -> None:
                self.events.append(event)

        app = FastAPI()
        app.include_router(router)
        bus = FakeBus()
        app.state.event_bus = bus
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put("/api/settings", json={"loss_limit": -3000.0})
        assert resp.status_code == 200
        topics = [e.topic.value for e in bus.events]
        assert "config.changed" in topics
        assert "risk.decision" in topics
        risk_event = next(e for e in bus.events if e.topic.value == "risk.decision")
        assert risk_event.data["loss_limit"] == -3000.0

    @pytest.mark.asyncio
    async def test_theme_change_skips_risk_decision(self, tmp_path) -> None:
        init_settings_store(tmp_path / "settings.db")

        class FakeBus:
            def __init__(self) -> None:
                self.events = []

            async def publish(self, event) -> None:
                self.events.append(event)

        app = FastAPI()
        app.include_router(router)
        bus = FakeBus()
        app.state.event_bus = bus
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put("/api/settings", json={"theme": "light"})
        assert resp.status_code == 200
        topics = [e.topic.value for e in bus.events]
        assert "config.changed" in topics
        assert "risk.decision" not in topics


class TestTheme:
    @pytest.mark.asyncio
    async def test_get_theme(self, client: AsyncClient) -> None:
        resp = await client.get("/api/settings/theme")
        assert resp.status_code == 200
        assert resp.json()["theme"] == "dark"

    @pytest.mark.asyncio
    async def test_put_theme_persists_and_broadcasts(self, client: AsyncClient) -> None:
        with patch(
            "shettyxtreme.terminal.api.settings_router.ws_bridge.broadcast",
            new_callable=AsyncMock,
        ) as mock_broadcast:
            resp = await client.put("/api/settings/theme", json={"theme": "light"})
        assert resp.status_code == 200
        assert resp.json()["theme"] == "light"
        mock_broadcast.assert_awaited_once_with("theme", {"theme": "light"})
        got = await client.get("/api/settings/theme")
        assert got.json()["theme"] == "light"

    @pytest.mark.asyncio
    async def test_put_theme_invalid_400(self, client: AsyncClient) -> None:
        resp = await client.put("/api/settings/theme", json={"theme": "blue"})
        assert resp.status_code == 400


class TestScheduler:
    @pytest.mark.asyncio
    async def test_get_scheduler_defaults(self, client: AsyncClient) -> None:
        resp = await client.get("/api/settings/scheduler")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["interval_minutes"] == 60.0
        assert body["running"] is False

    @pytest.mark.asyncio
    async def test_put_scheduler_persists(self, client: AsyncClient) -> None:
        resp = await client.put("/api/settings/scheduler", json={
            "enabled": True,
            "interval_minutes": 30.0,
            "lenses": ["tail_risk"],
            "tools": ["regime_snapshot"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["interval_minutes"] == 30.0
        assert body["lenses"] == ["tail_risk"]
        assert body["running"] is False  # no handle / no DEEPSEEK_API_KEY
        again = await client.get("/api/settings/scheduler")
        assert again.json()["interval_minutes"] == 30.0

    @pytest.mark.asyncio
    async def test_put_scheduler_invalid_interval_400(self, client: AsyncClient) -> None:
        resp = await client.put("/api/settings/scheduler", json={"interval_minutes": 0})
        assert resp.status_code == 400
        resp2 = await client.put("/api/settings/scheduler", json={"interval_minutes": 99999})
        assert resp2.status_code == 400

    @pytest.mark.asyncio
    async def test_put_scheduler_empty_400(self, client: AsyncClient) -> None:
        resp = await client.put("/api/settings/scheduler", json={})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_put_scheduler_restarts_on_interval_change(self, client: AsyncClient) -> None:
        get_settings_store().update({
            "scheduler_enabled": True,
            "scheduler_interval_minutes": 30.0,
        })
        sched = _FakeScheduler(interval_minutes=30.0)
        sched.enabled = True
        init_settings(scheduler=sched)

        resp = await client.put("/api/settings/scheduler", json={"interval_minutes": 45.0})
        assert resp.status_code == 200
        assert sched.stops == 1
        assert sched.starts == 1
        assert sched.interval_minutes == 45.0
        assert resp.json()["running"] is True

    @pytest.mark.asyncio
    async def test_put_scheduler_same_interval_no_restart(self, client: AsyncClient) -> None:
        get_settings_store().update({
            "scheduler_enabled": True,
            "scheduler_interval_minutes": 30.0,
        })
        sched = _FakeScheduler(interval_minutes=30.0)
        sched.enabled = True
        init_settings(scheduler=sched)

        resp = await client.put("/api/settings/scheduler", json={"interval_minutes": 30.0})
        assert resp.status_code == 200
        assert sched.stops == 0
        assert sched.starts == 0

    @pytest.mark.asyncio
    async def test_put_scheduler_disable_stops_handle(self, client: AsyncClient) -> None:
        get_settings_store().update({
            "scheduler_enabled": True,
            "scheduler_interval_minutes": 30.0,
        })
        sched = _FakeScheduler(interval_minutes=30.0)
        sched.enabled = True
        init_settings(scheduler=sched)

        resp = await client.put("/api/settings/scheduler", json={"enabled": False})
        assert resp.status_code == 200
        assert sched.stops == 1
        assert sched.enabled is False
        assert settings_router_module._scheduler is None
        body = resp.json()
        assert body["enabled"] is False
        assert body["running"] is False

    @pytest.mark.asyncio
    async def test_put_scheduler_enable_starts_when_key_present(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        """Enabling a stopped scheduler spins one up when DEEPSEEK_API_KEY exists."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

        started: list[_FakeScheduler] = []

        def fake_build_orchestrator():
            return object()  # any non-None orchestrator

        def fake_start(sched) -> None:
            started.append(sched)

        with patch.object(settings_router_module, "build_orchestrator", fake_build_orchestrator):
            with patch.object(settings_router_module.ResearchScheduler, "start", fake_start):
                resp = await client.put("/api/settings/scheduler", json={"enabled": True})

        assert resp.status_code == 200
        assert started, "a scheduler should have been started"
        assert resp.json()["enabled"] is True

    @pytest.mark.asyncio
    async def test_put_scheduler_enable_without_key_does_not_start(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        resp = await client.put("/api/settings/scheduler", json={"enabled": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True  # intent persisted
        assert body["running"] is False  # but nothing started (no key)
        assert settings_router_module._scheduler is None
