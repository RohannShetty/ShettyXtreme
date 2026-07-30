"""EventBus bridge for RegimeClassifier — publishes REGIME_CHANGED on feature updates."""
from __future__ import annotations

import logging

from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.intelligence.regime.regime_classifier import RegimeClassifier

logger = logging.getLogger(__name__)


class RegimeBusBridge:
    """Bridges RegimeClassifier to the EventBus.

    Subscribes to FEATURES_COMPUTED, runs classification,
    and publishes REGIME_CHANGED when the regime transitions.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._classifier = RegimeClassifier()
        self._prev_regime = None

    async def start(self) -> None:
        self._event_bus.subscribe(Topic.FEATURES_COMPUTED, self._on_features)
        logger.info("RegimeBusBridge started")

    async def stop(self) -> None:
        self._event_bus.unsubscribe(Topic.FEATURES_COMPUTED, self._on_features)
        logger.info("RegimeBusBridge stopped")

    async def _on_features(self, event: Event) -> None:
        fc = event.data
        features = getattr(fc, "features", None)
        if not features or getattr(fc, "stale", False):
            return

        regime = self._classifier.classify(features)
        confidence = self._classifier.compute_confidence(features, regime)
        is_transition = self._prev_regime is not None and self._prev_regime != regime
        self._prev_regime = regime

        await self._event_bus.publish(
            Event(
                topic=Topic.REGIME_CHANGED,
                data={
                    "regime": str(regime),
                    "confidence": confidence,
                    "transition": is_transition,
                    "adx": features.get("adx"),
                    "di_plus": features.get("di_plus"),
                    "di_minus": features.get("di_minus"),
                },
                source="regime_bus_bridge",
            )
        )
        logger.debug(
            "Regime changed: %s (confidence=%.2f, transition=%s)",
            regime,
            confidence,
            is_transition,
        )
