"""Opening Range Breakout (ORB) Voter.

First 15-minute range establishes the opening range.
A breakout beyond this range is directional:
  - Price above range high → bullish
  - Price below range low → bearish
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import Vote, voter


@voter(name="orb_voter", weight=1.0)
def orb_vote(
    features: dict[str, float],
    regime: Regime,
    options_context: dict[str, Any],
) -> Vote:
    """Vote based on opening range breakout.

    Args:
        features: Must include 'orb_high', 'orb_low', 'current_price'.
        regime: Current market regime.
        options_context: Not used.

    Returns:
        Vote with direction based on ORB breakout.
    """
    orb_high = features.get("orb_high")
    orb_low = features.get("orb_low")
    current_price = features.get("current_price") or features.get("ltp")

    if orb_high is None or orb_low is None or current_price is None:
        return Vote(direction=0.0, confidence=0.0, weight=1.0, name="orb_voter")

    if current_price > orb_high:
        direction = 1.0
        distance = (current_price - orb_high) / orb_high
    elif current_price < orb_low:
        direction = -1.0
        distance = (orb_low - current_price) / orb_low
    else:
        return Vote(direction=0.0, confidence=0.0, weight=1.0, name="orb_voter")

    # Confidence scales with distance from range (capped)
    confidence = min(abs(distance) * 10.0, 0.8)
    return Vote(direction=direction, confidence=confidence, weight=1.0, name="orb_voter")
