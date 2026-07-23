"""Tests for the walkforward evaluator — honest premium-based backtest."""
from __future__ import annotations

import pytest

from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
)
from shettyxtreme.learning.outcome_tracker import SignalDecision
from shettyxtreme.learning.walkforward import WalkforwardEvaluator


def _decision(dec_id: str, direction: SignalDirection) -> SignalDecision:
    return SignalDecision(
        id=dec_id,
        signal=Signal(
            direction=direction,
            conviction=0.7,
            voters=[],
        ),
        timestamp=None,  # type: ignore[arg-type]
        strategy_hint=None,
    )


def test_tp1_hit_profit() -> None:
    ev = WalkforwardEvaluator()
    decisions = [_decision("d1", SignalDirection.UP)]
    entry = {"d1": 100.0}
    # exit premium 130 >= entry*(1+0.30)=130 -> TP1 exactly
    exit_p = {"d1": 130.0}
    res = ev.evaluate(decisions, entry, exit_p)
    # TP1 premium = 130, gross = (130-100)*75 = 2250 minus cost
    assert res.num_trades == 1
    assert res.total_return > 0
    assert res.win_rate == pytest.approx(1.0)


def test_losing_trade() -> None:
    ev = WalkforwardEvaluator()
    decisions = [_decision("d1", SignalDirection.UP)]
    entry = {"d1": 100.0}
    exit_p = {"d1": 80.0}  # below entry, no TP, no stop -> EOD loss
    res = ev.evaluate(decisions, entry, exit_p)
    assert res.total_return < 0
    assert res.win_rate == pytest.approx(0.0)


def test_eod_exit_no_target() -> None:
    ev = WalkforwardEvaluator()
    decisions = [_decision("d1", SignalDirection.UP)]
    entry = {"d1": 100.0}
    # exit premium 110 is below TP1 (130) and above stop (50) -> EOD
    exit_p = {"d1": 110.0}
    res = ev.evaluate(decisions, entry, exit_p)
    # gross = (110-100)*75 = 750 minus cost
    assert res.num_trades == 1
    assert res.total_return > 0


def test_short_trade() -> None:
    ev = WalkforwardEvaluator()
    decisions = [_decision("d1", SignalDirection.DOWN)]
    entry = {"d1": 100.0}
    exit_p = {"d1": 70.0}  # short profits when premium falls
    res = ev.evaluate(decisions, entry, exit_p)
    assert res.total_return > 0


def test_cost_adjusted_and_aggregate() -> None:
    ev = WalkforwardEvaluator()
    decisions = [
        _decision("a", SignalDirection.UP),
        _decision("b", SignalDirection.UP),
        _decision("c", SignalDirection.DOWN),
    ]
    entry = {"a": 100.0, "b": 100.0, "c": 100.0}
    exit_p = {"a": 130.0, "b": 80.0, "c": 70.0}
    res = ev.evaluate(decisions, entry, exit_p)
    assert res.num_trades == 3
    assert isinstance(res.sharpe_ratio, float)
    assert isinstance(res.max_drawdown, float)
    assert res.max_drawdown >= 0.0
    # cost-adjusted equals total_return (cost already subtracted)
    assert res.cost_adjusted_return == pytest.approx(res.total_return)
    # with one loss, win_rate < 1
    assert res.win_rate < 1.0
