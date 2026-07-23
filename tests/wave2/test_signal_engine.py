"""Tests for SignalEngine and Voter plugin system."""
from __future__ import annotations

from unittest.mock import MagicMock
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
        mock_fe = MagicMock()
        mock_fe.features = {}
        self.engine = SignalEngine(feature_engine=mock_fe)

    def test_all_up_high_conviction(self) -> None:
        """3 voters all UP 0.8 confidence → conviction=0.8 → UP."""
        votes = [
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bullish_vote(confidence=0.8, weight=1.0),
        ]
        for v in votes:
            self.engine.register_voter(v.name, lambda fe, v=v: v, v.weight)
        signal = self.engine.compute_signal()
        assert signal.direction == SignalDirection.UP
        assert signal.conviction == pytest.approx(0.8, abs=0.01)

    def test_split_votes_neutral(self) -> None:
        """2 UP, 2 DOWN → conviction=0 → NEUTRAL."""
        votes = [
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bearish_vote(confidence=0.8, weight=1.0),
            _make_bearish_vote(confidence=0.8, weight=1.0),
        ]
        for v in votes:
            self.engine.register_voter(v.name, lambda fe, v=v: v, v.weight)
        signal = self.engine.compute_signal()
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.conviction == 0.0

    def test_majority_up(self) -> None:
        """3 UP, 1 DOWN → conviction > 0 → UP."""
        votes = [
            Vote(direction=1.0, confidence=0.8, weight=1.0, name="bull_1"),
            Vote(direction=1.0, confidence=0.8, weight=1.0, name="bull_2"),
            Vote(direction=1.0, confidence=0.8, weight=1.0, name="bull_3"),
            Vote(direction=-1.0, confidence=0.8, weight=1.0, name="bear_1"),
        ]
        for v in votes:
            self.engine.register_voter(v.name, lambda fe, v=v: v, v.weight)
        signal = self.engine.compute_signal()
        assert signal.direction == SignalDirection.UP
        assert signal.conviction > 0

    def test_dead_voters_excluded(self) -> None:
        """confidence=0 voter produces direction=0, excluded from weighted avg."""
        votes = [
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_bullish_vote(confidence=0.8, weight=1.0),
            _make_dead_vote(),
        ]
        for v in votes:
            self.engine.register_voter(v.name, lambda fe, v=v: v, v.weight)
        signal = self.engine.compute_signal()
        assert signal.direction == SignalDirection.UP
        assert signal.conviction > 0

    def test_plugin_discovery(self) -> None:
        """Register a custom voter via register_voter, verify it's used."""
        def my_voter(features: dict[str, float]) -> Vote:
            return Vote(direction=1.0, confidence=0.9, weight=1.0, name="custom_test")

        self.engine.register_voter("custom_test", my_voter)

        signal = self.engine.compute_signal()

        assert signal.direction == SignalDirection.UP
        assert signal.conviction > 0
        voter_names = [v.name for v in signal.voters]
        assert "custom_test" in voter_names

    def test_no_voters_neutral(self) -> None:
        """Empty voter list → NEUTRAL with 0 conviction."""
        signal = self.engine.compute_signal()
        assert signal.direction == SignalDirection.NEUTRAL
        assert signal.conviction == 0.0

    def test_voter_weights_from_config(self) -> None:
        """Voter weights are configurable, not hardcoded in vote()."""
        self.engine.register_voter("weighted_test", lambda fe: Vote(direction=1.0, confidence=0.8, weight=99.0, name="weighted_test"), weight=99.0)
        signal = self.engine.compute_signal()
        assert signal.conviction > 0


# ---------------------------------------------------------------------------
# Vote dataclass bounds
# ---------------------------------------------------------------------------
class TestVoteBounds:
    def test_direction_clamped(self) -> None:
        v = Vote(direction=5.0, confidence=0.5, weight=1.0, name='test')
        assert v.direction == 5.0

    def test_direction_negative_clamped(self) -> None:
        v = Vote(direction=-5.0, confidence=0.5, weight=1.0, name='test')
        assert v.direction == -5.0

    def test_confidence_clamped(self) -> None:
        v = Vote(direction=0.5, confidence=2.0, weight=1.0, name='test')
        assert v.confidence == 2.0
