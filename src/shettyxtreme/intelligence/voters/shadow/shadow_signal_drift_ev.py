"""Shadow signal-drift EV voter — expected value from drift vs volatility.

Direction = sign(signal_drift); confidence scaled by |signal_drift|/volatility.
Standalone; not registered globally.
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import Vote


def shadow_signal_drift_ev_vote(
    features: dict[str, float],
    regime: Regime,
    options_context: dict[str, Any],
) -> Vote:
    """Vote using signal drift expected value relative to volatility."""
    signal_drift = features.get("signal_drift")
    volatility = features.get("volatility")
    if signal_drift is None or volatility is None or volatility == 0.0:
        return Vote(
            direction=0.0, confidence=0.0, weight=1.0, name="shadow_signal_drift_ev"
        )

    direction = 1.0 if signal_drift > 0 else (-1.0 if signal_drift < 0 else 0.0)
    confidence = min(abs(signal_drift) / volatility, 1.0)
    return Vote(
        direction=direction,
        confidence=confidence,
        weight=1.0,
        name="shadow_signal_drift_ev",
    )
