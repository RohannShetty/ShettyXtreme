
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum
from datetime import datetime, timezone

from shettyxtreme.core.data_models.market_data import Tick
from shettyxtreme.intelligence.features.feature_engine import FeatureEngine

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
    voters: List[Vote]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class VoterRegistry:
    def register(self, name, fn, weight=1.0): pass
    def names(self): return []
    def count(self): return 0
    def get(self, name): return None

def voter(name, weight=1.0):
    def decorator(fn): return fn
    return decorator

def get_registry(): return VoterRegistry()

class SignalEngine:
    def __init__(self, feature_engine: FeatureEngine, **kwargs) -> None:
        self.feature_engine = feature_engine
        self.voters: Dict[str, Callable[[Dict[str, float]], Vote]] = {}
        self.voter_weights: Dict[str, float] = {}

    def register_voter(self, name: str, voter: Callable[[Dict[str, float]], Vote], weight: float = 1.0) -> None:
        self.voters[name] = voter
        self.voter_weights[name] = weight

    def compute_signal(self, *args, **kwargs) -> Signal:
        votes = []
        for name, voter in self.voters.items():
            vote = voter(self.feature_engine.features)
            vote.weight = self.voter_weights.get(name, 1.0)
            votes.append(vote)

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
            
        return Signal(direction, conviction, votes)
    
    compute_signal_from_votes = compute_signal
