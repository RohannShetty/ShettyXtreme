"""Deterministic synthetic-session simulator for shadow-voter testing.

Test-only. Scripted vote/outcome patterns; no randomness.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from shettyxtreme.intelligence.signals.signal_engine import Vote
from shettyxtreme.intelligence.signals.shadow_manager import ShadowManager
from shettyxtreme.learning.outcome_tracker import OutcomeLabel


@dataclass
class SimulatedSignal:
    features: dict[str, float]
    regime: Any
    options_context: dict[str, Any]
    live_direction: float
    outcome: OutcomeLabel


@dataclass
class SimulatedSession:
    date: str
    signals: list[SimulatedSignal] = field(default_factory=list)


def make_shadow_manager(db_path: str) -> ShadowManager:
    mgr = ShadowManager(db_path=db_path)
    mgr.register_shadow("good_voter", _good_vote)
    mgr.register_shadow("poor_voter", _poor_vote)
    return mgr


def _good_vote(features: dict[str, float], regime: Any, options_context: dict) -> Vote:
    return Vote(direction=float(features.get("_live_direction", 0.0)), confidence=0.7, weight=1.0, name="good_voter")


def _poor_vote(features: dict[str, float], regime: Any, options_context: dict) -> Vote:
    return Vote(direction=-float(features.get("_live_direction", 0.0)), confidence=0.7, weight=1.0, name="poor_voter")


def run_sessions(manager: ShadowManager, sessions: list[SimulatedSession]) -> None:
    sig_idx = 0
    for session in sessions:
        for sig in session.signals:
            features = dict(sig.features)
            features["_live_direction"] = sig.live_direction
            votes = manager.run_shadow(features, sig.regime, sig.options_context)
            sid = f"sig-{sig_idx}"
            manager.log_shadow_results(sid, votes, session_date=session.date)
            manager.compare_shadow_vs_live(sid, sig.outcome, live_direction=sig.live_direction)
            sig_idx += 1
