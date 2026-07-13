"""Options Flow Voter — PCR contrarian with OI time-of-day normalization.

PCR > 1.3 → bullish (high puts = fear = contrarian buy)
PCR < 0.7 → bearish (high calls = greed = contrarian sell)

OI is normalized by time-of-day percentile rank within time bucket,
not raw OI values.
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import Vote, voter

_PCR_BULLISH_THRESHOLD = 1.3
_PCR_BEARISH_THRESHOLD = 0.7


@voter(name="options_flow_voter", weight=1.0)
def options_flow_vote(
    features: dict[str, float],
    regime: Regime,
    options_context: dict[str, Any],
) -> Vote:
    """Vote based on PCR and OI flow.

    Args:
        features: Must include 'pcr' key. Optional 'oi_percentile_rank'.
        regime: Current market regime (not used directly here).
        options_context: May contain 'symbol', 'time_bucket'.

    Returns:
        Vote with direction based on PCR contrarian logic.
    """
    pcr = features.get("pcr", 1.0)

    # Direction
    if pcr > _PCR_BULLISH_THRESHOLD:
        direction = 1.0  # Bullish (contrarian)
    elif pcr < _PCR_BEARISH_THRESHOLD:
        direction = -1.0  # Bearish (contrarian)
    else:
        return Vote(direction=0.0, confidence=0.0, weight=1.0, name="options_flow_voter")

    # Confidence: how far from neutral
    if direction > 0:
        distance = (pcr - _PCR_BULLISH_THRESHOLD) / _PCR_BULLISH_THRESHOLD
    else:
        distance = (_PCR_BEARISH_THRESHOLD - pcr) / _PCR_BEARISH_THRESHOLD
    confidence = min(abs(distance) * 0.5, 0.9)

    # OI percentile rank adjustment
    oi_pct = features.get("oi_percentile_rank", 50.0)
    if oi_pct > 80.0:
        confidence = min(confidence + 0.15, 1.0)
    elif oi_pct < 20.0:
        confidence = max(confidence - 0.15, 0.1)

    return Vote(direction=direction, confidence=confidence, weight=1.0, name="options_flow_voter")
