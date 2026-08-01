"""Participation-normalized conviction — D/P/G (blueprint §14).

Direction = participation-adjusted directional score; participation = share
of eligible voters that produced usable votes; grouping = how the active
voters cluster into a stance (unanimous / contested).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_DIRECTION_THRESHOLD: float = 0.1


@dataclass
class ConvictionResult:
    direction: str  # UP / DOWN / NEUTRAL
    conviction: float
    D: float  # participation-adjusted directional score
    P: float  # participation 0..1
    G: str    # unanimous / contested
    voters: list[dict[str, Any]] = field(default_factory=list)


class ConvictionEngine:
    """Aggregate voter votes into a participation-normalized D/P/G result."""

    def compute(self, votes: list[dict[str, Any]], eligible: int) -> ConvictionResult:
        usable = [
            v for v in votes
            if float(v.get("confidence", 0.0)) > 0.0
            and float(v.get("direction", 0.0)) != 0.0
        ]
        participation = len(usable) / eligible if eligible > 0 else (1.0 if usable else 0.0)
        if not usable:
            return ConvictionResult(
                direction="NEUTRAL", conviction=0.0, D=0.0,
                P=participation, G="contested", voters=list(votes),
            )
        score = (
            sum(float(v["direction"]) * float(v["confidence"]) for v in usable)
            / len(usable)
        )
        d = score * participation
        conviction = min(abs(d), 1.0)
        direction = "NEUTRAL"
        if d > _DIRECTION_THRESHOLD:
            direction = "UP"
        elif d < -_DIRECTION_THRESHOLD:
            direction = "DOWN"
        signs = {1.0 if float(v["direction"]) > 0 else -1.0 for v in usable}
        grouping = "unanimous" if len(signs) == 1 else "contested"
        return ConvictionResult(
            direction=direction, conviction=conviction, D=d,
            P=participation, G=grouping, voters=list(votes),
        )
