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
from typing import Any, Protocol
from uuid import uuid4

from shettyxtreme.core.data_models import OrderType, ProductType
from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.execution.execution_engine import ApprovalStatus, ExecutionEngine
from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection

logger = logging.getLogger(__name__)

#: Engine symbol label; matches IntelligencePipeline._PIPELINE_SYMBOL.
_PIPELINE_SYMBOL = "NIFTY"
_DEFAULT_LOTS = 1


class _LotSizeProvider(Protocol):
    """Minimal interface for lot-size lookup (FyersInstrumentMaster)."""
    def get_lot_size(
        self, internal_symbol: str, exchange: str = "NSE",
        instrument_type: str = "INDEX",
    ) -> int | None: ...


def _resolve_lot_size(
    master: _LotSizeProvider | None, symbol: str,
) -> int | None:
    """Look up lot_size from instrument_master; None when unavailable."""
    if master is None:
        return None
    try:
        return master.get_lot_size(symbol)
    except Exception:
        logger.debug("lot_size lookup failed for %s", symbol, exc_info=True)
        return None


def make_default_hint_builder(
    instrument_master: _LotSizeProvider | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Build a default hint builder that resolves lot_size from master.

    Returns 1 lot by default when lot_size is known; falls back to
    ``quantity=None`` when master is unavailable (caller must handle).
    """

    def _builder(data: dict[str, Any]) -> dict[str, Any]:
        lot_size = _resolve_lot_size(instrument_master, _PIPELINE_SYMBOL)
        quantity: int | None = None
        if lot_size is not None and lot_size > 0:
            quantity = lot_size * _DEFAULT_LOTS
        return {
            "symbol": _PIPELINE_SYMBOL,
            "exchange": "NFO",
            "quantity": quantity,
            "lot_size": lot_size,
            "lots": _DEFAULT_LOTS,
            "price": None,
            "order_type": OrderType.MARKET,
            "product": ProductType.MIS,
            "tag": "signal-v2",
            "hint_kind": "default",
            "strategy": "stand_aside",
            "underlying": _PIPELINE_SYMBOL,
        }

    return _builder


# Backward-compatible default (no master → quantity=None).
default_hint_builder: Callable[[dict[str, Any]], dict[str, Any]] = (
    make_default_hint_builder(None)
)


def make_chain_hint_builder(
    instrument_master: _LotSizeProvider | None = None,
    chain_provider: Callable[[str], list[dict[str, Any]]] | None = None,
    spot_provider: Callable[[str], float | None] | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
    """Build a chain-aware hint builder using StrategyHints.

    This builder:
    - Looks up lot_size from instrument_master.
    - Fetches option chain and spot price via injected providers.
    - Uses StrategyHints to pick strike/premium/EV.
    - Rounds quantity to lot multiples.
    - Returns a full hint dict with leg fields (strike, expiry, option_type,
      lot_size, qty, stop_loss, target, rationale, hint_kind="chain").

    Falls back to ``None`` (proposal skipped) when chain data or lot_size
    is unavailable.
    """
    from shettyxtreme.intelligence.hints.strategy_hints import StrategyHints

    def _builder(data: dict[str, Any]) -> dict[str, Any] | None:
        symbol = str(data.get("underlying", _PIPELINE_SYMBOL))
        lot_size = _resolve_lot_size(instrument_master, symbol)

        # Fetch chain + spot.
        chain: list[dict[str, Any]] = []
        spot: float | None = None
        if chain_provider is not None:
            try:
                chain = chain_provider(symbol)
            except Exception:
                logger.debug("chain fetch failed for %s", symbol, exc_info=True)
        if spot_provider is not None:
            try:
                spot = spot_provider(symbol)
            except Exception:
                logger.debug("spot fetch failed for %s", symbol, exc_info=True)

        hint_gen = StrategyHints(
            signal=data,
            chain=chain,
            current_price=spot,
            lot_size=lot_size,
        )
        hint = hint_gen.generate()

        # If StrategyHints produced no actionable hint (NEUTRAL / low
        # conviction), return None so the bridge skips it.
        if hint.direction == "neutral":
            return None

        quantity = hint.quantity
        if quantity is None or quantity <= 0:
            if lot_size is not None and lot_size > 0:
                quantity = lot_size  # 1 lot fallback
            else:
                logger.warning("chain hint: no lot_size for %s — skipping", symbol)
                return None

        return {
            "symbol": symbol,
            "exchange": str(data.get("exchange", "NFO")),
            "quantity": quantity,
            "lot_size": lot_size,
            "lots": (quantity // lot_size) if lot_size else 1,
            "price": hint.premium,
            "order_type": OrderType.LIMIT if hint.premium else OrderType.MARKET,
            "product": ProductType.MIS,
            "tag": "signal-v2",
            "hint_kind": "chain",
            "strike": hint.strike,
            "expiry": hint.leg.expiry if hint.leg else None,
            "option_type": hint.leg.option_type if hint.leg else None,
            "stop_loss": hint.stop_loss,
            "target": hint.target,
            "rationale": hint.rationale,
            "confidence": hint.confidence,
            "ev_after_cost": hint.ev_after_cost,
            # P3-4.3: strategy + underlying for the enriched proposal payload.
            "strategy": hint.strategy,
            "underlying": symbol,
        }

    return _builder


class ExecutionSignalBridge:
    """Bridges SIGNAL_V2 events into ExecutionEngine proposals."""

    def __init__(
        self,
        engine: ExecutionEngine,
        event_bus: EventBus,
        hint_builder: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
        instrument_master: _LotSizeProvider | None = None,
    ) -> None:
        self._engine = engine
        self._event_bus = event_bus
        if hint_builder is not None:
            self._hint_builder = hint_builder
        else:
            self._hint_builder = make_default_hint_builder(instrument_master)
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
