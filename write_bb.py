with open('src/shettyxtreme/data/pipeline/bar_builder.py', 'w') as f:
    f.write('''"""Bar aggregation engine - builds 1m/5m/15m/60m bars from ticks.

Listens for Tick events on the EventBus, aggregates ticks into OHLCV bars
at multiple timeframes, publishes completed bars onto the EventBus, and
persists them via TimeSeriesStore.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from shettyxtreme.core.data_models import Bar, Tick
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.core.storage import TimeSeriesStore

logger = logging.getLogger(__name__)

TIMEFRAMES = [1, 5, 15, 60]


class BarBuilderState:
    """In-memory aggregation state for a single symbol+timeframe."""

    __slots__ = ("open_", "high", "low", "close", "volume", "oi",
                 "period_start", "period_end", "tick_count")

    def __init__(self, period_start: datetime, period_end: datetime) -> None:
        self.open_: Optional[float] = None
        self.high: float = 0.0
        self.low: float = float("inf")
        self.close: float = 0.0
        self.volume: int = 0
        self.oi: Optional[int] = None
        self.period_start = period_start
        self.period_end = period_end
        self.tick_count: int = 0

    def apply_tick(self, tick: Tick) -> None:
        """Update OHLCV state from a tick."""
        ltp = tick.ltp
        if self.open_ is None:
            self.open_ = ltp
            self.high = ltp
            self.low = ltp
        self.high = max(self.high, ltp)
        self.low = min(self.low, ltp)
        self.close = ltp
        self.volume += max(0, tick.volume)
        self.tick_count += 1
        if tick.oi is not None:
            self.oi = tick.oi

    def is_complete(self, tick_time: datetime) -> bool:
        """Check if a tick timestamp falls in the next period."""
        return tick_time >= self.period_end

    def build_bar(self, symbol: str, exchange: str, timeframe: str) -> Bar:
        """Build a Bar dataclass from accumulated state."""
        return Bar(
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            open=self.open_ or self.close or 0.0,
            high=self.high if self.high > 0 else self.close or 0.0,
            low=self.low if self.low != float("inf") else self.close or 0.0,
            close=self.close,
            volume=self.volume,
            timestamp=self.period_start,
            oi=self.oi,
        )


def floor_timestamp(dt: datetime, minutes: int) -> datetime:
    """Floor a datetime to the nearest timeframe boundary."""
    total_minutes = dt.hour * 60 + dt.minute
    remainder = total_minutes % minutes
    return dt.replace(
        minute=total_minutes - remainder,
        second=0, microsecond=0,
    )


class BarBuilder:
    """Aggregates ticks into OHLCV bars at multiple timeframes.

    Subscribes to MARKET_DATA_TICK events on the EventBus, accumulates
    OHLCV data per (symbol, timeframe), publishes completed bars to
    MARKET_DATA_BAR topic, and persists them via TimeSeriesStore.
    """

    def __init__(self, event_bus: EventBus, ts_store: TimeSeriesStore) -> None:
        self._event_bus = event_bus
        self._ts_store = ts_store
        self._state: dict[str, dict[int, BarBuilderState]] = defaultdict(dict)
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Subscribe to tick events and begin bar aggregation."""
        if self._running:
            logger.warning("BarBuilder already running")
            return
        self._running = True
        self._event_bus.subscribe(Topic.MARKET_DATA_TICK, self._on_tick)
        logger.info("BarBuilder started, subscribed to %s", Topic.MARKET_DATA_TICK.value)

    async def stop(self) -> None:
        """Unsubscribe and flush remaining bars."""
        self._running = False
        self._event_bus.unsubscribe(Topic.MARKET_DATA_TICK, self._on_tick)
        await self._flush_all()
        logger.info("BarBuilder stopped")

    async def _on_tick(self, event: Event) -> None:
        """Handle an incoming Tick event."""
        tick: Tick = event.data
        if not isinstance(tick, Tick):
            return
        for tf in TIMEFRAMES:
            state = self._get_or_create_state(tick, tf)
            if state.is_complete(tick.timestamp):
                await self._finalise_bar(tick.symbol, tick.exchange, tf, state, tick.timestamp)
                state = self._create_state(tick, tf)
                self._state[tick.symbol][tf] = state
            state.apply_tick(tick)

    def _get_or_create_state(self, tick: Tick, tf: int) -> BarBuilderState:
        """Get existing state for (symbol, tf) or create a new one."""
        if tf not in self._state[tick.symbol]:
            state = self._create_state(tick, tf)
            self._state[tick.symbol][tf] = state
            return state
        return self._state[tick.symbol][tf]

    def _create_state(self, tick: Tick, tf: int) -> BarBuilderState:
        """Create a new BarBuilderState for (symbol, tf) starting at tick time."""
        period_start = floor_timestamp(tick.timestamp, tf)
        period_end = period_start + timedelta(minutes=tf)
        state = BarBuilderState(period_start, period_end)
        state.apply_tick(tick)
        return state

    async def _finalise_bar(
        self, symbol: str, exchange: str, tf: int,
        state: BarBuilderState, next_tick_time: datetime,
    ) -> None:
        """Publish and persist a completed bar."""
        bar = state.build_bar(symbol, exchange, f"{tf}min")
        try:
            await self._event_bus.publish_nowait(
                Event(topic=Topic.MARKET_DATA_BAR, data=bar, source="bar_builder"),
            )
            self._ts_store.write_bar(
                symbol=bar.symbol, exchange=bar.exchange,
                timeframe=bar.timeframe, open_=bar.open,
                high=bar.high, low=bar.low, close=bar.close,
                volume=bar.volume, timestamp=bar.timestamp, oi=bar.oi,
            )
            logger.debug("Bar completed: %s %s @ %s", bar.symbol, bar.timeframe, bar.timestamp)
        except Exception:
            logger.exception("Failed to finalise bar for %s %s", symbol, tf)

    async def _flush_all(self) -> None:
        """Flush any in-progress bars (called on shutdown)."""
        for symbol, tfs in list(self._state.items()):
            for tf, state in list(tfs.items()):
                if state.tick_count > 0:
                    bar = state.build_bar(symbol, "NSE", f"{tf}min")
                    try:
                        await self._event_bus.publish_nowait(
                            Event(topic=Topic.MARKET_DATA_BAR, data=bar, source="bar_builder"),
                        )
                        self._ts_store.write_bar(
                            symbol=bar.symbol, exchange=bar.exchange,
                            timeframe=bar.timeframe, open_=bar.open,
                            high=bar.high, low=bar.low, close=bar.close,
                            volume=bar.volume, timestamp=bar.timestamp, oi=bar.oi,
                        )
                    except Exception:
                        logger.exception("Failed to flush bar for %s %s", symbol, tf)
        self._state.clear()

    async def health(self) -> dict[str, Any]:
        """Return current bar builder health."""
        symbol_count = len(self._state)
        total_states = sum(len(tfs) for tfs in self._state.values())
        return {"running": self._running, "symbols": symbol_count, "active_states": total_states}
''')
print('bar_builder.py written')
