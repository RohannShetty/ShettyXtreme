"""Tests for calibrated position sizing (spec §3.3)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection, Vote
from shettyxtreme.learning.calibration import CalibrationCurve
from shettyxtreme.learning.outcome_tracker import OutcomeLabel, SignalDecision
from shettyxtreme.learning.sizing import CalibratedSizing


def _decision(conviction: float) -> SignalDecision:
    sig = Signal(direction=SignalDirection.UP, conviction=conviction,
                 voters=[Vote(1.0, conviction, 1.0, "v")], timestamp=datetime.now(UTC))
    return SignalDecision(id="x", signal=sig, timestamp=datetime.now(UTC), outcome=OutcomeLabel.WIN)


class TestCalibratedSizing:
    def test_adjust_uses_calibrated_win_rate(self) -> None:
        curve = CalibrationCurve()
        curve.fit([_decision(0.8) for _ in range(40)])
        sizing = CalibratedSizing(curve, base_rate=0.5)
        sizing.set_active(True)
        assert sizing.adjust(100, 0.8) == pytest.approx(200, rel=0.05)  # 1.0/0.5 * 100

    def test_clamps_to_max_multiplier(self) -> None:
        curve = CalibrationCurve()
        curve.fit([_decision(0.9) for _ in range(40)])
        sizing = CalibratedSizing(curve, base_rate=0.1, max_multiplier=2.0)
        sizing.set_active(True)
        assert sizing.adjust(100, 0.9) <= 200

    def test_clamps_to_min_multiplier(self) -> None:
        curve = CalibrationCurve()
        curve.fit([_decision(0.1) for _ in range(40)])
        sizing = CalibratedSizing(curve, base_rate=0.9, min_multiplier=0.25)
        sizing.set_active(True)
        assert sizing.adjust(100, 0.1) >= 25

    def test_inactive_returns_base(self) -> None:
        sizing = CalibratedSizing(CalibrationCurve())
        assert sizing.adjust(75, 0.8) == 75

    def test_positive_quantity_required(self) -> None:
        sizing = CalibratedSizing(CalibrationCurve())
        with pytest.raises(ValueError):
            sizing.adjust(0, 0.8)
