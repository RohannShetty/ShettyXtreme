"""Tests for CalibrationCurve (Wave 4 implementation)."""
from __future__ import annotations

from datetime import datetime

import pytest

from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
)
from shettyxtreme.learning.calibration import CalibrationCurve, CalibrationPoint
from shettyxtreme.learning.outcome_tracker import OutcomeLabel, SignalDecision


def _make_decision(conviction: float, win: bool) -> SignalDecision:
    sig = Signal(
        direction=SignalDirection.UP,
        conviction=conviction,
        D=0.0,
        P=1.0,
        G=0.0,
        voters=[],
        timestamp=datetime.now(),
    )
    return SignalDecision(
        id=f"d{conviction}",
        signal=sig,
        timestamp=datetime.now(),
        strategy_hint=None,
        outcome=OutcomeLabel.WIN if win else OutcomeLabel.LOSS,
    )


def test_predict_calibrated_with_enough_data() -> None:
    curve = CalibrationCurve()
    decisions: list[SignalDecision] = []
    # 40 samples per bin; win deterministically monotonic with conviction
    for bin_idx in range(10):
        for k in range(40):
            c = (bin_idx + 0.5) / 10.0
            win = (k / 40.0) < c
            decisions.append(_make_decision(c, win))
    curve.fit(decisions)
    prob = curve.predict(0.85)
    assert 0.0 <= prob <= 1.0
    assert prob == pytest.approx(0.95, abs=0.1)


def test_predict_raw_when_insufficient() -> None:
    curve = CalibrationCurve()
    decisions = [_make_decision(0.8, True) for _ in range(10)]
    curve.fit(decisions)
    assert curve.predict(0.8) == pytest.approx(0.8)


def test_curve_bin_edges_and_monotonic() -> None:
    curve = CalibrationCurve()
    decisions: list[SignalDecision] = []
    for bin_idx in range(10):
        for k in range(40):
            c = (bin_idx + 0.5) / 10.0
            win = (k / 40.0) < c
            decisions.append(_make_decision(c, win))
    curve.fit(decisions)

    points: list[CalibrationPoint] = curve.get_curve()
    assert len(points) == 10
    expected_edges = [
        (i / 10.0, (i + 1) / 10.0) for i in range(10)
    ]
    for p, (lo, hi) in zip(points, expected_edges):
        assert p.conviction_bin[0] == pytest.approx(lo, abs=1e-9)
        assert p.conviction_bin[1] == pytest.approx(hi, abs=1e-9)

    # Top bin win rate must exceed bottom bin win rate
    rates = [p.actual_win_rate for p in points]
    assert rates[-1] > rates[0]
