"""High-level coordinator for the ShettyXtreme data pipeline.

Wires together the WebSocket stream manager, bar builder, time-series
storage, and event bus into a unified ingestion lifecycle.
"""

import asyncio
import logging
from typing import Any, Optional

from shettyxtreme.core.event_bus import EventBus
from shettyxtreme.core.storage.time_series_store import TimeSeriesStore
from shettyxtreme.data.pipeline.bar_builder import BarBuilder
from shettyxtreme.data.pipeline.stream_manager import StreamManager

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """High-level coordinator for market data ingestion.

    Manages the lifecycle of a StreamManager (WebSocket connection),
    BarBuilder (bar aggregation), and their integration with the
    EventBus and TimeSeriesStore.
    """

    def __init__(
        self,
        event_bus: EventBus,
        ts_store: TimeSeriesStore,
        dhan_client_id: str = "",
        dhan_access_token: str = "",
        exchange: str = "NSE",
    ) -> None:
        self._event_bus = event_bus
        self._ts_store = ts_store
        self._stream = StreamManager(
            event_bus=event_bus,
            dhan_client_id=dhan_client_id,
            dhan_access_token=dhan_access_token,
            exchange=exchange,
        )
        self._bar_builder = BarBuilder(event_bus=event_bus, ts_store=ts_store)
        self._running = False
        self._event_bus_task: Optional[asyncio.Task[None]] = None

    async def start(self, symbols: list[str]) -> None:
        """Start the full data pipeline.

        Args:
            symbols: List of instrument symbols/IDs to subscribe to.
        """
        if self._running:
            logger.warning("IngestionPipeline already running")
            return

        self._running = True

        # Start the event bus dispatcher
        self._event_bus_task = asyncio.create_task(self._event_bus.start())

        # Start bar builder (subscribes to tick events)
        await self._bar_builder.start()

        # Configure and connect WebSocket stream
        self._stream.set_instruments(symbols)
        await self._stream.connect()

        logger.info("IngestionPipeline started with %d symbols", len(symbols))

    async def stop(self) -> None:
        """Gracefully shut down the pipeline."""
        if not self._running:
            return

        self._running = False

        # Disconnect WebSocket
        await self._stream.disconnect()

        # Stop bar builder (flushes remaining bars)
        await self._bar_builder.stop()

        # Stop event bus
        await self._event_bus.stop()
        if self._event_bus_task is not None:
            self._event_bus_task.cancel()
            try:
                await self._event_bus_task
            except asyncio.CancelledError:
                pass
            self._event_bus_task = None

        logger.info("IngestionPipeline stopped")

    async def health(self) -> dict[str, Any]:
        """Return combined health status of pipeline components."""
        stream_health = await self._stream.health()
        bar_health = await self._bar_builder.health()
        return {
            "running": self._running,
            "stream": stream_health,
            "bar_builder": bar_health,
        }
