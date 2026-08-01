from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from shettyxtreme.intelligence.conviction.conviction_engine import ConvictionEngine
from shettyxtreme.intelligence.features.feature_engine import FeatureEngine

if TYPE_CHECKING:
    from shettyxtreme.intelligence.signals.voter_correlation import VoterCorrelation


class SignalDirection(Enum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"

@dataclass
class Vote:
    direction: float
    confidence: float
    weight: float
    name: str

@dataclass
class Signal:
    direction: SignalDirection
    conviction: float
    voters: list[Vote]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    D: float = 0.0
    P: float = 1.0
    G: str = "contested"

class VoterRegistry:
    """Registry of named voter callables with weights."""

    def __init__(self) -> None:
        self._voters: dict[str, Callable[[dict[str, float]], Vote]] = {}
        self._weights: dict[str, float] = {}

    def register(self, name: str, fn: Callable[[dict[str, float]], Vote], weight: float = 1.0) -> None:
        if not name:
            raise ValueError("voter name must be non-empty")
        if not callable(fn):
            raise ValueError("voter must be callable")
        self._voters[name] = fn
        self._weights[name] = weight

    def names(self) -> list[str]:
        return list(self._voters)

    def count(self) -> int:
        return len(self._voters)

    def get(self, name: str) -> Callable[[dict[str, float]], Vote] | None:
        return self._voters.get(name)


_DEFAULT_REGISTRY = VoterRegistry()


def voter(name: str, weight: float = 1.0):
    """Decorator registering a voter function into the default registry."""
    def decorator(fn):
        _DEFAULT_REGISTRY.register(name, fn, weight)
        return fn
    return decorator


def get_registry() -> VoterRegistry:
    """Return the module-level default registry."""
    return _DEFAULT_REGISTRY

class SignalEngine:
    def __init__(
        self,
        feature_engine: FeatureEngine,
        correlation: VoterCorrelation | None = None,
        history_window: int = 50,
        **kwargs,
    ) -> None:
        self.feature_engine = feature_engine
        self.correlation = correlation
        self.history_window = history_window
        self.voters: dict[str, Callable[[dict[str, float]], Vote]] = {}
        self.voter_weights: dict[str, float] = {}
        self._vote_history: list[list[Vote]] = []

    def register_voter(self, name: str, voter: Callable[[dict[str, float]], Vote], weight: float = 1.0) -> None:
        self.voters[name] = voter
        self.voter_weights[name] = weight

    def compute_signal(self, *args, **kwargs) -> Signal:
        votes = []
        for name, voter in self.voters.items():
            vote = voter(self.feature_engine.features)
            vote.weight = self.voter_weights.get(name, 1.0)
            votes.append(vote)

        if self.correlation is not None:
            self._vote_history.append(list(votes))
            if len(self._vote_history) > self.history_window:
                self._vote_history = self._vote_history[-self.history_window:]
            if len(self._vote_history) >= 5:
                self.correlation.compute_correlation_matrix(self._vote_history)
                groups = self.correlation.get_correlation_groups(threshold=0.7)
                caps: dict[str, float] = {}
                for g in groups:
                    if len(g) < 2:
                        continue
                    cap = self.correlation.get_block_cap(g)
                    for name in g:
                        caps[name] = cap
                votes = self.correlation.apply_block_caps(votes, caps)

        total_weight = sum(v.weight for v in votes)
        if total_weight == 0:
            return Signal(SignalDirection.NEUTRAL, 0.0, votes)

        weighted_dir = sum(v.direction * v.confidence * v.weight for v in votes) / total_weight
        conviction = abs(weighted_dir)
        
        direction = SignalDirection.NEUTRAL
        if weighted_dir > 0.1:
            direction = SignalDirection.UP
        elif weighted_dir < -0.1:
            direction = SignalDirection.DOWN

        result = ConvictionEngine().compute(
            [asdict(v) for v in votes], eligible=len(self.voters)
        )
        return Signal(direction, conviction, votes, D=result.D, P=result.P, G=result.G)
    
    compute_signal_from_votes = compute_signal
