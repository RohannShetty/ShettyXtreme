"""Asyncio-based pub/sub event bus.

Decouples data producers from consumers. All market data, signals,
orders, and risk events flow through this bus.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional
from enum import Enum

class Topic(Enum):
    MARKET_DATA_TICK = "market.tick"
    MARKET_DATA_BAR = "market.bar"
    SIGNAL_GENERATED = "signal.generated"
    ORDER_PLACED = "order.placed"
    ORDER_FILLED = "order.filled"
    ORDER_REJECTED = "order.rejected"
    POSITION_CHANGED = "position.changed"
    RISK_ALERT = "risk.alert"
    CONFIG_CHANGED = "config.changed"
    SYSTEM_STATUS = "system.status"
    REGIME_CHANGED = "regime.changed"
    CONVICTION_CHANGED = "conviction.changed"
    FEATURES_COMPUTED = "features.computed"
    SIGNAL_V2 = "signal.v2"
    RISK_DECISION = "risk.decision"
    CREDENTIAL_HEALTH_CHANGED = "credential.health.changed"
    CREDENTIAL_WARNING = "credential.warning"
    ORDER_UPDATED = "order.updated"

@dataclass
class Event:
    topic: Topic
    data: Any
    source: str = "system"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Optional[dict] = None

EventHandler = Callable[[Event], Coroutine[Any, Any, None]]

class EventBus:
    def __init__(self):
        self._subscribers: dict[Topic, list[EventHandler]] = {}
        self._running = False
        self._queue: asyncio.Queue[Event] = asyncio.Queue()

    def subscribe(self, topic: Topic, handler: EventHandler):
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: Topic, handler: EventHandler):
        if topic in self._subscribers:
            self._subscribers[topic].remove(handler)

    async def publish(self, event: Event):
        await self._queue.put(event)

    async def publish_nowait(self, event: Event):
        self._queue.put_nowait(event)

    async def start(self):
        self._running = True
        while self._running:
            event = await self._queue.get()
            handlers = self._subscribers.get(event.topic, [])
            results = [h(event) for h in handlers]
            if results:
                await asyncio.gather(*results, return_exceptions=True)

    async def stop(self):
        self._running = False
        self._queue.put_nowait(Event(Topic.SYSTEM_STATUS, {"status": "stopped"}, "system"))

    @property
    def subscriber_count(self) -> int:
        return sum(len(h) for h in self._subscribers.values())
