"""Tests for the live intelligence pipeline wiring (P4a).

Proves the wiring the audit found missing: FeatureEngine + SignalEngine are
instantiated, live voters register, and a MARKET_DATA_TICK flows through
features → regime bridge → projections, with SIGNAL_V2 reaching subscribers.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from shettyxtreme.core.data_models.market_data import Tick
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.intelligence.pipeline import IntelligencePipeline
from shettyxtreme.intelligence.regime.bus_bridge import RegimeBusBridge
from shettyxtreme.terminal.projections import IntelligenceProjection

#: Live voters the package exports — decorator-registered only.
#: F-INTEL-001: orb_voter / iv_rank_voter stubs were removed from the registry —
#: they voted constant directions (DOWN / UP) on features that are never computed.
EXPECTED_VOTERS = {"options_flow_voter", "micro_voter", "breadth_voter"}


def _make_tick(ltp: float, high: float | None = None, low: float | None = None) -> Tick:
    return Tick(
        symbol="NIFTY",
        exchange="NSE",
        ltp=ltp,
        volume=100,
        timestamp=datetime.now(UTC),
        high=high,
        low=low,
    )


def _trending_ticks(count: int = 40) -> list[Tick]:
    """Monotonically rising ticks so ADX/EMA warm up and features populate."""
    return [
        _make_tick(100.0 + i, high=101.0 + i, low=99.0 + i)
        for i in range(count)
    ]


@pytest.mark.asyncio
async def test_pipeline_registers_all_live_voters() -> None:
    bus = EventBus()
    pipeline = IntelligencePipeline(bus)
    assert EXPECTED_VOTERS <= set(pipeline.signal_engine.voters)
    # F-INTEL-001 regression guard: the stub voters must not be registered —
    # with no real features backing them they voted constant directions and
    # dominated ~42% of the aggregate weight as noise.
    assert "orb" not in pipeline.signal_engine.voters
    assert "iv_rank" not in pipeline.signal_engine.voters
    # decorator-registered voters are synced through the registry
    assert "options_flow_voter" in pipeline.signal_engine.voters


@pytest.mark.asyncio
async def test_pipeline_registers_indicators() -> None:
    bus = EventBus()
    pipeline = IntelligencePipeline(bus)
    names = set(pipeline.feature_engine.indicator_names)
    assert {"adx", "di_plus", "di_minus", "atr", "ema_9", "ema_21", "rsi"} <= names


@pytest.mark.asyncio
async def test_tick_flow_reaches_regime_bridge_and_projection() -> None:
    """A tick must produce FEATURES_COMPUTED → REGIME_CHANGED → projection state."""
    bus = EventBus()
    pipeline = IntelligencePipeline(bus)
    pipeline.subscribe()
    bridge = RegimeBusBridge(bus)
    await bridge.start()
    proj = IntelligenceProjection()
    proj.subscribe(bus)

    bus_task = asyncio.create_task(bus.start())
    try:
        for tick in _trending_ticks():
            await bus.publish(Event(Topic.MARKET_DATA_TICK, tick, source="test"))
        # Drain the bus until the regime bridge has processed features.
        for _ in range(200):
            if proj.get_regime().get("adx") is not None:
                break
            await asyncio.sleep(0.05)
        regime = proj.get_regime()
        assert regime["adx"] is not None, "regime bridge never received features"
        assert regime["regime"] in (
            "trending_up", "trending_down", "range_bound", "volatile", "transition",
        )
        assert proj.has_data() is True
    finally:
        await bridge.stop()
        await bus.stop()
        bus_task.cancel()
        try:
            await bus_task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_signal_v2_reaches_projection() -> None:
    """SIGNAL_V2 must carry dict-shaped voters consumable by the router."""
    bus = EventBus()
    pipeline = IntelligencePipeline(bus)
    pipeline.subscribe()
    proj = IntelligenceProjection()
    proj.subscribe(bus)

    bus_task = asyncio.create_task(bus.start())
    try:
        for tick in _trending_ticks():
            await bus.publish(Event(Topic.MARKET_DATA_TICK, tick, source="test"))
        for _ in range(200):
            if proj.get_signal().get("voters"):
                break
            await asyncio.sleep(0.05)
        signal = proj.get_signal()
        assert signal["direction"] in ("UP", "DOWN", "NEUTRAL")
        voters = signal["voters"]
        assert voters, "signal should carry live voter votes"
        assert all(isinstance(v, dict) and "name" in v and "direction" in v for v in voters)
        assert {v["name"] for v in voters} <= EXPECTED_VOTERS | {"decorated_test"}
    finally:
        await bus.stop()
        bus_task.cancel()
        try:
            await bus_task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_stale_tick_publishes_no_signal() -> None:
    """A stale tick produces empty/stale features → no SIGNAL_V2 (honest idle)."""
    bus = EventBus()
    pipeline = IntelligencePipeline(bus)
    pipeline.subscribe()
    proj = IntelligenceProjection()
    proj.subscribe(bus)

    received: list[Event] = []

    async def spy(event: Any) -> None:
        received.append(event)

    bus.subscribe(Topic.SIGNAL_V2, spy)
    bus_task = asyncio.create_task(bus.start())
    try:
        import time
        stale_tick = _make_tick(100.0, high=101.0, low=99.0)
        stale_tick.timestamp = datetime.fromtimestamp(time.time() - 15, tz=UTC)
        await bus.publish(Event(Topic.MARKET_DATA_TICK, stale_tick, source="test"))
        await asyncio.sleep(0.2)
        assert received == []
        assert proj.has_data() is False
    finally:
        await bus.stop()
        bus_task.cancel()
        try:
            await bus_task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_regime_change_updates_engine_regime() -> None:
    """REGIME_CHANGED must flow into the engine so shadow voters vote live."""
    bus = EventBus()
    pipeline = IntelligencePipeline(bus)
    pipeline.subscribe()
    bus_task = asyncio.create_task(bus.start())
    try:
        await bus.publish(Event(
            Topic.REGIME_CHANGED,
            {"regime": "trending_up", "confidence": 0.8, "transition": False},
            source="test",
        ))
        await asyncio.sleep(0.1)
        assert pipeline.signal_engine.regime.value == "trending_up"
    finally:
        await bus.stop()
        bus_task.cancel()
        try:
            await bus_task
        except (asyncio.CancelledError, Exception):
            pass
