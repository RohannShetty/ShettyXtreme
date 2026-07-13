"""Tests for TokenHealthMonitor (background health checks)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any

import pytest

from shettyxtreme.core.event_bus.event_bus import EventBus, Event, Topic
from shettyxtreme.auth.health_monitor import TokenHealthMonitor


class FakeCredentialStore:
    """In-memory credential store for testing."""

    def __init__(self) -> None:
        self.trading_access_token: str | None = None
        self.trading_token_expiry: str | None = None
        self.data_access_token: str | None = None
        self.data_token_expiry: str | None = None


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
    """Valid token → CREDENTIAL_HEALTH_CHANGED published with HEALTHY."""
    store.trading_access_token = "tok_abc"
    store.trading_token_expiry = _future_iso(30)
    store.data_access_token = "tok_data"
    store.data_token_expiry = _future_iso(30)

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
    assert data["trading_status"] == "HEALTHY"
    assert data["data_status"] == "HEALTHY"


@pytest.mark.asyncio
async def test_expired_token_status(bus: EventBus, store: FakeCredentialStore) -> None:
    """Expired trading token → EXPIRED."""
    store.trading_access_token = "tok_abc"
    store.trading_token_expiry = _past_iso(1)
    store.data_access_token = "tok_data"
    store.data_token_expiry = _future_iso(30)

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

    assert captured[0].data["trading_status"] == "EXPIRED"


@pytest.mark.asyncio
async def test_expiring_soon_status(bus: EventBus, store: FakeCredentialStore) -> None:
    """Trading token within 1 hour → EXPIRING_SOON."""
    store.trading_access_token = "tok_abc"
    store.trading_token_expiry = _expiring_soon_iso(1800)
    store.data_access_token = "tok_data"
    store.data_token_expiry = _future_iso(30)

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

    assert captured[0].data["trading_status"] == "EXPIRING_SOON"


@pytest.mark.asyncio
async def test_healthy_token_status(bus: EventBus, store: FakeCredentialStore) -> None:
    """Far-future token → HEALTHY."""
    store.trading_access_token = "tok_abc"
    store.trading_token_expiry = _future_iso(30)
    store.data_access_token = "tok_data"
    store.data_token_expiry = _future_iso(30)

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

    assert captured[0].data["trading_status"] == "HEALTHY"


@pytest.mark.asyncio
async def test_warning_event_on_status_change(bus: EventBus, store: FakeCredentialStore) -> None:
    """Healthy → expired transition publishes CREDENTIAL_WARNING."""
    store.trading_access_token = "tok_abc"
    store.trading_token_expiry = _future_iso(30)
    store.data_access_token = "tok_data"
    store.data_token_expiry = _future_iso(30)

    monitor = TokenHealthMonitor(credential_store=store, event_bus=bus)

    # First check: HEALTHY
    await monitor._check_health()
    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0.05)
    await bus.stop()
    await task

    # Transition to expired
    store.trading_token_expiry = _past_iso(1)

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
    """No token set → status UNKNOWN."""
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

    assert captured[0].data["trading_status"] == "UNKNOWN"
    assert captured[0].data["data_status"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_data_token_threshold_3_days(bus: EventBus, store: FakeCredentialStore) -> None:
    """Data token within 3 days → EXPIRING_SOON (data threshold is 259200s)."""
    store.trading_access_token = "tok_abc"
    store.trading_token_expiry = _future_iso(30)
    store.data_access_token = "tok_data"
    store.data_token_expiry = _expiring_soon_iso(200000)  # ~2.3 days

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

    assert captured[0].data["data_status"] == "EXPIRING_SOON"
    assert captured[0].data["trading_status"] == "HEALTHY"
