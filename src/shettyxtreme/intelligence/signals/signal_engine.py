"""Signal engine with voter plugin system and participation-normalized conviction.

Voters register via the @voter decorator or VoterRegistry.register().
Conviction = |D| * P * (1 - G), where:
  D = participation-weighted direction score
  P = participation ratio
  G = disagreement (std of voter directions)
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

import yaml
from pathlib import Path

from shettyxtreme.intelligence.regime import Regime


# ---------------------------------------------------------------------------
# Enums / Dataclasses
# ---------------------------------------------------------------------------
class SignalDirection(Enum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"

    def __str__(self) -> str:
        return self.value


@dataclass
class Vote:
    """A single voter's opinion."""
    direction: float  # -1.0 to 1.0 (negative = bearish/down, positive = bullish/up)
    confidence: float  # 0.0 to 1.0
    weight: float  # from config
    name: str

    def __post_init__(self) -> None:
        self.direction = max(-1.0, min(1.0, self.direction))
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class Signal:
    """Aggregated signal from all voters."""
    direction: SignalDirection
    conviction: float  # 0.0-1.0
    D: float  # participation-weighted direction score
    P: float  # participation ratio
    G: float  # disagreement (std of directions)
    voters: list[Vote]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Voter plugin system
# ---------------------------------------------------------------------------
VoterFn = Callable[[dict[str, float], Regime, dict[str, Any]], Vote]


class VoterRegistry:
    """Registry for signal voters. Supports decorator and direct registration."""

    def __init__(self) -> None:
        self._voters: dict[str, VoterFn] = {}

    def register(self, name: str, fn: VoterFn, weight: float = 1.0) -> None:
        """Register a voter function by name."""
        self._voters[name] = fn

    def unregister(self, name: str) -> None:
        self._voters.pop(name, None)

    def get(self, name: str) -> VoterFn | None:
        return self._voters.get(name)

    @property
    def names(self) -> list[str]:
        return list(self._voters.keys())

    @property
    def count(self) -> int:
        return len(self._voters)


# Global registry
_registry = VoterRegistry()


def voter(name: str, weight: float = 1.0) -> Callable[[VoterFn], VoterFn]:
    """Decorator to register a voter function."""
    def decorator(fn: VoterFn) -> VoterFn:
        _registry.register(name, fn)
        return fn
    return decorator


def get_registry() -> VoterRegistry:
    """Get the global voter registry."""
    return _registry


# ---------------------------------------------------------------------------
# Default config path
# ---------------------------------------------------------------------------
_DEFAULT_WEIGHTS_PATH = Path(__file__).resolve().parent.parent.parent / "core" / "config" / "voter_weights.yaml"


def _load_weights(path: str | Path = _DEFAULT_WEIGHTS_PATH) -> dict[str, float]:
    """Load voter weights from YAML config."""
    p = Path(path)
    if not p.exists():
        return {}
    with open(p) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return {}
    return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}


# ---------------------------------------------------------------------------
# SignalEngine
# ---------------------------------------------------------------------------
class SignalEngine:
    """Orchestrates voters and computes participation-normalized conviction.

    Args:
        voter_registry: VoterRegistry instance. If None, uses global registry.
        weights_path: Path to YAML with voter weights.
        conviction_threshold: Min conviction for UP/DOWN signal (else NEUTRAL).
        disagreement_threshold: Max G before signalling NEUTRAL.
    """

    def __init__(
        self,
        voter_registry: VoterRegistry | None = None,
        weights_path: str | None = None,
        conviction_threshold: float | None = None,
        disagreement_threshold: float | None = None,
    ) -> None:
        self._registry = voter_registry or _registry
        weights = _load_weights(weights_path) if weights_path else _load_weights()
        self._weights: dict[str, float] = weights

        # Load thresholds from config, fallback to constants
        self._conviction_threshold = conviction_threshold
        self._disagreement_threshold = disagreement_threshold
        if self._conviction_threshold is None:
            self._conviction_threshold = weights.get("conviction_threshold", 0.35)
        if self._disagreement_threshold is None:
            self._disagreement_threshold = weights.get("disagreement_threshold", 0.45)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def compute_signal(
        self,
        features: dict[str, float],
        regime: Regime,
        options_context: dict[str, Any] | None = None,
    ) -> Signal:
        """Compute aggregate signal from all registered voters.

        Args:
            features: Feature dict from FeatureEngine.
            regime: Current market regime.
            options_context: Optional context for options-aware voters.

        Returns:
            Signal dataclass with direction, conviction, and decomposition.
        """
        ctx = options_context or {}
        votes: list[Vote] = []

        for name in self._registry.names:
            fn = self._registry.get(name)
            if fn is None:
                continue
            try:
                vote = fn(features, regime, ctx)
            except Exception:
                vote = Vote(direction=0.0, confidence=0.0, weight=0.0, name=name)
            votes.append(vote)

        return self._aggregate(votes)

    def compute_signal_from_votes(self, votes: list[Vote]) -> Signal:
        """Compute signal from a pre-collected list of votes."""
        return self._aggregate(votes)

    # ------------------------------------------------------------------
    # Conviction computation
    # ------------------------------------------------------------------
    def _aggregate(self, votes: list[Vote]) -> Signal:
        """Participation-normalized conviction aggregation."""
        if not votes:
            return Signal(
                direction=SignalDirection.NEUTRAL,
                conviction=0.0,
                D=0.0, P=0.0, G=0.0,
                voters=[],
            )

        # Only consider voters with confidence > 0
        active_votes = [v for v in votes if v.confidence > 0]
        total_voters = len(votes)

        if not active_votes:
            return Signal(
                direction=SignalDirection.NEUTRAL,
                conviction=0.0,
                D=0.0, P=0.0, G=0.0,
                voters=list(votes),
            )

        # Apply per-voter weight from config
        weighted_votes: list[Vote] = []
        for v in active_votes:
            w = self._weights.get(v.name, v.weight)
            weighted_votes.append(Vote(
                direction=v.direction,
                confidence=v.confidence,
                weight=w,
                name=v.name,
            ))

        # D = participation-weighted direction score
        numerator = sum(v.direction * v.confidence * v.weight for v in weighted_votes)
        denominator = sum(v.confidence * v.weight for v in weighted_votes)
        D = numerator / denominator if denominator != 0 else 0.0

        # P = participation ratio
        P = len(active_votes) / total_voters if total_voters > 0 else 0.0

        # G = disagreement (proportion of voters opposite to weighted consensus)
        # This measures how many voters disagree with the net direction.
        if len(weighted_votes) >= 2:
            # Consensus direction is sign(D)
            consensus_sign = 1 if D >= 0 else -1
            opposing = sum(
                1 for v in weighted_votes
                if (v.direction > 0 and consensus_sign < 0)
                or (v.direction < 0 and consensus_sign > 0)
            )
            G = opposing / len(weighted_votes)  # 0.0 (all agree) to 1.0 (all oppose)
        else:
            G = 0.0

        # Conviction = |D| * P * (1 - G)
        conviction = abs(D) * P * (1.0 - G)

        # Determine direction
        if conviction < self._conviction_threshold or G > self._disagreement_threshold:
            direction = SignalDirection.NEUTRAL
        elif D > 0:
            direction = SignalDirection.UP
        else:
            direction = SignalDirection.DOWN

        return Signal(
            direction=direction,
            conviction=conviction,
            D=D, P=P, G=G,
            voters=list(votes),
        )
