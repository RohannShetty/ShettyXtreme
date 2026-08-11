"""Regression tests for RiskBusBridge risk honesty (fix #2).

The margin poller in terminal/api/app.py publishes real available margin via
RISK_DECISION. RiskBusBridge must NEVER publish a placeholder margin from
ticks/position updates — those carry no margin, so any value the bridge emits
would clobber the poller's real figure moments later.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.intelligence.risk.bus_bridge import RiskBusBridge


async def _run_bridge(bus: EventBus, bridge: RiskBusBridge, event: Event) -> list[Event]:
    """Start bus+bridge, publish one event, drain until bridge replies."""
    received: list[Event] = []

    async def spy(ev: Event) -> None:
        received.append(ev)

    await bridge.start()
    bus.subscribe(Topic.RISK_DECISION, spy)
    bus_task = asyncio.create_task(bus.start())
    try:
        await bus.publish(event)
        for _ in range(100):
            if received:
                break
            await asyncio.sleep(0.02)
        assert received, "RiskBusBridge never published a RISK_DECISION"
        return received
    finally:
        await bridge.stop()
        await bus.stop()
        bus_task.cancel()
        try:
            await bus_task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_tick_does_not_publish_fabricated_margin() -> None:
    """A tick must not publish margin_available — ticks don't carry margin.

    Regression: the bridge initialized _margin_available to 0.0 and published
    it in every RISK_DECISION, overwriting the poller's real margin with 0.0.
    """
    bus = EventBus()
    bridge = RiskBusBridge(bus)
    received = await _run_bridge(
        bus,
        bridge,
        Event(Topic.MARKET_DATA_TICK, {"symbol": "NIFTY", "ltp": 24000.0}, source="test"),
    )

    decision = received[0].data
    assert "margin_available" not in decision


@pytest.mark.asyncio
async def test_position_update_does_not_publish_fabricated_margin() -> None:
    """Position updates also must not carry a placeholder margin."""
    bus = EventBus()
    bridge = RiskBusBridge(bus)
    received = await _run_bridge(
        bus,
        bridge,
        Event(
            Topic.POSITION_CHANGED,
            {"symbol": "NIFTY", "daily_pnl": -2000.0, "margin_used": 100000.0},
            source="test",
        ),
    )

    decision = received[0].data
    assert decision["daily_pnl"] == -2000.0
    assert decision["margin_used"] == 100000.0
    assert "margin_available" not in decision


@pytest.mark.asyncio
async def test_tick_with_real_margin_source_is_published() -> None:
    """Only a real margin source updates _margin_available (the guard)."""
    bus = EventBus()
    bridge = RiskBusBridge(bus)
    received = await _run_bridge(
        bus,
        bridge,
        Event(
            Topic.MARKET_DATA_TICK,
            {"symbol": "NIFTY", "ltp": 24000.0, "margin_available": 250000.0},
            source="real_source",
        ),
    )

    decision = received[0].data
    assert decision["margin_available"] == 250000.0


@pytest.mark.asyncio
async def test_decision_after_real_margin_keeps_value() -> None:
    """Once real margin is known, later margin-less ticks keep it, not 0.0."""
    bus = EventBus()
    bridge = RiskBusBridge(bus)
    await bridge.start()
    received: list[Event] = []

    async def spy(ev: Event) -> None:
        received.append(ev)

    bus.subscribe(Topic.RISK_DECISION, spy)
    bus_task = asyncio.create_task(bus.start())
    try:
        # First, a real source reports margin.
        await bus.publish(Event(
            Topic.MARKET_DATA_TICK,
            {"symbol": "NIFTY", "ltp": 24000.0, "margin_available": 250000.0},
            source="real_source",
        ))
        # Then a plain market tick with no margin follows.
        await bus.publish(Event(
            Topic.MARKET_DATA_TICK,
            {"symbol": "NIFTY", "ltp": 24100.0},
            source="test",
        ))
        for _ in range(200):
            if len(received) >= 2:
                break
            await asyncio.sleep(0.02)

        assert len(received) >= 2, "expected two RISK_DECISION events"
        # The second decision must not regress the real margin.
        second = received[1].data
        assert "margin_available" not in second or second["margin_available"] != 0.0
    finally:
        await bridge.stop()
        await bus.stop()
        bus_task.cancel()
        try:
            await bus_task
        except (asyncio.CancelledError, Exception):
            pass
