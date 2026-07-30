"""EventBus bridge for risk metrics — publishes RISK_DECISION on position/market updates."""
from __future__ import annotations

import logging

from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic

logger = logging.getLogger(__name__)

_DEFAULT_LOSS_LIMIT = -5000.0
_MAX_POSITIONS = 5


class RiskBusBridge:
    """Bridges risk metrics to the EventBus.

    Maintains in-memory PnL and margin state, publishing RISK_DECISION
    whenever positions or market ticks update.
    """

    def __init__(
        self,
        event_bus: EventBus,
        loss_limit: float = _DEFAULT_LOSS_LIMIT,
    ) -> None:
        self._event_bus = event_bus
        self._daily_pnl = 0.0
        self._margin_used = 0.0
        self._margin_available = 0.0
        self._loss_limit = loss_limit

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
        decision = {
            "daily_pnl": self._daily_pnl,
            "margin_used": self._margin_used,
            "margin_available": self._margin_available,
            "loss_limit": self._loss_limit,
            "loss_limit_hit": self._daily_pnl < self._loss_limit,
            "max_positions": _MAX_POSITIONS,
        }
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
