"""Async background monitor for Dhan API token health.

Checks credential health periodically and publishes events to the bus.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.core.event_bus.event_bus import EventBus, Event, Topic


class TokenHealthMonitor:
    """Periodically checks credential health and publishes status events."""

    def __init__(self, credential_store: CredentialStore, event_bus: EventBus) -> None:
        self._credential_store = credential_store
        self._event_bus = event_bus
        self._task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self) -> None:
        """Start the background monitoring loop."""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the background monitoring loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()

    async def _monitor_loop(self) -> None:
        """Main loop: check health every 5 minutes."""
        try:
            while self._running:
                await self._check_health()
                await asyncio.sleep(300)
        except asyncio.CancelledError:
            pass

    async def _check_health(self) -> None:
        """Check both trading and data credential health, publish events."""
        try:
            trading_expiry = getattr(self._credential_store, "trading_token_expiry", None)
            data_expiry = getattr(self._credential_store, "data_token_expiry", None)

            trading_status, trading_days = self._get_status(trading_expiry, 3600)
            data_status, data_days = self._get_status(data_expiry, 259200)

            health_data = {
                "trading_status": trading_status,
                "data_status": data_status,
                "trading_expiry": trading_expiry,
                "data_expiry": data_expiry,
                "trading_days_to_expiry": trading_days,
                "data_days_to_expiry": data_days,
            }

            await self._event_bus.publish(Event(Topic.CREDENTIAL_HEALTH_CHANGED, health_data, source="health_monitor"))

            for status in (trading_status, data_status):
                if status in ("EXPIRED", "EXPIRING_SOON"):
                    await self._event_bus.publish(Event(
                        Topic.CREDENTIAL_WARNING,
                        {"message": f"Credential status changed to {status}", "trading_status": trading_status, "data_status": data_status},
                        source="health_monitor",
                    ))
                    break
        except Exception:
            logger.exception("Health check failed")

    def _get_status(self, token_expiry: str | None, warning_threshold_seconds: int) -> tuple[str, float | None]:
        """Return (status_string, days_to_expiry) for a token expiry timestamp."""
        if token_expiry is None:
            return ("UNKNOWN", None)

        try:
            expiry_dt = datetime.fromisoformat(token_expiry)
        except (ValueError, TypeError):
            return ("UNKNOWN", None)

        now = datetime.now(timezone.utc)
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)

        delta = expiry_dt - now
        days_to_expiry = delta.total_seconds() / 86400

        if delta.total_seconds() <= 0:
            return ("EXPIRED", days_to_expiry)
        if delta.total_seconds() <= warning_threshold_seconds:
            return ("EXPIRING_SOON", days_to_expiry)
        return ("HEALTHY", days_to_expiry)
