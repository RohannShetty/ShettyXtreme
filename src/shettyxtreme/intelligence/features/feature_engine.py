"""Streaming feature computation — indicators and FeatureEngine."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from shettyxtreme.core.data_models.market_data import Tick
from shettyxtreme.core.event_bus import Event, EventBus, Topic

STALE_THRESHOLD_SECONDS = 10.0


@dataclass
class Feature:
    name: str
    value: float
    timestamp: float = field(default_factory=lambda: 0.0)


@dataclass
class FeaturesComputed:
    features: dict[str, float]
    stale: bool = False


class FeatureEngine:
    def __init__(
        self,
        event_bus: EventBus,
        symbol: str = "UNKNOWN",
        max_age_seconds: float = STALE_THRESHOLD_SECONDS,
    ) -> None:
        self.event_bus = event_bus
        self.symbol = symbol
        self.max_age_seconds = max_age_seconds
        self._indicators: dict[str, Any] = {}
        self._plugins: dict[str, Callable[[Tick], list[Feature]]] = {}
        self.features: dict[str, float] = {}
        #: Epoch seconds of the last FRESH (non-stale) tick that updated features.
        #: 0.0 means no fresh data has ever been processed. Consumers (SignalEngine)
        #: use this to detect stale feature snapshots at their own boundary.
        self.last_update: float = 0.0

    def register(self, name: str, indicator: Any) -> None:
        self._indicators[name] = indicator

    def register_plugin(self, name: str, plugin: Callable[[Tick], list[Feature]]) -> None:
        self._plugins[name] = plugin

    def get_indicator(self, name: str) -> Any | None:
        return self._indicators.get(name)

    @property
    def indicator_names(self) -> list[str]:
        return list(self._indicators.keys())

    async def process_tick(self, tick: Tick) -> None:
        now = time.time()
        tick_ts = tick.timestamp.timestamp() if hasattr(tick.timestamp, 'timestamp') else float(tick.timestamp)
        stale = (now - tick_ts) > self.max_age_seconds

        if stale:
            fc = FeaturesComputed(features={}, stale=True)
        else:
            for name, indicator in self._indicators.items():
                result = indicator.update(tick)
                if result is not None:
                    self.features[name] = result
                elif indicator.value is not None:
                    self.features[name] = indicator.value
            self.last_update = now
            fc = FeaturesComputed(features=dict(self.features), stale=False)

        await self.event_bus.publish(Event(Topic.FEATURES_COMPUTED, fc, source="feature_engine"))
