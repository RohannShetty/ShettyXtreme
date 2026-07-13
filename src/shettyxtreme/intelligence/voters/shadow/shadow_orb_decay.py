"""Shadow ORB voter with time-decay confidence.

Like the real orb_voter (breakout beyond orb_high/orb_low) but EARLY breakouts
(time_bucket == 'morning') receive higher confidence than LATE breakouts.
Standalone; not registered globally.
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import Vote

_DECAY: dict[str, float] = {
    "morning": 1.0,
    "midday": 0.7,
    "afternoon": 0.4,
}


def shadow_orb_decay_vote(
    features: dict[str, float],
    regime: Regime,
    options_context: dict[str, Any],
) -> Vote:
    """Vote on ORB breakout, with confidence decayed by breakout timing."""
    orb_high = features.get("orb_high")
    orb_low = features.get("orb_low")
    current_price = features.get("current_price") or features.get("ltp")
    time_bucket = features.get("time_bucket") or options_context.get("time_bucket")
    if orb_high is None or orb_low is None or current_price is None:
        return Vote(
            direction=0.0, confidence=0.0, weight=1.0, name="shadow_orb_decay"
        )

    if current_price > orb_high:
        direction = 1.0
        distance = (current_price - orb_high) / orb_high
    elif current_price < orb_low:
        direction = -1.0
        distance = (orb_low - current_price) / orb_low
    else:
        return Vote(
            direction=0.0, confidence=0.0, weight=1.0, name="shadow_orb_decay"
        )

    confidence = min(abs(distance) * 10.0, 0.8)
    decay = _DECAY.get(str(time_bucket), 0.7)
    confidence = min(confidence * decay, 1.0)
    return Vote(
        direction=direction,
        confidence=confidence,
        weight=1.0,
        name="shadow_orb_decay",
    )
