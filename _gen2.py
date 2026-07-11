import os
base = '/d/ShettyXtreme'
def w(relpath, content):
    full = os.path.join(base, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', newline='\n') as f:
        f.write(content)
    print('OK:', relpath)

# stream_manager.py
w('src/shettyxtreme/data/pipeline/stream_manager.py', """
\"\"\"WebSocket streaming manager for real-time market data.
\"\"\"
from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import httpx
import websockets
from shettyxtreme.core.data_models.market_data import Tick
from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
logger = logging.getLogger(__name__)
MAX_RECONNECT_RETRIES: int = 3
BASE_RECONNECT_DELAY: float = 1.0
@dataclass
class StreamConfig:
    ws_url: str = \"ws://localhost:5000/ws\"
    rest_url: str = \"http://localhost:5000\"
    api_key: str = \"\"
    ping_interval: int = 30
    max_retries: int = MAX_RECONNECT_RETRIES
class StreamManager:
    def __init__(self, event_bus: EventBus, config: StreamConfig | None = None) -> None:
        self._event_bus = event_bus
        self._config = config or StreamConfig()
        self._ws = None
        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        self._running = False
        self._subscribed_symbols = set()
        self._reconnect_attempt = 0
        self._listen_task = None
        self._reconnect_lock = asyncio.Lock()
    async def start(self) -> None:
        self._running = True
        await self._connect()
    async def stop(self) -> None:
        self._running = False
        if self._listen_task is not None and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        await self._disconnect_ws()
        await self._http_client.aclose()
    async def subscribe(self, symbols: list[str]) -> None:
        new_symbols = [s for s in symbols if s not in self._subscribed_symbols]
        if not new_symbols:
            return
        self._subscribed_symbols.update(new_symbols)
        if self._ws is not None:
            await self._send_subscribe(new_symbols)
    async def unsubscribe(self, symbols: list[str]) -> None:
        for s in symbols:
            self._subscribed_symbols.discard(s)
        if self._ws is not None and symbols:
            msg = {\"action\": \"unsubscribe\", \"symbols\": symbols}
            await self._ws.send(json.dumps(msg))
    @property
    def is_connected(self) -> bool:
        return self._ws is not None and not self._ws.closed
    @property
    def subscribed_symbols(self) -> set[str]:
        return self._subscribed_symbols.copy()
    async def _connect(self) -> None:
        async with self._reconnect_lock:
            if not self._running:
                return
            try:
                await self._check_health()
            except Exception:
                logger.exception(\"REST health check errored\")
            try:
                self._ws = await websockets.connect(
                    self._config.ws_url,
                    ping_interval=self._config.ping_interval,
                )
                self._reconnect_attempt = 0
                if self._subscribed_symbols:
                    await self._send_subscribe(list(self._subscribed_symbols))
                self._listen_task = asyncio.create_task(self._listen_loop())
            except Exception as exc:
                logger.error(\"WS connection failed: %s\", exc)
                await self._schedule_reconnect()
    async def _disconnect_ws(self) -> None:
        if self._ws is not None and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
    async def _schedule_reconnect(self) -> None:
        if self._reconnect_attempt >= MAX_RECONNECT_RETRIES:
            logger.error(\"Max reconnect retries exhausted\")
            self._running = False
            return
        delay = BASE_RECONNECT_DELAY * (2**self._reconnect_attempt)
        self._reconnect_attempt += 1
        await asyncio.sleep(delay)
        if self._running:
            await self._connect()
    async def _check_health(self) -> bool:
        try:
            response = await self._http_client.get(
                f\"{self._config.rest_url}/api/v1/analyzerstatus\"
            )
            return response.status_code == 200
        except httpx.RequestError:
            return False
    async def _listen_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw_message in self._ws:
                if not self._running:
                    break
                try:
                    await self._process_message(raw_message)
                except Exception:
                    logger.exception(\"Error processing WS message\")
        except websockets.ConnectionClosed:
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(\"Unexpected error\")
        finally:
            if self._running:
                await self._disconnect_ws()
                await self._schedule_reconnect()
    async def _process_message(self, raw: str) -> None:
        data = json.loads(raw)
        symbol = data.get(\"symbol\", \"\")
        if not symbol:
            return
        ts_str = data.get(\"timestamp\", \"\")
        try:
            timestamp = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            timestamp = datetime.now(timezone.utc)
        tick = Tick(
            symbol=symbol,
            exchange=data.get(\"exchange\", \"NSE\"),
            ltp=float(data.get(\"ltp\", 0.0)),
            volume=int(data.get(\"volume\", 0)),
            timestamp=timestamp,
            bid=float(data[\"bid\"]) if data.get(\"bid\") is not None else None,
            ask=float(data[\"ask\"]) if data.get(\"ask\") is not None else None,
            open=float(data[\"open\"]) if data.get(\"open\") is not None else None,
            high=float(data[\"high\"]) if data.get(\"high\") is not None else None,
            low=float(data[\"low\"]) if data.get(\"low\") is not None else None,
            close=float(data[\"close\"]) if data.get(\"close\") is not None else None,
        )
        event = Event(topic=Topic.MARKET_DATA_TICK, data=tick, source=\"stream_manager\", timestamp=timestamp)
        await self._event_bus.publish_nowait(event)
    async def _send_subscribe(self, symbols: list[str]) -> None:
        if self._ws is None or self._ws.closed:
            return
        msg = {\"action\": \"subscribe\", \"symbols\": symbols}
        try:
            await self._ws.send(json.dumps(msg))
        except Exception:
            pass
""")

print("stream_manager.py written")
