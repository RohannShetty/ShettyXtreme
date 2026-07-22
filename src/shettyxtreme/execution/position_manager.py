"""Position management with the critical TP3 fix.

WAVE 5 (Execution + Position Management).

CRITICAL DESIGN RULE (ShettyBot V1 fix):
  _check_targets is called BEFORE _update_tsl in manage_position. This makes
  TP3 (and all TP levels) REACHABLE even when the trailing stop would also
  trigger at the same LTP. The position manager is NEVER blocked by the loss
  limit / risk engine — position management always runs.

TSL definition is canonical (premium-relative, vol-aware) and only moves in
the favourable direction (never widens).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from shettyxtreme.intelligence.signals.signal_engine import Signal
from shettyxtreme.intelligence.risk.cost_model import CostBreakdown, compute_cost


class Action(str, Enum):
    """Exit/hold actions produced by the position manager."""
    HOLD = "HOLD"
    EXIT_TP1 = "EXIT_TP1"
    EXIT_TP2 = "EXIT_TP2"
    EXIT_TP3 = "EXIT_TP3"
    EXIT_TSL = "EXIT_TSL"
    EXIT_EOD = "EXIT_EOD"


@dataclass
class ManagedPosition:
    """A position managed by PositionManager (local, unambiguous)."""
    symbol: str
    entry_price: float
    quantity: int
    direction: int  # +1 long, -1 short
    atr: float
    ltp: float
    tsl: float | None = None
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0


@dataclass
class PositionAction:
    """An action recommended by the position manager."""
    action: Action
    reason: str
    quantity: int
    price: float | None


_CONFIG_PATH = Path(__file__).resolve().parent.parent / "core" / "config" / "execution_config.yaml"


class PositionManager:
    """Manage exits: take-profit ladder (TP1/TP2/TP3) + trailing stop + EOD."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = dict(config or {})
        if not cfg and _CONFIG_PATH.exists():
            with open(_CONFIG_PATH) as f:
                loaded = yaml.safe_load(f) or {}
            tp = loaded.get("take_profit", {})
            ts = loaded.get("trailing_stop", {})
            cfg.setdefault("tp1_percent", tp.get("tp1_percent", 0.30))
            cfg.setdefault("tp2_percent", tp.get("tp2_percent", 0.60))
            cfg.setdefault("tp3_percent", tp.get("tp3_percent", 1.00))
            cfg.setdefault("tsl_atr_multiplier", ts.get("atr_multiplier", 1.5))
            cfg.setdefault("min_profit_to_activate", ts.get("min_profit_to_activate", 0.15))
            cfg.setdefault("eod_exit_time", loaded.get("eod_exit_time", "15:15"))

        self.tp1_percent: float = float(cfg.get("tp1_percent", 0.30))
        self.tp2_percent: float = float(cfg.get("tp2_percent", 0.60))
        self.tp3_percent: float = float(cfg.get("tp3_percent", 1.00))
        self.tsl_atr_multiplier: float = float(cfg.get("tsl_atr_multiplier", 1.5))
        self.min_profit_to_activate: float = float(cfg.get("min_profit_to_activate", 0.15))
        self.eod_exit_time: str = str(cfg.get("eod_exit_time", "15:15"))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def manage_position(
        self, position: ManagedPosition, signal: Signal | None = None
    ) -> PositionAction:
        # 1. FIRST check if any TP target is hit
        tp_hit = self._check_targets(position)
        if tp_hit is not None:
            return tp_hit  # Exit at TP target — BEFORE _update_tsl (TP3 reachable)

        # 2. THEN update trailing stop loss
        self._update_tsl(position)

        # 3. Check if TSL is hit
        if self._is_tsl_hit(position):
            return PositionAction(
                action=Action.EXIT_TSL,
                reason="trailing stop hit",
                quantity=position.quantity,
                price=position.tsl,
            )

        # 4. Check EOD
        if self._is_eod():
            return PositionAction(
                action=Action.EXIT_EOD,
                reason="end of day",
                quantity=position.quantity,
                price=position.ltp,
            )

        return PositionAction(
            action=Action.HOLD,
            reason="no target hit",
            quantity=position.quantity,
            price=None,
        )

    # ------------------------------------------------------------------
    # TP levels
    # ------------------------------------------------------------------
    def _compute_tp_levels(self, entry_price: float, direction: int) -> tuple[float, float, float]:
        if direction > 0:
            tp1 = entry_price * (1.0 + self.tp1_percent)
            tp2 = entry_price * (1.0 + self.tp2_percent)
            tp3 = entry_price * (1.0 + self.tp3_percent)
        else:
            tp1 = entry_price * (1.0 - self.tp1_percent)
            tp2 = entry_price * (1.0 - self.tp2_percent)
            tp3 = entry_price * (1.0 - self.tp3_percent)
        return (tp1, tp2, tp3)

    def _apply_tp_levels(self, position: ManagedPosition) -> None:
        position.tp1, position.tp2, position.tp3 = self._compute_tp_levels(
            position.entry_price, position.direction
        )

    # ------------------------------------------------------------------
    # Target check (called BEFORE TSL)
    # ------------------------------------------------------------------
    def _check_targets(self, position: ManagedPosition) -> PositionAction | None:
        self._apply_tp_levels(position)
        ltp = position.ltp
        if position.direction > 0:
            if ltp >= position.tp3:
                return self._tp_action(Action.EXIT_TP3, position.tp3, position)
            if ltp >= position.tp2:
                return self._tp_action(Action.EXIT_TP2, position.tp2, position)
            if ltp >= position.tp1:
                return self._tp_action(Action.EXIT_TP1, position.tp1, position)
        else:
            if ltp <= position.tp3:
                return self._tp_action(Action.EXIT_TP3, position.tp3, position)
            if ltp <= position.tp2:
                return self._tp_action(Action.EXIT_TP2, position.tp2, position)
            if ltp <= position.tp1:
                return self._tp_action(Action.EXIT_TP1, position.tp1, position)
        return None

    def _tp_action(self, action: Action, price: float, position: ManagedPosition) -> PositionAction:
        return PositionAction(
            action=action,
            reason=f"{action.value} hit at {price:.2f}",
            quantity=position.quantity,
            price=price,
        )

    # ------------------------------------------------------------------
    # Trailing stop (canonical, favourable-only)
    # ------------------------------------------------------------------
    def _update_tsl(self, position: ManagedPosition) -> None:
        # Only activate after min profit reached
        if position.direction > 0:
            profit = position.ltp - position.entry_price
        else:
            profit = position.entry_price - position.ltp
        min_profit = position.entry_price * self.min_profit_to_activate
        if profit < min_profit:
            return

        if position.direction > 0:
            candidate = position.ltp - (position.atr * self.tsl_atr_multiplier)
        else:
            candidate = position.ltp + (position.atr * self.tsl_atr_multiplier)

        if position.direction > 0:
            if position.tsl is None or candidate > position.tsl:
                position.tsl = candidate
        else:
            if position.tsl is None or candidate < position.tsl:
                position.tsl = candidate

    def _is_tsl_hit(self, position: ManagedPosition) -> bool:
        if position.tsl is None:
            return False
        if position.direction > 0:
            return position.ltp <= position.tsl
        return position.ltp >= position.tsl

    # ------------------------------------------------------------------
    # EOD
    # ------------------------------------------------------------------
    def _is_eod(self, now: datetime | None = None) -> bool:
        ref = now or datetime.now(timezone.utc)
        hour, minute = (ref.hour, ref.minute)
        try:
            eh, em = int(self.eod_exit_time.split(":")[0]), int(self.eod_exit_time.split(":")[1])
        except (ValueError, IndexError):
            eh, em = 15, 15
        return (hour, minute) > (eh, em)

    # ------------------------------------------------------------------
    # Cost helper (unused by core flow but available to callers)
    # ------------------------------------------------------------------
    def estimate_exit_cost(self, position: ManagedPosition) -> CostBreakdown:
        return compute_cost(quantity=position.quantity, price=position.ltp)
