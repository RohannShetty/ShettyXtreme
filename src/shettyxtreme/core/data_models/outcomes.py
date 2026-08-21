"""Outcome label enum — canonical home for signal outcome classification.

Moved from learning.outcome_tracker to break the intelligence↔learning
import cycle.  Both intelligence/ and learning/ import from here.
"""
from __future__ import annotations

from enum import Enum


class OutcomeLabel(Enum):
    """Outcome of a signal decision."""

    WIN = "win"
    LOSS = "loss"
    NEUTRAL = "neutral"
    EXPIRED = "expired"
    UNREALIZED = "unrealized"
