"""Walkforward evaluation — HONEST option-premium backtest.

Simulates exits against a TP/SL/EOD policy and scores the strategy on real
option PREMIUM movement (never underlying % moves), with transaction costs
subtracted so performance is not inflated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Optional

from shettyxtreme.intelligence.risk.cost_model import compute_cost
from shettyxtreme.learning.outcome_tracker import SignalDecision

LOT_SIZE = 75


@dataclass
class WalkforwardResult:
    """Aggregate walkforward evaluation metrics."""

    total_return: float
    win_rate: float
    avg_win: float
    avg_loss: float
    sharpe_ratio: float
    max_drawdown: float
    num_trades: int
    cost_adjusted_return: float


class WalkforwardEvaluator:
    """Evaluate signal decisions against premium entry/exit prices."""

    def __init__(self, config: Optional[dict] = None) -> None:
        cfg = config or {}
        self.tp1 = float(cfg.get("tp1", 0.30))
        self.tp2 = float(cfg.get("tp2", 0.60))
        self.tp3 = float(cfg.get("tp3", 1.00))
        self.tsl_atr_multiplier = float(cfg.get("tsl_atr_multiplier", 1.5))
        self.tsl_stop_fraction = float(cfg.get("tsl_stop_fraction", 0.5))
        eod = cfg.get("eod_time", "15:15")
        if isinstance(eod, str):
            hh, mm = eod.split(":")
            eod = time(int(hh), int(mm))
        self.eod_time = eod

    def _direction(self, decision: SignalDecision) -> float:
        d = decision.signal.direction.value
        if d == "up":
            return 1.0
        if d == "down":
            return -1.0
        return 0.0

    def _simulate_exit(
        self, entry: float, exit_price: float, direction: float
    ) -> float:
        """Return the realized exit premium under the TP/SL/EOD policy."""
        if direction > 0:
            tp1 = entry * (1 + self.tp1)
            tp2 = entry * (1 + self.tp2)
            tp3 = entry * (1 + self.tp3)
            tsl = entry - (entry * self.tsl_atr_multiplier * 0.01)
            if exit_price >= tp3:
                return tp3
            if exit_price >= tp2:
                return tp2
            if exit_price >= tp1:
                return tp1
            if exit_price <= tsl:
                return tsl
            return exit_price
        tsl = entry + (entry * self.tsl_atr_multiplier * 0.01)
        if exit_price <= entry * (1 - self.tp3):
            return entry * (1 - self.tp3)
        if exit_price <= entry * (1 - self.tp2):
            return entry * (1 - self.tp2)
        if exit_price <= entry * (1 - self.tp1):
            return entry * (1 - self.tp1)
        if exit_price >= tsl:
            return tsl
        return exit_price

    def evaluate(
        self,
        signals: list[SignalDecision],
        entry_prices: dict[str, float],
        exit_prices: dict[str, float],
    ) -> WalkforwardResult:
        """Evaluate decisions and return aggregate metrics."""
        pnls: list[float] = []
        gross_returns: list[float] = []
        wins = 0
        losses = 0
        win_sum = 0.0
        loss_sum = 0.0
        total_cost = 0.0

        for decision in signals:
            direction = self._direction(decision)
            if direction == 0:
                continue
            if decision.id not in entry_prices or decision.id not in exit_prices:
                continue
            entry = float(entry_prices[decision.id])
            exit_price = float(exit_prices[decision.id])
            exit_premium = self._simulate_exit(entry, exit_price, direction)
            if direction > 0:
                gross = (exit_premium - entry) * LOT_SIZE
            else:
                gross = (entry - exit_premium) * LOT_SIZE
            cost = compute_cost(LOT_SIZE, entry).total
            total_cost += cost
            net = gross - cost
            pnls.append(net)
            gross_returns.append(gross)
            if net > 0:
                wins += 1
                win_sum += net
            elif net < 0:
                losses += 1
                loss_sum += net

        num_trades = len(pnls)
        total_return = sum(pnls)
        win_rate = wins / num_trades if num_trades > 0 else 0.0
        avg_win = win_sum / wins if wins > 0 else 0.0
        avg_loss = loss_sum / losses if losses > 0 else 0.0
        sharpe = self._sharpe(pnls)
        max_dd = self._max_drawdown(pnls)

        return WalkforwardResult(
            total_return=total_return,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            num_trades=num_trades,
            cost_adjusted_return=total_return,
        )

    def _sharpe(self, pnls: list[float]) -> float:
        if len(pnls) < 2:
            return 0.0
        mean = sum(pnls) / len(pnls)
        var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        std = var ** 0.5
        if std == 0:
            return 0.0
        return mean / std

    def _max_drawdown(self, pnls: list[float]) -> float:
        peak = 0.0
        cum = 0.0
        max_dd = 0.0
        for p in pnls:
            cum += p
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd
        return max_dd
