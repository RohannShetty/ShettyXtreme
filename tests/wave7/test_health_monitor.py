"""Tests for TokenHealthMonitor (background health checks)."""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone, timedelta
from typing import Any

import pytest

from shettyxtreme.core.event_bus.event_bus import EventBus, Event, Topic
from shettyxtreme.auth.health_monitor import TokenHealthMonitor


class FakeCredentialStore:
    def __init__(self) -> None:
        self.access_token: str | None = None
        self.token_expiry: str | None = None


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def store() -> FakeCredentialStore:
    return FakeCredentialStore()


def _future_iso(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _past_iso(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _expiring_soon_iso(seconds: int = 1800) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


@pytest.mark.asyncio
async def test_check_health_publishes_event(bus: EventBus, store: FakeCredentialStore) -> None:
    store.access_token = "tok_abc"
    store.token_expiry = _future_iso(30)

    captured: list[Event] = []

    async def handler(event: Event) -> None:
        captured.append(event)

    bus.subscribe(Topic.CREDENTIAL_HEALTH_CHANGED, handler)

    monitor = TokenHealthMonitor(credential_store=store, event_bus=bus)
    await monitor._check_health()

    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    assert len(captured) == 1
    data = captured[0].data
    assert data["status"] == "HEALTHY"


@pytest.mark.asyncio
async def test_expired_token_status(bus: EventBus, store: FakeCredentialStore) -> None:
    store.access_token = "tok_abc"
    store.token_expiry = _past_iso(1)

    captured: list[Event] = []

    async def handler(event: Event) -> None:
        captured.append(event)

    bus.subscribe(Topic.CREDENTIAL_HEALTH_CHANGED, handler)

    monitor = TokenHealthMonitor(credential_store=store, event_bus=bus)
    await monitor._check_health()

    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    assert captured[0].data["status"] == "EXPIRED"


@pytest.mark.asyncio
async def test_expiring_soon_status(bus: EventBus, store: FakeCredentialStore) -> None:
    store.access_token = "tok_abc"
    store.token_expiry = _expiring_soon_iso(1800)

    captured: list[Event] = []

    async def handler(event: Event) -> None:
        captured.append(event)

    bus.subscribe(Topic.CREDENTIAL_HEALTH_CHANGED, handler)

    monitor = TokenHealthMonitor(credential_store=store, event_bus=bus)
    await monitor._check_health()

    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    assert captured[0].data["status"] == "EXPIRING_SOON"


@pytest.mark.asyncio
async def test_healthy_token_status(bus: EventBus, store: FakeCredentialStore) -> None:
    store.access_token = "tok_abc"
    store.token_expiry = _future_iso(30)

    captured: list[Event] = []

    async def handler(event: Event) -> None:
        captured.append(event)

    bus.subscribe(Topic.CREDENTIAL_HEALTH_CHANGED, handler)

    monitor = TokenHealthMonitor(credential_store=store, event_bus=bus)
    await monitor._check_health()

    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    assert captured[0].data["status"] == "HEALTHY"


@pytest.mark.asyncio
async def test_warning_event_on_status_change(bus: EventBus, store: FakeCredentialStore) -> None:
    store.access_token = "tok_abc"
    store.token_expiry = _future_iso(30)

    monitor = TokenHealthMonitor(credential_store=store, event_bus=bus)

    await monitor._check_health()
    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    store.token_expiry = _past_iso(1)

    warnings: list[Event] = []

    async def warning_handler(event: Event) -> None:
        warnings.append(event)

    bus.subscribe(Topic.CREDENTIAL_WARNING, warning_handler)
    await monitor._check_health()

    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    assert len(warnings) == 1
    assert "EXPIRED" in warnings[0].data.get("message", "")


@pytest.mark.asyncio
async def test_unknown_when_no_token(bus: EventBus, store: FakeCredentialStore) -> None:
    captured: list[Event] = []

    async def handler(event: Event) -> None:
        captured.append(event)

    bus.subscribe(Topic.CREDENTIAL_HEALTH_CHANGED, handler)

    monitor = TokenHealthMonitor(credential_store=store, event_bus=bus)
    await monitor._check_health()

    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    assert captured[0].data["status"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_monitor_cadence_defaults_to_60_seconds(
    bus: EventBus, store: FakeCredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: cadence must be 60s so Fyers' daily-expiring tokens are
    detected fast (a 300s sleep means up to 5 minutes of zombie trading)."""
    sleep_calls: list[float] = []
    original_sleep = asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        # Yield control so the monitor task can be scheduled/cancelled,
        # but never actually wait the real duration.
        await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    monitor = TokenHealthMonitor(credential_store=store, event_bus=bus)
    assert monitor._cadence_seconds == 60

    await monitor.start()

    for _ in range(50):
        await asyncio.sleep(0)
        if 60 in sleep_calls:
            break

    await monitor.stop()
    with contextlib.suppress(asyncio.CancelledError):
        await monitor._task

    assert 60 in sleep_calls, "monitor loop never slept with the 60s cadence"


# ── Pre-market liveness probe (Fyers daily tokens) ────────────────────────

from datetime import datetime as _dt  # noqa: E402
from zoneinfo import ZoneInfo as _ZoneInfo  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from shettyxtreme.auth.health_monitor import _IST, _TOKEN_EXPIRED_WARNING  # noqa: E402
from shettyxtreme.integration.fyers.client import FyersHTTPClient, FyersTokenExpired  # noqa: E402


class FakeFyersStore:
    app_id = "APP123"
    access_token = "tok_probe"
    token_expiry = "2099-01-01T00:00:00"


def _ist_time(hour: int, minute: int) -> _dt:
    return _dt(2026, 8, 4, hour, minute, tzinfo=_IST)


def _ok_profile() -> dict:
    return {"s": "ok", "data": {"name": "Rohan"}}


@pytest.mark.asyncio
async def test_premarket_probe_expired_token_publishes_warning(bus: EventBus) -> None:
    client = MagicMock(spec=FyersHTTPClient)
    client.get = AsyncMock(side_effect=FyersTokenExpired("HTTP 401"))

    monitor = TokenHealthMonitor(
        credential_store=FakeFyersStore(), event_bus=bus, http_client=client
    )

    warnings: list[Event] = []

    async def handler(event: Event) -> None:
        warnings.append(event)

    bus.subscribe(Topic.CREDENTIAL_WARNING, handler)

    await monitor._maybe_premarket_probe(now=_ist_time(8, 46))

    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    assert len(warnings) == 1
    assert _TOKEN_EXPIRED_WARNING in warnings[0].data.get("message", "")
    client.get.assert_awaited_once_with("/profile")


@pytest.mark.asyncio
async def test_premarket_probe_valid_token_no_warning(bus: EventBus) -> None:
    client = MagicMock(spec=FyersHTTPClient)
    client.get = AsyncMock(return_value=_ok_profile())

    monitor = TokenHealthMonitor(
        credential_store=FakeFyersStore(), event_bus=bus, http_client=client
    )

    warnings: list[Event] = []

    async def handler(event: Event) -> None:
        warnings.append(event)

    bus.subscribe(Topic.CREDENTIAL_WARNING, handler)

    await monitor._maybe_premarket_probe(now=_ist_time(8, 50))

    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    assert warnings == []


@pytest.mark.asyncio
async def test_premarket_probe_skips_outside_window(bus: EventBus) -> None:
    client = MagicMock(spec=FyersHTTPClient)
    client.get = AsyncMock(side_effect=FyersTokenExpired("HTTP 401"))

    monitor = TokenHealthMonitor(
        credential_store=FakeFyersStore(), event_bus=bus, http_client=client
    )

    warnings: list[Event] = []

    async def handler(event: Event) -> None:
        warnings.append(event)

    bus.subscribe(Topic.CREDENTIAL_WARNING, handler)

    await monitor._maybe_premarket_probe(now=_ist_time(10, 0))

    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    assert warnings == []
    client.get.assert_not_called()


@pytest.mark.asyncio
async def test_premarket_probe_runs_once_per_day(bus: EventBus) -> None:
    client = MagicMock(spec=FyersHTTPClient)
    client.get = AsyncMock(side_effect=FyersTokenExpired("HTTP 401"))

    monitor = TokenHealthMonitor(
        credential_store=FakeFyersStore(), event_bus=bus, http_client=client
    )

    warnings: list[Event] = []

    async def handler(event: Event) -> None:
        warnings.append(event)

    bus.subscribe(Topic.CREDENTIAL_WARNING, handler)

    await monitor._maybe_premarket_probe(now=_ist_time(8, 46))
    await monitor._maybe_premarket_probe(now=_ist_time(8, 51))

    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    assert len(warnings) == 1
    assert client.get.await_count == 1


# ── F-AUTH-001: probe must use the stored credentials ───────────────────────

@pytest.mark.asyncio
async def test_premarket_probe_uses_credentialed_client_when_available(
    bus: EventBus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-market liveness probe must probe WITH the stored credentials.

    Regression: ``TokenHealthMonitor.__init__`` defaulted ``_http_client`` to
    a credential-less ``FyersHTTPClient()``, so ``self._http_client or
    FyersHTTPClient(app_id, access_token)`` always picked the credential-less
    client — a false 'TOKEN EXPIRED' alarm fired every morning before market
    open even with valid credentials.
    """
    created: list[tuple[str, str | None]] = []

    class RecordingClient:
        def __init__(self, app_id: str = "", access_token: str | None = None) -> None:
            created.append((app_id, access_token))

        async def get(self, path: str) -> dict:
            return {"s": "ok"}

    monkeypatch.setattr("shettyxtreme.auth.health_monitor.FyersHTTPClient", RecordingClient)

    monitor = TokenHealthMonitor(credential_store=FakeFyersStore(), event_bus=bus)

    await monitor._maybe_premarket_probe(now=_ist_time(8, 46))

    assert created == [("APP123", "tok_probe")]


@pytest.mark.asyncio
async def test_premarket_probe_skips_when_no_token(
    bus: EventBus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a stored token the probe constructs no client and publishes
    no (false) expiry warning — the credential-less fallback path."""
    class NoTokenStore:
        app_id = "APP123"
        access_token = None

    built: list[tuple[str, str | None]] = []

    class RecordingClient:
        def __init__(self, app_id: str = "", access_token: str | None = None) -> None:
            built.append((app_id, access_token))

        async def get(self, path: str) -> dict:
            return {"s": "ok"}

    monkeypatch.setattr("shettyxtreme.auth.health_monitor.FyersHTTPClient", RecordingClient)

    warnings: list[Event] = []

    async def handler(event: Event) -> None:
        warnings.append(event)

    bus.subscribe(Topic.CREDENTIAL_WARNING, handler)

    monitor = TokenHealthMonitor(credential_store=NoTokenStore(), event_bus=bus)

    await monitor._maybe_premarket_probe(now=_ist_time(8, 46))

    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    assert built == []
    assert warnings == []
