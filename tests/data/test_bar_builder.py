"""Tests for the bar aggregation engine (BarBuilder)."""

import asyncio
from datetime import datetime, timedelta, timezone

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
        bb.stop()
        await task
        assert True
