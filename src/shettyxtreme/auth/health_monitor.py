"""Async background monitor for Dhan API token health.

Checks credential health periodically and publishes events to the bus.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic

logger = logging.getLogger(__name__)


class TokenHealthMonitor:

    def __init__(self, credential_store: CredentialStore, event_bus: EventBus) -> None:
        self._credential_store = credential_store
        self._event_bus = event_bus
        self._task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()

    async def _monitor_loop(self) -> None:
        try:
            while self._running:
                await self._check_health()
                await asyncio.sleep(300)
        except asyncio.CancelledError:
            pass

    async def _check_health(self) -> None:
        try:
            token_expiry = getattr(self._credential_store, "token_expiry", None)

            status, days = self._get_status(token_expiry)

            health_data = {
                "status": status,
                "expiry": token_expiry,
                "days_to_expiry": days,
            }

            await self._event_bus.publish(Event(Topic.CREDENTIAL_HEALTH_CHANGED, health_data, source="health_monitor"))

            if status in ("EXPIRED", "EXPIRING_SOON"):
                await self._event_bus.publish(Event(
                    Topic.CREDENTIAL_WARNING,
                    {"message": f"Credential status changed to {status}"},
                    source="health_monitor",
                ))
        except Exception:
            logger.exception("Health check failed")

    def _get_status(self, token_expiry: str | None) -> tuple[str, float | None]:
        if token_expiry is None:
            return ("UNKNOWN", None)

        try:
            expiry_dt = datetime.fromisoformat(token_expiry)
        except (ValueError, TypeError):
            return ("UNKNOWN", None)

        now = datetime.now(UTC)
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=UTC)

        delta = expiry_dt - now
        days_to_expiry = delta.total_seconds() / 86400

        if delta.total_seconds() <= 0:
            return ("EXPIRED", days_to_expiry)
        if delta.total_seconds() <= 3600:
            return ("EXPIRING_SOON", days_to_expiry)
        return ("HEALTHY", days_to_expiry)
