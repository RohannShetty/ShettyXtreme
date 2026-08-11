"""EventBus -> TradeLedger recorder (ticket 06).

Paper fills arrive as ORDER_FILLED (full order details); Dhan postbacks
arrive as ORDER_UPDATED (order_id/status/filled_quantity/average_price —
side is unknowable at this surface, recorded as NULL). The symbol IS
resolved from the fill already recorded for the order-id so postbacks
pair against the right instrument; unresolvable postbacks are skipped
with a warning. Idempotent via the ledger's (order_id, source) key.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.execution.ledger import TradeLedger

logger = logging.getLogger(__name__)

_FILLED_STATUSES = {"FILLED", "TRADED", "COMPLETE"}


class LedgerRecorder:
    def __init__(
        self,
        ledger: TradeLedger,
        session_id_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self._ledger = ledger
        self._session_id = session_id_provider or (lambda: None)

    async def on_order_filled(self, event: Event) -> None:
        d = event.data
        self._ledger.record_fill({
            "fill_id": f"{d.get('order_id')}:paper",
            "order_id": d.get("order_id"),
            "session_id": self._session_id(),
            "symbol": d.get("symbol"),
            "side": d.get("side"),
            "quantity": d.get("quantity"),
            "price": d.get("price"),
            "product": d.get("product"),
            "source": "paper",
            "recorded_at": event.timestamp.isoformat(),
        })

    async def on_order_updated(self, event: Event) -> None:
        d = event.data
        status = str(d.get("status", "")).upper()
        qty = d.get("filled_quantity") or 0
        if status not in _FILLED_STATUSES or not qty:
            return
        order_id = d.get("order_id")
        symbol = self._ledger.symbol_for_order(order_id) if order_id else None
        if not symbol:
            logger.warning(
                "postback fill skipped for order_id=%r — no resolvable symbol "
                "in ledger (no original fill recorded for that order-id)",
                order_id,
            )
            return
        self._ledger.record_fill({
            "fill_id": f"{order_id}:postback",
            "order_id": order_id,
            "session_id": self._session_id(),
            "symbol": symbol,
            "side": None,
            "quantity": int(qty),
            "price": d.get("average_price"),
            "product": None,
            "source": "postback",
            "recorded_at": event.timestamp.isoformat(),
        })

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.ORDER_FILLED, self.on_order_filled)
        bus.subscribe(Topic.ORDER_UPDATED, self.on_order_updated)
