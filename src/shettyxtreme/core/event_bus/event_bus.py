"""Asyncio-based pub/sub event bus.

Decouples data producers from consumers. All market data, signals,
orders, and risk events flow through this bus.

Ordering guarantee: events are delivered strictly in FIFO order as
enqueued. With multiple concurrent publishers the global interleaving is
nondeterministic, but each publisher's own events are delivered in the
order they were published (per-publisher FIFO) — the single consumer loop
drains the queue one event at a time, so a publisher can never overtake
itself.
"""
import asyncio
import inspect
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

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
    SCANNER_GAP = "scanner.gap"
    SCANNER_CLUSTER = "scanner.cluster"
    SCANNER_LOG = "scanner.log"
    SCANNER_FINDING = "scanner.finding"

@dataclass
class Event:
    topic: Topic
    data: Any
    source: str = "system"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict | None = None

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
            coroutines = []
            for handler in handlers:
                try:
                    result = handler(event)
                except Exception:
                    # A handler raised synchronously — log it and keep the
                    # loop alive; one bad subscriber must not kill the bus.
                    logger.exception(
                        "EventBus handler raised synchronously on topic %s",
                        event.topic.value,
                    )
                    continue
                if inspect.isawaitable(result):
                    coroutines.append(result)
                else:
                    # Sync handler — already invoked. Its result is not
                    # awaitable, so there is nothing to gather; discard it.
                    logger.debug(
                        "EventBus handler %r returned a non-awaitable result; discarded",
                        handler,
                    )
            if coroutines:
                gathered = await asyncio.gather(*coroutines, return_exceptions=True)
                for result in gathered:
                    if isinstance(result, Exception):
                        logger.exception(
                            "EventBus handler error on topic %s",
                            event.topic.value,
                            exc_info=result,
                        )

    async def stop(self):
        self._running = False
        self._queue.put_nowait(Event(Topic.SYSTEM_STATUS, {"status": "stopped"}, "system"))

    @property
    def subscriber_count(self) -> int:
        return sum(len(h) for h in self._subscribers.values())
