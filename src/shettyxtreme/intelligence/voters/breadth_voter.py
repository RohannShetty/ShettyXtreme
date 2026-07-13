"""Breadth Voter — Advance/Decline ratio.

Uses market breadth (advancers / decliners) to gauge broad market sentiment.
Returns direction=0 if breadth data is not available in features.
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import Vote, voter

_AD_RATIO_BULLISH = 1.5
_AD_RATIO_BEARISH = 0.67


@voter(name="breadth_voter", weight=0.8)
def breadth_vote(
    features: dict[str, float],
    regime: Regime,
    options_context: dict[str, Any],
) -> Vote:
    """Vote based on advance/decline ratio.

    Args:
        features: Optional 'advance_decline_ratio' key.
                  If not present, returns neutral vote.
        regime: Current market regime.
        options_context: Not used.

    Returns:
        Vote with direction based on market breadth.
    """
    ad_ratio = features.get("advance_decline_ratio")
    if ad_ratio is None:
        return Vote(direction=0.0, confidence=0.0, weight=0.8, name="breadth_voter")

    if ad_ratio > _AD_RATIO_BULLISH:
        direction = 1.0
        distance = (ad_ratio - _AD_RATIO_BULLISH) / _AD_RATIO_BULLISH
    elif ad_ratio < _AD_RATIO_BEARISH:
        direction = -1.0
        distance = (_AD_RATIO_BEARISH - ad_ratio) / _AD_RATIO_BEARISH
    else:
        return Vote(direction=0.0, confidence=0.0, weight=0.8, name="breadth_voter")

    confidence = min(abs(distance) * 0.4, 0.7)
    return Vote(direction=direction, confidence=confidence, weight=0.8, name="breadth_voter")
