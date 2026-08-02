"""Voter plugins for the Signal Engine.

Each voter is a function with signature:
  vote(features: dict[str, float], regime: Regime, options_context: dict) -> Vote

Register with the @voter decorator.
"""
from .options_flow_voter import options_flow_vote
from .orb_voter import orb_vote
from .micro_voter import micro_vote
from .breadth_voter import breadth_vote

__all__ = ["options_flow_vote", "orb_vote", "micro_vote", "breadth_vote"]
