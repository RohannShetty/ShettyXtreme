"""Tests for the bar aggregation engine (BarBuilder).

Covers 1m/5m/15m/60m bar construction from synthetic ticks, gap
tolerance, and EventBus publishing behaviour.
"""

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tick(
    symbol: str = "11536",
    ltp: float = 100.0,
    volume: int = 10,
    timestamp: datetime | None = None,
    exchange: str = "NSE",
) -> Tick:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    return Tick(
        symbol=symbol, exchange=exchange, ltp=ltp, volume=volume,
        timestamp=timestamp,
    )


def _make_event(tick: Tick) -> Event:
    return Event(topic=Topic.MARKET_DATA_TICK, data=tick, source="test")
