"""Tests for StrategyHints generation (D6 pipeline stage 4)."""
from __future__ import annotations

import pytest

from shettyxtreme.intelligence.hints.strategy_hints import StrategyHints, StrategyHint

BULLISH_SIGNAL = {
    "direction": "UP", "conviction": 0.7, "D": 0.6, "P": 1.0, "G": "unanimous",
    "voters": [{"name": "v1", "direction": 1.0, "confidence": 0.7, "weight": 1.0}],
}

CHAIN = [
    {"strike": 24000, "option_type": "CE", "premium": 150.0, "lot_size": 25, "iv": 15.0},
    {"strike": 24100, "option_type": "CE", "premium": 100.0, "lot_size": 25, "iv": 15.0},
]


class TestStrategyHints:
    def test_neutral_signal_returns_neutral_hint(self) -> None:
        hint = StrategyHints(signal={"direction": "NEUTRAL", "conviction": 0.0}).generate()
        assert hint.direction == "neutral"
        assert hint.strike is None
        assert hint.rationale

    def test_low_conviction_stays_neutral(self) -> None:
        sig = dict(BULLISH_SIGNAL, conviction=0.1)
        hint = StrategyHints(signal=sig).generate()
        assert hint.direction == "neutral"

    def test_low_participation_stays_neutral(self) -> None:
        sig = dict(BULLISH_SIGNAL, P=0.2)
        hint = StrategyHints(signal=sig).generate()
        assert hint.direction == "neutral"

    def test_bullish_hint_without_price(self) -> None:
        hint = StrategyHints(signal=BULLISH_SIGNAL, chain=CHAIN).generate()
        assert hint.direction == "bullish"
        assert hint.strategy
        assert hint.strike is None
        assert hint.rationale

    def test_bullish_selects_positive_ev_strike(self) -> None:
        hint = StrategyHints(
            signal=BULLISH_SIGNAL, chain=CHAIN, current_price=24000.0,
            slippage_per_lot=0.0, brokerage_per_lot=0.0,
        ).generate()
        assert hint.direction == "bullish"
        assert hint.strike == 24000.0
        assert hint.ev_after_cost > 0

    def test_bullish_selects_strike_with_alias_keys(self) -> None:
        """Dhan /optionchain alias keys (strike_price/drv_option_type) must work."""
        chain = [
            {"strike_price": 24000, "drv_option_type": "CE", "premium": 150.0, "lot_size": 25, "iv": 15.0},
            {"strike_price": 24100, "drv_option_type": "CE", "premium": 100.0, "lot_size": 25, "iv": 15.0},
        ]
        hint = StrategyHints(
            signal=BULLISH_SIGNAL, chain=chain, current_price=24000.0,
            slippage_per_lot=0.0, brokerage_per_lot=0.0,
        ).generate()
        assert hint.direction == "bullish"
        assert hint.strike == 24000.0


def test_sizing_hook_sets_quantity() -> None:
    from datetime import UTC, datetime
    from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection, Vote
    from shettyxtreme.learning.calibration import CalibrationCurve
    from shettyxtreme.learning.outcome_tracker import OutcomeLabel, SignalDecision
    from shettyxtreme.learning.sizing import CalibratedSizing

    def cal_decision(conviction: float) -> SignalDecision:
        sig = Signal(direction=SignalDirection.UP, conviction=conviction,
                     voters=[Vote(1.0, conviction, 1.0, "v")], timestamp=datetime.now(UTC))
        return SignalDecision(id="x", signal=sig, timestamp=datetime.now(UTC), outcome=OutcomeLabel.WIN)

    # Fit at the signal's own conviction (0.7): predict(0.7) hits a populated
    # bin (100% WIN -> 1.0); fitting at 0.8 would leave bin 7 empty and fall
    # back to raw conviction.
    curve = CalibrationCurve()
    curve.fit([cal_decision(0.7) for _ in range(40)])
    sizing = CalibratedSizing(curve, base_rate=0.5)
    sizing.set_active(True)
    hint = StrategyHints(signal=BULLISH_SIGNAL, chain=None, current_price=24000.0,
                         sizing=sizing, base_quantity=100).generate()
    assert hint.quantity == pytest.approx(200, rel=0.05)


def test_sizing_hook_sets_quantity_with_strike() -> None:
    from datetime import UTC, datetime
    from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection, Vote
    from shettyxtreme.learning.calibration import CalibrationCurve
    from shettyxtreme.learning.outcome_tracker import OutcomeLabel, SignalDecision
    from shettyxtreme.learning.sizing import CalibratedSizing

    def cal_decision(conviction: float) -> SignalDecision:
        sig = Signal(direction=SignalDirection.UP, conviction=conviction,
                     voters=[Vote(1.0, conviction, 1.0, "v")], timestamp=datetime.now(UTC))
        return SignalDecision(id="x", signal=sig, timestamp=datetime.now(UTC), outcome=OutcomeLabel.WIN)

    curve = CalibrationCurve()
    curve.fit([cal_decision(0.7) for _ in range(40)])
    sizing = CalibratedSizing(curve, base_rate=0.5)
    sizing.set_active(True)
    hint = StrategyHints(signal=BULLISH_SIGNAL, chain=CHAIN, current_price=24000.0,
                         slippage_per_lot=0.0, brokerage_per_lot=0.0,
                         sizing=sizing, base_quantity=100).generate()
    assert hint.direction == "bullish"
    assert hint.strike == 24000.0
    assert hint.quantity == pytest.approx(200, rel=0.05)


def test_no_sizing_no_quantity() -> None:
    hint = StrategyHints(signal=BULLISH_SIGNAL).generate()
    assert hint.quantity is None
