"""Micro Momentum Voter — short-term EMA crossover.

Uses EMA(9) vs EMA(21):
  - EMA(9) > EMA(21) → bullish momentum
  - EMA(9) < EMA(21) → bearish momentum
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import Vote, voter


@voter(name="micro_voter", weight=1.0)
def micro_vote(
    features: dict[str, float],
    regime: Regime,
    options_context: dict[str, Any],
) -> Vote:
    """Vote based on short-term EMA crossover.

    Args:
        features: Must include 'ema_9' and 'ema_21'.
        regime: Current market regime.
        options_context: Not used.

    Returns:
        Vote with direction based on EMA crossover momentum.
    """
    ema_9 = features.get("ema_9") or features.get("ema")
    ema_21 = features.get("ema_21")

    if ema_9 is None or ema_21 is None or ema_21 == 0:
        return Vote(direction=0.0, confidence=0.0, weight=1.0, name="micro_voter")

    spread_pct = abs(ema_9 - ema_21) / ema_21

    if ema_9 > ema_21 and spread_pct > 0.001:
        direction = 1.0
    elif ema_9 < ema_21 and spread_pct > 0.001:
        direction = -1.0
    else:
        return Vote(direction=0.0, confidence=0.0, weight=1.0, name="micro_voter")

    # Confidence scales with spread
    confidence = min(spread_pct * 50.0, 0.85)
    return Vote(direction=direction, confidence=confidence, weight=1.0, name="micro_voter")
