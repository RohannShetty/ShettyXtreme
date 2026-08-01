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
