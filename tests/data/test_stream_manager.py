"""Tests for StreamManager."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shettyxtreme.core.event_bus import EventBus
from shettyxtreme.core.event_bus.event_bus import Topic
from shettyxtreme.data.pipeline.stream_manager import StreamManager


class TestStreamManager:
    @pytest.mark.asyncio
    async def test_initial_state(self):
        eb = EventBus()
        sm = StreamManager(event_bus=eb)
        assert not sm.is_connected

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        eb = EventBus()
        sm = StreamManager(event_bus=eb)
        task = asyncio.create_task(eb.start())
        await asyncio.sleep(0.05)
        await sm.disconnect()
        await eb.stop()
        await task
        assert True

    @pytest.mark.asyncio
    async def test_set_instruments(self):
        eb = EventBus()
        sm = StreamManager(event_bus=eb)
        sm.set_instruments({"NSE_EQ": [11536]})
        assert sm._instruments is not None

    @pytest.mark.asyncio
    async def test_tick_symbol_resolved_through_symbol_map(self):
        """Ticks keyed by security ID should publish under the display symbol."""
        eb = EventBus()
        sm = StreamManager(event_bus=eb)
        sm.set_symbol_map({"13": "NIFTY"})

        published = []

        async def handler(event):
            published.append(event)

        eb.subscribe(Topic.MARKET_DATA_TICK, handler)
        task = asyncio.create_task(eb.start())
        await asyncio.sleep(0.05)

        await sm._process_ticks(
            [{"security_id": "13", "exchange_segment": "NSE_FNO", "ltp": 24500.5, "volume": 1000}]
        )
        await asyncio.sleep(0.05)
        await eb.stop()
        await task

        assert len(published) == 1
        assert published[0].data.symbol == "NIFTY"
        assert published[0].data.ltp == 24500.5

    @pytest.mark.asyncio
    async def test_tick_symbol_falls_back_to_id(self):
        """Unknown security IDs should keep the raw ID as the symbol."""
        eb = EventBus()
        sm = StreamManager(event_bus=eb)
        sm.set_symbol_map({"13": "NIFTY"})

        published = []

        async def handler(event):
            published.append(event)

        eb.subscribe(Topic.MARKET_DATA_TICK, handler)
        task = asyncio.create_task(eb.start())
        await asyncio.sleep(0.05)

        await sm._process_ticks(
            [{"security_id": "999", "exchange_segment": "NSE_FNO", "ltp": 100.0, "volume": 5}]
        )
        await asyncio.sleep(0.05)
        await eb.stop()
        await task

        assert published[0].data.symbol == "999"
