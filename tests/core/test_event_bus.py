
"""Integration tests for EventBus."""

import pytest
from shettyxtreme.core.event_bus import Event, Topic
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_subscribe_and_publish(event_bus):
    handler = AsyncMock()
    topic = Topic.MARKET_DATA_TICK
    event_bus.subscribe(topic, handler)

    event = Event(
        topic=topic,
        data={"symbol": "RELIANCE", "ltp": 2500},
        source="test",
    )
    await event_bus.publish(event)

    import asyncio
    task = asyncio.create_task(event_bus.start())
    await asyncio.sleep(0.05)
    await event_bus.stop()
    await task

    handler.assert_awaited()  # verify handler was called at least once


@pytest.mark.asyncio
async def test_unsubscribe(event_bus):
    handler = AsyncMock()
    topic = Topic.SIGNAL_GENERATED
    event_bus.subscribe(topic, handler)
    event_bus.unsubscribe(topic, handler)

    event = Event(topic=topic, data={"signal": "BUY"}, source="test")
    await event_bus.publish(event)

    import asyncio
    task = asyncio.create_task(event_bus.start())
    await asyncio.sleep(0.05)
    await event_bus.stop()
    await task

    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_multiple_subscribers_same_topic(event_bus):
    handler1 = AsyncMock()
    handler2 = AsyncMock()
    topic = Topic.ORDER_FILLED
    event_bus.subscribe(topic, handler1)
    event_bus.subscribe(topic, handler2)

    event = Event(topic=topic, data={"order_id": "123"}, source="test")
    await event_bus.publish(event)

    import asyncio
    task = asyncio.create_task(event_bus.start())
    await asyncio.sleep(0.05)
    await event_bus.stop()
    await task

    handler1.assert_awaited_once_with(event)
    handler2.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_error_in_one_handler_does_not_block_others(event_bus):
    failing_handler = AsyncMock(side_effect=ValueError("boom"))
    good_handler = AsyncMock()
    topic = Topic.RISK_ALERT
    event_bus.subscribe(topic, failing_handler)
    event_bus.subscribe(topic, good_handler)

    event = Event(topic=topic, data={"message": "risk"}, source="test")
    await event_bus.publish(event)

    import asyncio
    task = asyncio.create_task(event_bus.start())
    await asyncio.sleep(0.05)
    await event_bus.stop()
    await task

    failing_handler.assert_awaited()  # verify handler was called at least once
    good_handler.assert_awaited()  # verify handler was called at least once


@pytest.mark.asyncio
async def test_publish_nowait(event_bus):
    handler = AsyncMock()
    topic = Topic.SYSTEM_STATUS
    event_bus.subscribe(topic, handler)

    event = Event(topic=topic, data={"status": "ok"}, source="test")
    await event_bus.publish_nowait(event)

    import asyncio
    task = asyncio.create_task(event_bus.start())
    await asyncio.sleep(0.05)
    await event_bus.stop()
    await task

    handler.assert_awaited()  # verify handler was called at least once


@pytest.mark.asyncio
async def test_subscriber_count(event_bus):
    handler1 = AsyncMock()
    handler2 = AsyncMock()
    assert event_bus.subscriber_count == 0

    event_bus.subscribe(Topic.MARKET_DATA_TICK, handler1)
    assert event_bus.subscriber_count == 1

    event_bus.subscribe(Topic.ORDER_PLACED, handler2)
    assert event_bus.subscriber_count == 2


@pytest.mark.asyncio
async def test_event_timestamp_is_utc(event_bus):
    from datetime import timezone
    event = Event(
        topic=Topic.MARKET_DATA_TICK,
        data={},
        source="test",
    )
    assert event.timestamp.tzinfo is not None
    assert event.timestamp.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_different_topic_no_delivery(event_bus):
    handler = AsyncMock()
    event_bus.subscribe(Topic.ORDER_PLACED, handler)

    event = Event(
        topic=Topic.MARKET_DATA_TICK, data={}, source="test",
    )
    await event_bus.publish(event)

    import asyncio
    task = asyncio.create_task(event_bus.start())
    await asyncio.sleep(0.05)
    await event_bus.stop()
    await task

    handler.assert_not_awaited()
