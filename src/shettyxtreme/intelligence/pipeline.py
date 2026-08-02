"""Live intelligence pipeline wiring — ticks → features → regime → signal.

This module is the runtime wiring the audit found missing: FeatureEngine and
SignalEngine were never instantiated, so FEATURES_COMPUTED / SIGNAL_V2 never
fired, the RegimeBusBridge was starved, and the intelligence endpoints served
hard-coded defaults.

Event flow once subscribed:

    MARKET_DATA_TICK ──► FeatureEngine ──► FEATURES_COMPUTED
                                              ├─► RegimeBusBridge ──► REGIME_CHANGED ──► projections
                                              └─► SignalEngine  ─────► SIGNAL_V2     ──► projections

Everything is event-driven (computed on tick) — no timers.
"""
from __future__ import annotations

import logging
from dataclasses import asdict

from shettyxtreme.core.data_models.market_data import Tick
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.intelligence.features import ADX, ATR, EMA, RSI, FeatureEngine
from shettyxtreme.intelligence.features.adapters import AttributeIndicator
from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import SignalEngine
from shettyxtreme.intelligence import voters  # noqa: F401 — imports run @voter decorators

logger = logging.getLogger(__name__)

#: Engine symbol label; features are computed across the watchlist feed.
_PIPELINE_SYMBOL = "NIFTY"


class IntelligencePipeline:
    """Wires FeatureEngine + SignalEngine to an EventBus and keeps them live.

    Voters come from two sources (judgment call, see P4a report):
    1. the package's decorator registry (options_flow_voter, micro_voter,
       breadth_voter — imported above so their ``@voter`` registrations run),
       synced via ``consume_registry=True``; 3-arg voters are wrapped by the
       engine's ShadowAdapter and vote under the engine's live regime.
    2. the two exported 1-arg voters (orb_voter, iv_rank_voter) that are NOT
       decorator-registered — registered explicitly on the engine.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self.feature_engine = FeatureEngine(event_bus, symbol=_PIPELINE_SYMBOL)
        self._register_indicators()
        self.signal_engine = SignalEngine(self.feature_engine, consume_registry=True)
        self.signal_engine.register_voter("orb", voters.orb_voter, weight=1.0)
        self.signal_engine.register_voter("iv_rank", voters.iv_rank_voter, weight=1.0)
        self._subscribed = False

    def _register_indicators(self) -> None:
        """Register the feature set the regime classifier + voters consume."""
        adx = ADX(period=14)
        self.feature_engine.register("adx", adx)
        self.feature_engine.register("di_plus", AttributeIndicator(adx, "di_plus"))
        self.feature_engine.register("di_minus", AttributeIndicator(adx, "di_minus"))
        self.feature_engine.register("atr", ATR(period=14))
        self.feature_engine.register("ema_9", EMA(period=9))
        self.feature_engine.register("ema_21", EMA(period=21))
        self.feature_engine.register("rsi", RSI(period=14))

    def subscribe(self) -> None:
        if self._subscribed:
            return
        self._bus.subscribe(Topic.MARKET_DATA_TICK, self._on_tick)
        self._bus.subscribe(Topic.FEATURES_COMPUTED, self._on_features)
        self._bus.subscribe(Topic.REGIME_CHANGED, self._on_regime_changed)
        self._subscribed = True
        logger.info(
            "IntelligencePipeline subscribed (voters=%s)",
            sorted(self.signal_engine.voters),
        )

    def unsubscribe(self) -> None:
        if not self._subscribed:
            return
        self._bus.unsubscribe(Topic.MARKET_DATA_TICK, self._on_tick)
        self._bus.unsubscribe(Topic.FEATURES_COMPUTED, self._on_features)
        self._bus.unsubscribe(Topic.REGIME_CHANGED, self._on_regime_changed)
        self._subscribed = False

    @property
    def voter_names(self) -> list[str]:
        return sorted(self.signal_engine.voters)

    async def _on_tick(self, event: Event) -> None:
        tick = event.data
        if not isinstance(tick, Tick):
            logger.warning("IntelligencePipeline: non-Tick payload on %s", event.topic.value)
            return
        try:
            await self.feature_engine.process_tick(tick)
        except Exception:
            logger.exception("feature computation failed for %s", tick.symbol)

    async def _on_features(self, event: Event) -> None:
        fc = event.data
        features = getattr(fc, "features", None)
        if not features or getattr(fc, "stale", False):
            return
        try:
            signal = self.signal_engine.compute_signal()
        except Exception:
            logger.exception("signal computation failed")
            return
        await self._bus.publish(
            Event(
                topic=Topic.SIGNAL_V2,
                data={
                    "direction": signal.direction.name,
                    "conviction": signal.conviction,
                    "D": signal.D,
                    "P": signal.P,
                    "G": signal.G,
                    "voters": [asdict(v) for v in signal.voters],
                    "timestamp": signal.timestamp,
                },
                source="signal_engine",
            )
        )

    async def _on_regime_changed(self, event: Event) -> None:
        """Keep the engine's regime live so 3-arg voters vote under it."""
        d = event.data if isinstance(event.data, dict) else {}
        raw = d.get("regime")
        if not raw:
            return
        try:
            self.signal_engine.regime = Regime(raw)
        except ValueError:
            logger.warning("IntelligencePipeline: unknown regime value %r", raw)
