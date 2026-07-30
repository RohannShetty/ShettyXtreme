"""Tests for scanner_data module — GapDetector, LogCollector, ClusterDetector."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from shettyxtreme.core.data_models import Tick
from shettyxtreme.core.event_bus.event_bus import Event, Topic
from shettyxtreme.terminal.api.scanner_data import (
    ClusterDetector,
    GapDetector,
    LogCollector,
)


@pytest.fixture
def bus():
    from shettyxtreme.core.event_bus.event_bus import EventBus
    return EventBus()


# ---------------------------------------------------------------------------
# GapDetector
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gap_detector_detects_gap():
    det = GapDetector()
    t1 = datetime(2025, 1, 2, 9, 0, tzinfo=UTC)
    t2 = datetime(2025, 1, 2, 9, 0, 1, tzinfo=UTC)

    tick1 = Event(Topic.MARKET_DATA_TICK, {"symbol": "RELIANCE", "ltp": 100.0, "open": 100.0}, timestamp=t1)
    tick2 = Event(Topic.MARKET_DATA_TICK, {"symbol": "RELIANCE", "ltp": 110.0, "open": 110.0}, timestamp=t2)

    await det.on_tick(tick1)
    await det.on_tick(tick2)

    assert len(det.gaps) == 1
    g = det.gaps[0]
    assert g["symbol"] == "RELIANCE"
    assert g["direction"] == "gap_up"
    assert g["gap_percent"] == pytest.approx(10.0, abs=0.1)


@pytest.mark.asyncio
async def test_gap_detector_detects_gap_tick_dataclass():
    det = GapDetector()
    t1 = datetime(2025, 1, 2, 9, 0, tzinfo=UTC)
    t2 = datetime(2025, 1, 2, 9, 0, 1, tzinfo=UTC)

    tick1 = Tick(symbol="RELIANCE", exchange="NSE", ltp=100.0, volume=1000, timestamp=t1, open=100.0)
    tick2 = Tick(symbol="RELIANCE", exchange="NSE", ltp=110.0, volume=1200, timestamp=t2, open=110.0)

    await det.on_tick(Event(Topic.MARKET_DATA_TICK, tick1, timestamp=t1))
    await det.on_tick(Event(Topic.MARKET_DATA_TICK, tick2, timestamp=t2))

    assert len(det.gaps) == 1
    g = det.gaps[0]
    assert g["symbol"] == "RELIANCE"
    assert g["direction"] == "gap_up"
    assert g["gap_percent"] == pytest.approx(10.0, abs=0.1)


@pytest.mark.asyncio
async def test_gap_detector_no_gap_small_move():
    det = GapDetector()
    t1 = datetime(2025, 1, 2, 9, 0, tzinfo=UTC)
    t2 = datetime(2025, 1, 2, 9, 0, 1, tzinfo=UTC)

    tick1 = Event(Topic.MARKET_DATA_TICK, {"symbol": "INFY", "ltp": 100.0, "open": 100.0}, timestamp=t1)
    tick2 = Event(Topic.MARKET_DATA_TICK, {"symbol": "INFY", "ltp": 100.3, "open": 100.3}, timestamp=t2)

    await det.on_tick(tick1)
    await det.on_tick(tick2)

    assert len(det.gaps) == 0


# ---------------------------------------------------------------------------
# LogCollector
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_collector_on_signal():
    lc = LogCollector()
    event = Event(
        Topic.SIGNAL_GENERATED,
        {"direction": "BULLISH", "conviction": 0.85},
        timestamp=datetime.now(UTC),
    )
    await lc.on_signal(event)

    assert len(lc.logs) == 1
    assert lc.logs[0]["log_type"] == "signal"
    assert "BULLISH" in lc.logs[0]["message"]


@pytest.mark.asyncio
async def test_log_collector_on_order():
    lc = LogCollector()
    event = Event(
        Topic.ORDER_PLACED,
        {"order_id": "ORD-001", "status": "placed"},
        timestamp=datetime.now(UTC),
    )
    await lc.on_order(event)

    assert len(lc.logs) == 1
    assert lc.logs[0]["log_type"] == "execution"
    assert "ORD-001" in lc.logs[0]["message"]


@pytest.mark.asyncio
async def test_log_collector_max_limit():
    lc = LogCollector()
    for i in range(501):
        event = Event(
            Topic.SIGNAL_GENERATED,
            {"direction": "BULLISH", "conviction": 0.5},
            timestamp=datetime.now(UTC),
        )
        await lc.on_signal(event)

    assert len(lc.logs) == 500


# ---------------------------------------------------------------------------
# ClusterDetector
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cluster_detector_single_signal():
    det = ClusterDetector()
    now = datetime.now(UTC)
    event = Event(
        Topic.SIGNAL_GENERATED,
        {"symbol": "TCS", "direction": "BULLISH"},
        timestamp=now,
    )
    await det.on_signal(event)

    assert len(det.clusters) == 0


@pytest.mark.asyncio
async def test_cluster_detector_multiple_signals():
    det = ClusterDetector()
    t1 = datetime(2025, 1, 2, 9, 0, tzinfo=UTC)
    t2 = datetime(2025, 1, 2, 9, 1, tzinfo=UTC)

    await det.on_signal(Event(
        Topic.SIGNAL_GENERATED,
        {"symbol": "TCS", "direction": "BULLISH"},
        timestamp=t1,
    ))
    await det.on_signal(Event(
        Topic.SIGNAL_GENERATED,
        {"symbol": "TCS", "direction": "BULLISH"},
        timestamp=t2,
    ))

    assert len(det.clusters) == 1
    c = det.clusters[0]
    assert c["symbol"] == "TCS"
    assert c["cluster_type"] == "multi_signal"
    assert c["source_count"] == 2
