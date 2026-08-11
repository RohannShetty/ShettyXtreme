"""Voter plugins for the Signal Engine.

Each voter is a function with signature:
  vote(features: dict[str, float], regime: Regime, options_context: dict) -> Vote

Register with the @voter decorator.

Note (F-INTEL-001): the former orb_voter / iv_rank_voter stubs were removed —
they voted constant directions on features that are never computed. New voters
must abstain (direction=0, confidence=0) when their input feature is missing.
"""
from .options_flow_voter import options_flow_vote
from .micro_voter import micro_vote
from .breadth_voter import breadth_vote

__all__ = ["options_flow_vote", "micro_vote", "breadth_vote"]
