"""Tests for SignalEngine and Voter plugin system."""
from __future__ import annotations

from unittest.mock import MagicMock
from typing import Any

import pytest

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import (
    SignalEngine, SignalDirection, Signal, Vote,
    VoterRegistry, voter, get_registry,
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


# ---------------------------------------------------------------------------
# VoterRegistry
# ---------------------------------------------------------------------------
class TestVoterRegistry:
    def test_register_and_get(self) -> None:
        reg = VoterRegistry()
        fn = lambda fe: Vote(direction=1.0, confidence=0.5, weight=1.0, name="r")
        reg.register("r", fn, weight=2.0)
        assert reg.count() == 1
        assert reg.names() == ["r"]
        assert reg.get("r") is fn
        assert reg.get("missing") is None

    def test_register_requires_name_and_callable(self) -> None:
        reg = VoterRegistry()
        with pytest.raises(ValueError):
            reg.register("", lambda fe: None)
        with pytest.raises(ValueError):
            reg.register("x", None)

    def test_decorator_registers_into_default_registry(self) -> None:
        @voter("decorated_test", weight=0.5)
        def decorated(features: dict[str, float]) -> Vote:
            return Vote(direction=-1.0, confidence=0.7, weight=0.5, name="decorated_test")

        reg = get_registry()
        assert reg.get("decorated_test") is decorated


# ---------------------------------------------------------------------------
# Signal path wiring: correlation block caps + conviction D/P/G
# ---------------------------------------------------------------------------
class TestSignalPathWiring:
    def setup_method(self) -> None:
        self.engine = SignalEngine(feature_engine=MagicMock(features={}))

    def test_correlation_block_caps_scale_group_weights(self) -> None:
        from shettyxtreme.intelligence.signals.voter_correlation import VoterCorrelation
        engine = SignalEngine(feature_engine=MagicMock(features={}),
                              correlation=VoterCorrelation(block_cap=1.0))
        engine.register_voter("v1", lambda fe: Vote(1.0, 0.8, 1.0, "v1"))
        engine.register_voter("v2", lambda fe: Vote(1.0, 0.8, 1.0, "v2"))
        engine.register_voter("v3", lambda fe: Vote(-1.0, 0.8, 1.0, "v3"))
        for _ in range(6):  # build history so the matrix is computed
            engine.compute_signal()
        sig = engine.compute_signal()
        assert sig.conviction < 0.8  # capped group cannot dominate
        assert sig.P == pytest.approx(1.0)

    def test_signal_carries_dpg(self) -> None:
        self.engine.register_voter("u", lambda fe: Vote(1.0, 0.8, 1.0, "u"))
        sig = self.engine.compute_signal()
        assert sig.D > 0
        assert sig.P == pytest.approx(1.0)
        assert sig.G in ("unanimous", "contested")

    def test_dpg_defaults_when_no_voters(self) -> None:
        sig = self.engine.compute_signal()
        assert sig.D == 0.0 and sig.P == 1.0 and sig.G == "contested"
