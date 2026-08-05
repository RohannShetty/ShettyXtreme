"""EventBus bridge: SIGNAL_V2 -> ExecutionEngine proposals (OBSERVER flow).

The ExecutionSignalBridge converts live SIGNAL_V2 events (P4a pipeline) into
PENDING proposals on the ExecutionEngine, so in OBSERVER (and any) mode the
human always approves before anything is placed (D10). It follows the
start/stop subscribe pattern of RegimeBusBridge / RiskBusBridge.

Rules:
  - NEUTRAL signals never become proposals.
  - A proposal is only created when no PENDING proposal already exists for
    the same symbol + side (signals re-fire on every features-computed tick;
    this dedupes without a clock).
  - The order context (symbol/exchange/quantity/price/product) comes from an
    injectable hint builder; the default is a deterministic minimal structure
    for the pipeline symbol. Plug a StrategyHints-based builder when chain
    data is available.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from shettyxtreme.core.data_models import OrderType, ProductType
from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.execution.execution_engine import ApprovalStatus, ExecutionEngine
from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection

logger = logging.getLogger(__name__)

#: Engine symbol label; matches IntelligencePipeline._PIPELINE_SYMBOL.
_PIPELINE_SYMBOL = "NIFTY"
_DEFAULT_QUANTITY = 75


def default_hint_builder(data: dict[str, Any]) -> dict[str, Any]:
    """Deterministic minimal order context for a proposal.

    Override by passing a custom builder to ExecutionSignalBridge when a
    strategy-hint (chain-aware) structure is desired.
    """
    return {
        "symbol": _PIPELINE_SYMBOL,
        "exchange": "NFO",
        "quantity": _DEFAULT_QUANTITY,
        "price": None,
        "order_type": OrderType.MARKET,
        "product": ProductType.MIS,
        "tag": "signal-v2",
        "hint_kind": "default",
    }


class ExecutionSignalBridge:
    """Bridges SIGNAL_V2 events into ExecutionEngine proposals."""

    def __init__(
        self,
        engine: ExecutionEngine,
        event_bus: EventBus,
        hint_builder: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> None:
        self._engine = engine
        self._event_bus = event_bus
        self._hint_builder = hint_builder or default_hint_builder
        self._subscribed = False

    async def start(self) -> None:
        if self._subscribed:
            return
        self._event_bus.subscribe(Topic.SIGNAL_V2, self._on_signal_v2)
        self._subscribed = True
        logger.info("ExecutionSignalBridge started (SIGNAL_V2 -> proposals)")

    async def stop(self) -> None:
        if not self._subscribed:
            return
        self._event_bus.unsubscribe(Topic.SIGNAL_V2, self._on_signal_v2)
        self._subscribed = False
        logger.info("ExecutionSignalBridge stopped")

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------
    async def _on_signal_v2(self, event: Event) -> None:
        d = event.data
        values = getattr(d, "__dict__", d) if not isinstance(d, dict) else d
        if not values:
            return
        direction = str(values.get("direction", "NEUTRAL")).upper()
        if direction == "NEUTRAL":
            return
        if direction not in ("UP", "DOWN"):
            logger.warning("ExecutionSignalBridge: unknown direction %r", direction)
            return

        signal = Signal(
            direction=SignalDirection[direction],
            conviction=self._to_float(values.get("conviction"), 0.0),
            voters=[],
            timestamp=self._to_dt(values.get("timestamp")),
            D=self._to_float(values.get("D"), 0.0),
            P=self._to_float(values.get("P"), 1.0),
            G=str(values.get("G", "contested")),
        )
        hint = self._hint_builder(values)
        if not hint:
            return
        side = "BUY" if direction == "UP" else "SELL"
        symbol = str(hint.get("symbol", ""))
        if self._has_pending(side, symbol):
            logger.debug(
                "proposal skipped: PENDING %s %s already queued", side, symbol
            )
            return
        self._engine.submit_signal(signal, hint, signal_id=uuid4().hex)
        logger.info("proposal queued: %s %s qty=%s (conviction=%.2f)", side, symbol, hint.get("quantity"), signal.conviction)

    def _has_pending(self, side: str, symbol: str) -> bool:
        for approval in self._engine.get_all_approvals():
            if approval.status != ApprovalStatus.PENDING.value:
                continue
            hint_symbol = str(approval.strategy_hint.get("symbol", ""))
            direction = str(approval.signal.direction.name).upper()
            approval_side = "BUY" if direction == "UP" else "SELL"
            if hint_symbol == symbol and approval_side == side:
                return True
        return False

    # ------------------------------------------------------------------
    # Coercion helpers (never raise on junk payloads)
    # ------------------------------------------------------------------
    @staticmethod
    def _to_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_dt(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.now(UTC)
