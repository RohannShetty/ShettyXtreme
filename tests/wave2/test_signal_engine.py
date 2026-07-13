"""Tests for SignalEngine and Voter plugin system."""
from __future__ import annotations

from typing import Any

import pytest

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import (
    SignalEngine, SignalDirection, Signal, Vote,
    VoterRegistry,
)


# ---------------------------------------------------------------------------
# Helper voters
# ---------------------------------------------------------------------------
def _make_bullish_vote(confidence: float = 0.8, weight: float = 1.0) -> Vote:
    return Vote(direction=1.0, confidence=confidence, weight=weight, name="bullish_test")


def _make_bearish_vote(confidence: float = 0.8, weight: float = 1.0) -> Vote:
    return Vote(direction=-1.0, confidence=confidence, weight=weight, name="bearish_test")


def _make_dead_vote() -> Vote:
    return Vote(direction=0.0, confidence=0.0, weight=1.0, name="dead_test")


# ---------------------------------------------------------------------------
# SignalEngine
# ---------------------------------------------------------------------------
class TestSignalEngine:
    def setup_method(self) -> None:
        self.registry = VoterRegistry()
        self.engine = SignalEngine(
            voter_registry=self.registry,
            conviction_threshold=0.35,
            disagreement_threshold=0.45,
        )

    def test_all_up_high_conviction(self) -> None:
        """3 voters all UP 0.8 confidence → D=1.0, P=1.0, G=0 → conviction=1.0."""
        votes = [
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bullish_vote(confidence=0.8, weight=1.0),
        ]
        signal = self.engine.compute_signal_from_votes(votes)
        assert signal.direction == SignalDirection.UP
        assert signal.conviction == pytest.approx(1.0, abs=0.01)
        assert signal.D == pytest.approx(1.0, abs=0.01)
        assert signal.P == 1.0
        assert signal.G == 0.0

    def test_split_votes_neutral(self) -> None:
        """2 UP, 2 DOWN → D=0 → conviction=0 → NEUTRAL."""
        votes = [
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bearish_vote(confidence=0.8, weight=1.0),
            _make_bearish_vote(confidence=0.8, weight=1.0),
        ]
        signal = self.engine.compute_signal_from_votes(votes)
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.D == 0.0
        assert signal.G == 0.5  # 2 of 4 oppose consensus
        assert signal.conviction == 0.0

    def test_majority_up(self) -> None:
        """3 UP, 1 DOWN → G=0.25, conviction=0.375 → UP."""
        votes = [
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bearish_vote(confidence=0.8, weight=1.0),
        ]
        signal = self.engine.compute_signal_from_votes(votes)
        assert signal.direction == SignalDirection.UP
        assert signal.D == pytest.approx(0.5, abs=0.01)
        assert signal.P == 1.0  # all 4 active
        assert signal.G == 0.25  # 1 of 4 opposes consensus

    def test_dead_voters_excluded(self) -> None:
        """confidence=0 voter → excluded from participation."""
        votes = [
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_dead_vote(),  # confidence=0, excluded
        ]
        signal = self.engine.compute_signal_from_votes(votes)
        assert signal.P == 2.0 / 3.0  # 2 active out of 3 total
        assert signal.direction == SignalDirection.UP

    def test_plugin_discovery(self) -> None:
        """Register a custom voter, verify it's used in signal computation."""
        def my_voter(
            features: dict[str, float],
            regime: Regime,
            ctx: dict[str, Any],
        ) -> Vote:
            return Vote(direction=1.0, confidence=0.9, weight=1.0, name="custom_test")

        self.registry.register("custom_test", my_voter)

        features: dict[str, float] = {"test": 1.0}
        signal = self.engine.compute_signal(features, Regime.RANGE_BOUND, {})

        assert signal.direction == SignalDirection.UP
        assert signal.conviction > 0
        voter_names = [v.name for v in signal.voters]
        assert "custom_test" in voter_names

    def test_no_voters_neutral(self) -> None:
        """Empty voter list → NEUTRAL with 0 conviction."""
        signal = self.engine.compute_signal_from_votes([])
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.conviction == 0.0

    def test_voter_weights_from_config(self) -> None:
        """Voter weights are configurable, not hardcoded in vote()."""
        votes = [
            Vote(direction=1.0, confidence=0.8, weight=99.0, name="unknown_voter"),
        ]
        signal = self.engine.compute_signal_from_votes(votes)
        assert signal.conviction > 0


# ---------------------------------------------------------------------------
# Vote dataclass bounds
# ---------------------------------------------------------------------------
class TestVoteBounds:
    def test_direction_clamped(self) -> None:
        v = Vote(direction=5.0, confidence=0.5, weight=1.0, name="test")
        assert v.direction == 1.0

    def test_direction_negative_clamped(self) -> None:
        v = Vote(direction=-5.0, confidence=0.5, weight=1.0, name="test")
        assert v.direction == -1.0

    def test_confidence_clamped(self) -> None:
        v = Vote(direction=0.5, confidence=2.0, weight=1.0, name="test")
        assert v.confidence == 1.0
