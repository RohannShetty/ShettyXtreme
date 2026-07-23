"""Tests for the analytics engine."""
from __future__ import annotations

import os

import pytest

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
    Vote,
)
from shettyxtreme.learning.analytics import AnalyticsEngine
from shettyxtreme.learning.outcome_tracker import OutcomeLabel, SignalDecision
from shettyxtreme.learning.voter_quality import VoterQualityTracker


def _decision(
    dec_id: str,
    regime: Regime,
    outcome: OutcomeLabel,
    conviction: float = 0.7,
    voters: list[Vote] | None = None,
) -> SignalDecision:
    return SignalDecision(
        id=dec_id,
        signal=Signal(
            direction=SignalDirection.UP,
            conviction=conviction,
            voters=voters or [],
        ),
        timestamp=None,  # type: ignore[arg-type]
        strategy_hint={"regime": regime},
        outcome=outcome,
    )


def test_signal_quality_by_regime() -> None:
    eng = AnalyticsEngine()
    decisions = [
        _decision("a", Regime.TRENDING_UP, OutcomeLabel.WIN),
        _decision("b", Regime.TRENDING_UP, OutcomeLabel.LOSS),
        _decision("c", Regime.RANGE_BOUND, OutcomeLabel.WIN),
    ]
    result = eng.signal_quality_by_regime(decisions)
    assert Regime.TRENDING_UP in result
    assert Regime.RANGE_BOUND in result
    assert result[Regime.TRENDING_UP].total_signals == 2
    assert result[Regime.TRENDING_UP].win_rate == pytest.approx(0.5)
    assert result[Regime.TRENDING_UP].avg_conviction == pytest.approx(0.7)


def test_win_loss_by_regime() -> None:
    eng = AnalyticsEngine()
    decisions = [
        _decision("a", Regime.VOLATILE, OutcomeLabel.WIN),
        _decision("b", Regime.VOLATILE, OutcomeLabel.WIN),
        _decision("c", Regime.VOLATILE, OutcomeLabel.LOSS),
    ]
    result = eng.win_loss_by_regime(decisions)
    wl = result[Regime.VOLATILE]
    assert wl.wins == 2
    assert wl.losses == 1


def test_cost_analysis() -> None:
    eng = AnalyticsEngine()
    decisions = [
        _decision("a", Regime.VOLATILE, OutcomeLabel.WIN),
        _decision("b", Regime.VOLATILE, OutcomeLabel.LOSS),
    ]
    result = eng.cost_analysis(decisions)
    assert result.total_trades == 2
    assert result.total_cost == pytest.approx(0.0)


def test_performance_summary() -> None:
    eng = AnalyticsEngine()
    decisions = [
        _decision("a", Regime.VOLATILE, OutcomeLabel.WIN),
        _decision("b", Regime.VOLATILE, OutcomeLabel.WIN),
        _decision("c", Regime.VOLATILE, OutcomeLabel.LOSS),
    ]
    summary = eng.performance_summary(decisions)
    assert summary.total_signals == 3
    assert summary.total_trades == 3
    assert 0.0 <= summary.win_rate <= 1.0
    assert summary.win_rate == pytest.approx(2 / 3)
    assert isinstance(summary.sharpe, float)
    assert isinstance(summary.max_drawdown, float)
    assert isinstance(summary.total_pnl, float)


def test_voter_contribution(tmp_data_dir: str) -> None:
    eng = AnalyticsEngine()
    quality = VoterQualityTracker(os.path.join(tmp_data_dir, "vq.db"))
    voters = [Vote(direction=1.0, confidence=0.8, weight=1.0, name="momentum")]
    decisions = [
        _decision("a", Regime.VOLATILE, OutcomeLabel.WIN, voters=voters),
        _decision("b", Regime.VOLATILE, OutcomeLabel.LOSS, voters=voters),
    ]
    result = eng.voter_contribution(decisions, quality)
    assert "momentum" in result
    assert result["momentum"].signals_contributed == 2
    quality.close()
