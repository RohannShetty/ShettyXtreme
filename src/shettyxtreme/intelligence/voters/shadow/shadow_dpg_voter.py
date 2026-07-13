"""Shadow DPG tier router — de-inverted directional participation grouping.

Direction = sign of (directional_score * participation * (1 - disagreement))
with CORRECT (non-inverted) logic. Standalone; not registered globally.
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import Vote


def shadow_dpg_vote(
    features: dict[str, float],
    regime: Regime,
    options_context: dict[str, Any],
) -> Vote:
    """Vote using participation-weighted, disagreement-adjusted direction."""
    directional_score = features.get("directional_score")
    participation = features.get("participation")
    disagreement = features.get("disagreement")
    if (
        directional_score is None
        or participation is None
        or disagreement is None
    ):
        return Vote(direction=0.0, confidence=0.0, weight=1.0, name="shadow_dpg_voter")

    score = directional_score * participation * (1.0 - disagreement)
    direction = 1.0 if score > 0 else (-1.0 if score < 0 else 0.0)
    confidence = min(abs(score), 1.0)
    return Vote(
        direction=direction,
        confidence=confidence,
        weight=1.0,
        name="shadow_dpg_voter",
    )
