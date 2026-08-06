"""EventBus bridge for risk metrics — publishes RISK_DECISION on position/market updates."""
from __future__ import annotations

import logging

from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.core.settings import get_settings_store

logger = logging.getLogger(__name__)


class RiskBusBridge:
    """Bridges risk metrics to the EventBus.

    Maintains in-memory PnL and margin state, publishing RISK_DECISION
    whenever positions or market ticks update. The loss limit and max
    positions caps are read live from the shared settings store, so the
    payload always reflects the operator's current settings.
    """

    def __init__(
        self,
        event_bus: EventBus,
        loss_limit: float | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._daily_pnl = 0.0
        self._margin_used = 0.0
        # Margin starts UNKNOWN (None). Ticks/position updates carry no margin,
        # so publishing any placeholder here would clobber the real value the
        # margin poller publishes via RISK_DECISION (fix #2 honesty rule).
        self._margin_available: float | None = None
        # Kept for the startup log; the decision payload reads the live store.
        self._loss_limit = (
            loss_limit if loss_limit is not None else get_settings_store().loss_limit()
        )

    async def start(self) -> None:
        self._event_bus.subscribe(Topic.POSITION_CHANGED, self._on_position)
        self._event_bus.subscribe(Topic.MARKET_DATA_TICK, self._on_tick)
        logger.info("RiskBusBridge started (loss_limit=%.0f)", self._loss_limit)

    async def stop(self) -> None:
        self._event_bus.unsubscribe(Topic.POSITION_CHANGED, self._on_position)
        self._event_bus.unsubscribe(Topic.MARKET_DATA_TICK, self._on_tick)
        logger.info("RiskBusBridge stopped")

    async def _on_position(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {}
        self._daily_pnl = data.get("daily_pnl", self._daily_pnl)
        self._margin_used = data.get("margin_used", self._margin_used)
        await self._publish_decision()

    async def _on_tick(self, event: Event) -> None:
        data = event.data if isinstance(event.data, dict) else {}
        if "margin_available" in data:
            self._margin_available = data["margin_available"]
        await self._publish_decision()

    async def _publish_decision(self) -> None:
        # Read the caps live from the settings store so a runtime change
        # (via /api/settings) is reflected in the very next decision instead
        # of regressing the projection to a stale value (P7-W3).
        loss_limit = get_settings_store().loss_limit()
        decision = {
            "daily_pnl": self._daily_pnl,
            "margin_used": self._margin_used,
            "loss_limit": loss_limit,
            "loss_limit_hit": self._daily_pnl < loss_limit,
            "max_positions": get_settings_store().max_positions(),
        }
        # Only carry margin when a real source reported it (fix #2). Omitting
        # the key lets consumers keep the poller's last real value instead of
        # being overwritten by an unknown/placeholder figure.
        if self._margin_available is not None:
            decision["margin_available"] = self._margin_available
        await self._event_bus.publish(
            Event(
                topic=Topic.RISK_DECISION,
                data=decision,
                source="risk_bus_bridge",
            )
        )
        logger.debug(
            "Risk decision: pnl=%.2f, loss_limit_hit=%s",
            self._daily_pnl,
            decision["loss_limit_hit"],
        )
