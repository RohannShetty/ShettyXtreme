"""Backtest engine — event-driven backtesting via IAF adapter.

Replaces the static walkforward evaluator with an event-driven backtest
engine. First consumer of the BacktestEngine Protocol (FR-005).

OutcomeTracker/analytics/shadow_loop stay as-is — this module provides
the backtest API that feeds BacktestReport for the comparison dashboard.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from shettyxtreme.core.interfaces.backtest_engine import (
    BacktestConfig,
    BacktestEngine,
    BacktestReport,
)
from shettyxtreme.learning.outcome_tracker import OutcomeTracker, SignalDecision

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Wrapper around BacktestReport with convenience accessors."""

    report: BacktestReport

    @property
    def total_return(self) -> float:
        return self.report.metrics.total_return

    @property
    def win_rate(self) -> float:
        return self.report.metrics.win_rate

    @property
    def sharpe_ratio(self) -> float:
        return self.report.metrics.sharpe_ratio

    @property
    def sortino_ratio(self) -> float:
        return self.report.metrics.sortino_ratio

    @property
    def max_drawdown(self) -> float:
        return self.report.metrics.max_drawdown

    @property
    def total_trades(self) -> int:
        return self.report.metrics.total_trades

    @property
    def profit_factor(self) -> float:
        return self.report.metrics.profit_factor

    @property
    def net_return(self) -> float:
        return self.report.metrics.net_return


class BacktestRunner:
    """Run backtests via the BacktestEngine adapter.

    Consumes SignalDecision records from OutcomeTracker, historical bars
    from market data, and produces BacktestReport.
    """

    def __init__(self, engine: BacktestEngine) -> None:
        self._engine = engine

    def run(
        self,
        config: BacktestConfig,
        decisions: list[SignalDecision],
        market_data: list[dict],
    ) -> BacktestResult:
        """Run a backtest with the given config.

        Args:
            config: Backtest configuration.
            decisions: Signal decisions from OutcomeTracker.
            market_data: Historical bar data (symbol, timestamp, OHLCV).

        Returns:
            BacktestResult wrapping BacktestReport.
        """
        # Convert SignalDecision → signal dicts for the adapter
        signals = self._decisions_to_signals(decisions)

        # Run backtest via engine
        report = self._engine.run_backtest(config, signals, market_data)

        return BacktestResult(report=report)

    def run_from_tracker(
        self,
        config: BacktestConfig,
        tracker: OutcomeTracker,
        market_data: list[dict],
    ) -> BacktestResult:
        """Run a backtest using decisions from OutcomeTracker.

        Args:
            config: Backtest configuration.
            tracker: OutcomeTracker with recorded decisions.
            market_data: Historical bar data.

        Returns:
            BacktestResult wrapping BacktestReport.
        """
        decisions = tracker.get_all_decisions()
        return self.run(config, decisions, market_data)

    def compare(
        self,
        reports: list[BacktestReport],
    ) -> dict:
        """Compare multiple backtest reports.

        Args:
            reports: List of BacktestReport objects.

        Returns:
            Comparison dict with per-strategy metrics and rankings.
        """
        return self._engine.compare_strategies(reports)

    def _decisions_to_signals(
        self, decisions: list[SignalDecision]
    ) -> list[dict]:
        """Convert SignalDecision list to signal dicts for the adapter."""
        signals = []
        for d in decisions:
            direction = d.signal.direction.value
            if direction not in ("up", "down"):
                continue

            voters = [
                {"name": v.name, "direction": v.direction, "confidence": v.confidence}
                for v in d.signal.voters
            ]

            signals.append({
                "symbol": "NIFTY",  # Default; can be extended
                "direction": direction,
                "conviction": d.signal.conviction,
                "timestamp": d.timestamp.isoformat() if d.timestamp else None,
                "voters": voters,
                "decision_id": d.id,
            })

        return signals
