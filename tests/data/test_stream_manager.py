"""Tests for StreamManager."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shettyxtreme.core.event_bus import EventBus
from shettyxtreme.data.pipeline.stream_manager import StreamManager


class TestStreamManager:
    @pytest.mark.asyncio
    async def test_initial_state(self):
        eb = EventBus()
        sm = StreamManager(event_bus=eb)
        assert not sm.is_connected()
        health = sm.health()
        assert health["status"] == "disconnected"

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        eb = EventBus()
        sm = StreamManager(event_bus=eb)
        task = asyncio.create_task(eb.start())
        await asyncio.sleep(0.02)
        sm.disconnect()
        await task

    @pytest.mark.asyncio
    async def test_set_instruments(self):
        eb = EventBus()
        sm = StreamManager(event_bus=eb)
        sm.set_instruments({"NSE_EQ": [11536]})
        health = sm.health()
        assert "NSE_EQ" in str(health)
