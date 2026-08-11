
"""Integration tests for EventBus."""

import asyncio
import logging

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


# --- F-CORE-002: the start() loop must survive sync handlers and raising handlers ---


@pytest.mark.asyncio
async def test_sync_handler_does_not_crash_loop(event_bus):
    received = []

    def sync_handler(event):
        received.append(event.data["seq"])

    topic = Topic.MARKET_DATA_TICK
    event_bus.subscribe(topic, sync_handler)

    for seq in range(3):
        await event_bus.publish_nowait(
            Event(topic=topic, data={"seq": seq}, source="test")
        )

    task = asyncio.create_task(event_bus.start())
    await asyncio.sleep(0.05)
    await event_bus.stop()
    await task

    assert received == [0, 1, 2]


@pytest.mark.asyncio
async def test_sync_handler_raising_does_not_crash_loop(event_bus):
    calls = []

    def bad_sync_handler(event):
        calls.append(("bad", event.data["seq"]))
        raise ValueError("sync boom")

    def good_sync_handler(event):
        calls.append(("good", event.data["seq"]))

    topic = Topic.SYSTEM_STATUS
    event_bus.subscribe(topic, bad_sync_handler)
    event_bus.subscribe(topic, good_sync_handler)

    await event_bus.publish_nowait(Event(topic=topic, data={"seq": 1}, source="test"))
    await event_bus.publish_nowait(Event(topic=topic, data={"seq": 2}, source="test"))

    task = asyncio.create_task(event_bus.start())
    await asyncio.sleep(0.05)
    await event_bus.stop()
    await task

    # Both events were processed by the healthy handler despite the raising
    # one on the same topic; the raising handler's errors were logged, not fatal.
    good_seqs = [seq for kind, seq in calls if kind == "good"]
    assert good_seqs == [1, 2]


@pytest.mark.asyncio
async def test_async_handler_exception_logged_but_loop_continues(event_bus, caplog):
    failing = AsyncMock(side_effect=ValueError("async boom"))
    received = []

    async def record(event):
        received.append(event.data["seq"])

    topic = Topic.RISK_ALERT
    event_bus.subscribe(topic, failing)
    event_bus.subscribe(topic, record)

    for seq in range(3):
        await event_bus.publish_nowait(
            Event(topic=topic, data={"seq": seq}, source="test")
        )

    with caplog.at_level(logging.ERROR, logger="shettyxtreme.core.event_bus"):
        task = asyncio.create_task(event_bus.start())
        await asyncio.sleep(0.05)
        await event_bus.stop()
        await task

    assert received == [0, 1, 2]
    assert failing.await_count == 3
    assert "EventBus handler error" in caplog.text


# --- Oracle #3: FIFO ordering guarantee under concurrent publishers ---


@pytest.mark.asyncio
async def test_concurrent_publishers_preserve_per_publisher_fifo(event_bus):
    publishers, seqs_per_publisher = 4, 25
    topic = Topic.MARKET_DATA_TICK
    delivered = []
    all_delivered = asyncio.Event()

    async def record(event):
        delivered.append((event.metadata["publisher"], event.metadata["seq"]))
        if len(delivered) == publishers * seqs_per_publisher:
            all_delivered.set()

    event_bus.subscribe(topic, record)

    async def publisher(pid):
        for seq in range(seqs_per_publisher):
            await event_bus.publish_nowait(
                Event(
                    topic=topic,
                    data={},
                    source=f"publisher-{pid}",
                    metadata={"publisher": pid, "seq": seq},
                )
            )
            # Yield so the event loop interleaves the publishers genuinely.
            await asyncio.sleep(0)

    # Consume concurrently with publishing (realistic concurrent load).
    task = asyncio.create_task(event_bus.start())
    await asyncio.gather(*(publisher(p) for p in range(publishers)))
    await asyncio.wait_for(all_delivered.wait(), timeout=5)
    await event_bus.stop()
    await task

    assert len(delivered) == publishers * seqs_per_publisher
    for pid in range(publishers):
        seqs = [seq for p, seq in delivered if p == pid]
        assert seqs == list(range(seqs_per_publisher)), (
            f"publisher {pid} delivered out of FIFO order: {seqs}"
        )
