"""Shadow OI voter with time-of-day bucketing (contrarian).

Normalizes OI by time bucket (morning/midday/afternoon) before applying
contrarian logic, separate from the real options_flow_voter. Standalone.
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import Vote

_BUCKET_FACTOR: dict[str, float] = {
    "morning": 1.2,
    "midday": 1.0,
    "afternoon": 0.8,
}


def shadow_time_bucketed_oi_vote(
    features: dict[str, float],
    regime: Regime,
    options_context: dict[str, Any],
) -> Vote:
    """Vote using OI contrarian logic normalized by time-of-day bucket."""
    oi = features.get("oi")
    time_bucket = features.get("time_bucket") or options_context.get("time_bucket")
    if oi is None or time_bucket is None:
        return Vote(
            direction=0.0, confidence=0.0, weight=1.0, name="shadow_time_bucketed_oi"
        )

    factor = _BUCKET_FACTOR.get(str(time_bucket), 1.0)
    norm_oi = oi * factor

    if norm_oi > 1.0:
        direction = -1.0  # contrarian: excessive OI build-up signals reversal
        confidence = min((norm_oi - 1.0) * 0.5, 0.9)
    elif norm_oi < 0.5:
        direction = 1.0
        confidence = min((0.5 - norm_oi) * 0.5, 0.9)
    else:
        direction = 0.0
        confidence = 0.0

    return Vote(
        direction=direction,
        confidence=confidence,
        weight=1.0,
        name="shadow_time_bucketed_oi",
    )
