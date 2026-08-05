"""Async background monitor for Fyers token health.

Checks credential health periodically and publishes events to the bus.
At 8:45 AM IST (pre-market) it additionally runs a live ``/profile`` probe
so a daily-expiring Fyers token is detected before the market opens.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.integration.fyers.client import FyersHTTPClient, FyersTokenExpired

logger = logging.getLogger(__name__)

_IST = ZoneInfo("Asia/Kolkata")
_PRE_MARKET_PROBE_HOUR = 8
_PRE_MARKET_PROBE_MINUTE = 45
_PRE_MARKET_WINDOW_MINUTES = 10
_TOKEN_EXPIRED_WARNING = "TOKEN EXPIRED — re-auth required"


class TokenHealthMonitor:

    def __init__(
        self,
        credential_store: CredentialStore,
        event_bus: EventBus,
        cadence_seconds: int = 60,
        http_client: FyersHTTPClient | None = None,
    ) -> None:
        self._credential_store = credential_store
        self._event_bus = event_bus
        self._cadence_seconds = cadence_seconds
        self._http_client = http_client or FyersHTTPClient()
        self._task: asyncio.Task | None = None
        self._running: bool = False
        self._last_premarket_probe: date | None = None

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
                await self._maybe_premarket_probe()
                await asyncio.sleep(self._cadence_seconds)
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

    async def _maybe_premarket_probe(self, now: datetime | None = None) -> None:
        """Live /profile probe once per day in the 8:45 AM IST window.

        A probe failure (401 / expired error code) means the daily token is
        dead before market open — publish the re-auth warning.
        """
        try:
            now_ist = (now or datetime.now(_IST)).astimezone(_IST)
            in_window = (
                now_ist.hour == _PRE_MARKET_PROBE_HOUR
                and _PRE_MARKET_PROBE_MINUTE
                <= now_ist.minute
                <= _PRE_MARKET_PROBE_MINUTE + _PRE_MARKET_WINDOW_MINUTES
            )
            if not in_window or self._last_premarket_probe == now_ist.date():
                return

            self._last_premarket_probe = now_ist.date()
            access_token = getattr(self._credential_store, "access_token", None)
            if not access_token:
                return

            app_id = getattr(self._credential_store, "app_id", "")
            client = self._http_client or FyersHTTPClient(
                app_id=app_id, access_token=access_token
            )
            try:
                data = await client.get("/profile")
                if isinstance(data, dict) and data.get("s") == "ok":
                    logger.info("Pre-market Fyers liveness probe: token valid")
                    return
            except FyersTokenExpired:
                pass  # definite expiry — warn below
            except Exception:
                logger.exception("Pre-market Fyers liveness probe failed (non-auth)")
                return

            logger.warning("Pre-market probe: Fyers token expired — re-auth required")
            await self._event_bus.publish(Event(
                Topic.CREDENTIAL_WARNING,
                {"message": _TOKEN_EXPIRED_WARNING},
                source="health_monitor",
            ))
        except Exception:
            logger.exception("Pre-market probe failed")

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
