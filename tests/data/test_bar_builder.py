"""Tests for the bar aggregation engine (BarBuilder)."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from shettyxtreme.core.data_models import Bar, Tick
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.data.pipeline.bar_builder import (
    BarBuilder,
    BarBuilderState,
    floor_timestamp,
)

# Helpers

def _make_tick(
    symbol: str = "NIFTY",
    ltp: float = 100.0,
    volume: int = 10,
    timestamp: datetime | None = None,
    exchange: str = "NFO",
) -> Tick:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    return Tick(
        symbol=symbol, exchange=exchange, ltp=ltp, volume=volume,
        timestamp=timestamp,
    )

def _make_event(tick: Tick) -> Event:
    return Event(topic=Topic.MARKET_DATA_TICK, data=tick, source="test")

class TestFloorTimestamp:
    def test_1m_floor(self):
        t = datetime(2026, 7, 12, 10, 30, 45, tzinfo=timezone.utc)
        floored = floor_timestamp(t, 1)
        assert floored.minute == 30
        assert floored.second == 0

    def test_5m_floor(self):
        t = datetime(2026, 7, 12, 10, 33, 15, tzinfo=timezone.utc)
        floored = floor_timestamp(t, 5)
        assert floored.minute == 30
        assert floored.second == 0

    def test_15m_floor(self):
        t = datetime(2026, 7, 12, 10, 41, 0, tzinfo=timezone.utc)
        floored = floor_timestamp(t, 15)
        assert floored.minute == 30

class TestBarBuilder:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        eb = EventBus()
        bb = BarBuilder(event_bus=eb, ts_store=None)
        task = asyncio.create_task(bb.start())
        await asyncio.sleep(0.05)
        await bb.stop()
        await task
        assert True

    @pytest.mark.asyncio
    async def test_bar_boundary_tick_not_double_counted(self):
        """F-INTEL-002: a tick that crosses a bar boundary must be applied
        exactly once — to the finalized bar it closes and to the new bar it
        opens, never twice to either."""
        eb = EventBus()
        ts_store = MagicMock()
        bb = BarBuilder(event_bus=eb, ts_store=ts_store)
        bars: list[Bar] = []

        async def _capture(event: Event) -> None:
            bars.append(event.data)

        eb.subscribe(Topic.MARKET_DATA_BAR, _capture)
        bus_task = asyncio.create_task(eb.start())

        # Tick inside the 10:30 bar, then a tick exactly at the 10:31 boundary.
        t0 = datetime(2026, 7, 12, 10, 30, 30, tzinfo=timezone.utc)
        t1 = datetime(2026, 7, 12, 10, 31, 0, tzinfo=timezone.utc)
        await bb._on_tick(_make_event(_make_tick(ltp=100.0, volume=10, timestamp=t0)))
        await bb._on_tick(_make_event(_make_tick(ltp=101.0, volume=5, timestamp=t1)))

        await asyncio.sleep(0.05)
        await eb.stop()
        await bus_task

        # The 10:30 bar must carry only the pre-boundary tick (volume 10),
        # not the boundary tick added on top (10 + 5) or doubled (20).
        assert len(bars) == 1
        assert bars[0].volume == 10
        assert bars[0].timestamp == floor_timestamp(t0, 1)
        # The in-progress 10:31 bar holds the boundary tick exactly once.
        state = bb._state["NIFTY"][1]
        assert state.volume == 5
        assert state.tick_count == 1
