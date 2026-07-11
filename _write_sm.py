content = """\"\"\"WebSocket connection manager for DhanHQ live market feed.

Wraps DhanHQ's MarketFeed with async-compatible interface, auto-reconnect
with exponential backoff, symbol subscription management, and Tick event
publication onto the EventBus.
\"\"\"

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from shettyxtreme.core.data_models import Tick
from shettyxtreme.core.event_bus import Event, EventBus, Topic

logger = logging.getLogger(__name__)

_EXCHANGE_MAP = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FNO",
    "BFO": "BSE_FNO",
    "MCX": "MCX",
    "IDX": "IDX_I",
}


class StreamManager:
    \"\"\"Manages a DhanHQ WebSocket market feed connection with auto-reconnect.\"\"\"

    MAX_RETRIES = 3
    BASE_DELAY = 1.0

    def __init__(
        self,
        event_bus: EventBus,
        dhan_client_id: str = "",
        dhan_access_token: str = "",
        exchange: str = "NSE",
    ) -> None:
        self._event_bus = event_bus
        self._client_id = dhan_client_id
        self._access_token = dhan_access_token
        self._exchange = exchange
        self._instruments: dict[str, list[str | int]] = {}
        self._running = False
        self._connected = False
        self._ws_task: Optional[asyncio.Task[None]] = None
        self._dhanhq_instance: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_instruments(self, symbols: list[str]) -> None:
        \"\"\"Set the list of instrument symbols to subscribe to.\"\"\"
        segment = _EXCHANGE_MAP.get(self._exchange, self._exchange)
        self._instruments = {segment: list(symbols)}

    async def connect(self) -> bool:
        \"\"\"Start the WebSocket connection. Returns True if successful.\"\"\"
        if self._running:
            logger.warning("StreamManager already running")
            return True
        self._running = True
        self._ws_task = asyncio.create_task(self._run_loop())
        return True

    async def disconnect(self) -> None:
        \"\"\"Gracefully stop the WebSocket connection.\"\"\"
        self._running = False
        self._connected = False
        if self._ws_task is not None:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def health(self) -> dict[str, Any]:
        \"\"\"Return current connection health status.\"\"\"
        return {"running": self._running, "connected": self._connected,
                "instruments": self._instruments, "exchange": self._exchange}

    # ------------------------------------------------------------------
    # Internal: reconnection loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        \"\"\"Run the WebSocket connection with auto-reconnect.\"\"\"
        retries = 0
        while self._running and retries <= self.MAX_RETRIES:
            try:
                self._connected = False
                await self._connect_ws()
                self._connected = True
                retries = 0
                await self._ws_loop()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("WebSocket connection error")
                self._connected = False
            if not self._running:
                break
            retries += 1
            if retries <= self.MAX_RETRIES:
                delay = self.BASE_DELAY * (2 ** (retries - 1))
                logger.info(
                    "Reconnecting in %.0fs (attempt %d/%d)",
                    delay, retries, self.MAX_RETRIES,
                )
                await asyncio.sleep(delay)
            else:
                logger.error("Max retries (%d) reached, giving up", self.MAX_RETRIES)
        self._connected = False

    # ------------------------------------------------------------------
    # Internal: actual WS connection and feed loop
    # ------------------------------------------------------------------

    def _lazy_init_dhanhq(self) -> Any:
        \"\"\"Lazy init DhanHQ client (can be mocked in tests).\"\"\"
        if self._dhanhq_instance is None:
            from dhanhq import dhanhq
            self._dhanhq_instance = dhanhq.DhanHQ(
                client_id=self._client_id,
                access_token=self._access_token,
            )
        return self._dhanhq_instance

    async def _connect_ws(self) -> None:
        \"\"\"Create the DhanHQ MarketFeed instance (runs in executor).\"\"\"
        self._lazy_init_dhanhq()

    async def _ws_loop(self) -> None:
        \"\"\"Run the blocking DhanHQ MarketFeed loop in a thread.\"\"\"
        from dhanhq.marketfeed import MarketFeed as DhanWSFeed
        loop = asyncio.get_event_loop()

        def _run() -> None:
            feed = DhanWSFeed(
                dhan_context=self._dhanhq_instance,
                instruments=self._instruments,
                on_ticks=self._make_tick_callback(loop),
            )
            feed.run_forever()

        await loop.run_in_executor(None, _run)

    def _make_tick_callback(
        self, loop: asyncio.AbstractEventLoop
    ) -> Callable[[list[dict[str, Any]]], None]:
        \"\"\"Create a synchronous callback bridging DhanHQ ticks to the event loop.\"\"\"

        def on_ticks(ticks: list[dict[str, Any]]) -> None:
            asyncio.run_coroutine_threadsafe(self._process_ticks(ticks), loop)

        return on_ticks

    async def _process_ticks(self, raw_ticks: list[dict[str, Any]]) -> None:
        \"\"\"Parse raw DhanHQ tick dicts and publish as Tick events.\"\"\"
        for raw in raw_ticks:
            try:
                tick = self._parse_tick(raw)
                if tick is not None:
                    await self._event_bus.publish_nowait(
                        Event(topic=Topic.MARKET_DATA_TICK, data=tick, source="stream_manager"),
                    )
            except Exception:
                logger.exception("Failed to process tick: %s", raw)

    # ------------------------------------------------------------------
    # Tick parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_tick(raw: dict[str, Any]) -> Optional[Tick]:
        \"\"\"Parse a DhanHQ tick dict into a Tick dataclass.\"\"\"
        if not raw or "security_id" not in raw:
            return None
        exch = raw.get("exchange_segment", "")
        exchange = "NSE"
        for short, seg in _EXCHANGE_MAP.items():
            if seg == exch:
                exchange = short
                break
        return Tick(
            symbol=str(raw.get("security_id", "")),
            exchange=exchange,
            ltp=float(raw.get("ltp", 0)),
            volume=int(raw.get("volume", raw.get("ltq", 0))),
            timestamp=datetime.now(timezone.utc),
            bid=float(raw["bid"]) if raw.get("bid") is not None else None,
            ask=float(raw["ask"]) if raw.get("ask") is not None else None,
            open=float(raw["open"]) if raw.get("open") is not None else None,
            high=float(raw["high"]) if raw.get("high") is not None else None,
            low=float(raw["low"]) if raw.get("low") is not None else None,
            close=float(raw["close"]) if raw.get("close") is not None else None,
        )
"""
with open("src/shettyxtreme/data/pipeline/stream_manager.py", "w") as f:
    f.write(content)
print("stream_manager.py written")
