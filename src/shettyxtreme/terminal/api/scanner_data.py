"""Scanner data pipeline — populates gaps, clusters, and logs.

Subscribes to EventBus topics and maintains in-memory stores
that scanner_router.py reads from.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from shettyxtreme.core.data_models import Tick
from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic

logger = logging.getLogger(__name__)


class GapDetector:
    """Detects overnight gaps from MARKET_DATA_TICK events.

    Compares current tick open vs previous close per symbol.
    """

    def __init__(self) -> None:
        self._prev_close: dict[str, float] = {}
        self.gaps: list[dict[str, Any]] = []

    async def on_tick(self, event: Event) -> None:
        d = event.data
        if isinstance(d, Tick):
            d = {
                "symbol": d.symbol,
                "exchange": d.exchange,
                "ltp": d.ltp,
                "volume": d.volume,
                "open": d.open,
                "high": d.high,
                "low": d.low,
                "close": d.close,
                "timestamp": d.timestamp,
            }
        symbol = d.get("symbol")
        if not symbol:
            return

        open_price = d.get("open", 0.0)
        prev_close = self._prev_close.get(symbol)

        if prev_close and prev_close > 0 and open_price > 0:
            gap_pct = ((open_price - prev_close) / prev_close) * 100.0
            if abs(gap_pct) > 0.5:
                direction = "gap_up" if gap_pct > 0 else "gap_down"
                if abs(gap_pct) > 1.5:
                    gap_type = "breakaway"
                elif abs(gap_pct) > 1.0:
                    gap_type = "exhaustion"
                else:
                    gap_type = "common"
                self.gaps.append({
                    "symbol": symbol,
                    "gap_type": gap_type,
                    "gap_percent": round(abs(gap_pct), 2),
                    "direction": direction,
                    "timestamp": event.timestamp,
                })
                if len(self.gaps) > 100:
                    self.gaps = self.gaps[-100:]

        close = d.get("ltp", 0.0)
        if close > 0:
            self._prev_close[symbol] = close

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.MARKET_DATA_TICK, self.on_tick)


class LogCollector:
    """Collects structured log entries from EventBus events."""

    MAX_LOGS = 500

    def __init__(self) -> None:
        self.logs: list[dict[str, Any]] = []

    def _add(self, log_type: str, message: str, level: str = "INFO") -> None:
        self.logs.append({
            "log_type": log_type,
            "message": message,
            "level": level,
            "timestamp": datetime.now(UTC),
        })
        if len(self.logs) > self.MAX_LOGS:
            self.logs = self.logs[-self.MAX_LOGS:]

    async def on_signal(self, event: Event) -> None:
        d = event.data
        direction = d.get("direction", "NEUTRAL")
        conviction = d.get("conviction", 0.0)
        self._add("signal", f"Signal: {direction} (conviction={conviction:.2f})", "INFO")

    async def on_order(self, event: Event) -> None:
        d = event.data
        status = d.get("status", "unknown")
        order_id = d.get("order_id", "?")
        self._add("execution", f"Order {order_id}: {status}", "INFO")

    async def on_order_rejected(self, event: Event) -> None:
        d = event.data
        order_id = d.get("order_id", "?")
        reason = d.get("reason", "unknown")
        self._add("execution", f"Order {order_id} REJECTED: {reason}", "ERROR")

    async def on_risk_alert(self, event: Event) -> None:
        d = event.data
        msg = d.get("message", "risk alert")
        self._add("risk", msg, "WARN")

    async def on_system_status(self, event: Event) -> None:
        d = event.data
        status = d.get("status", "unknown")
        self._add("system", f"System: {status}", "INFO")

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.SIGNAL_GENERATED, self.on_signal)
        bus.subscribe(Topic.ORDER_PLACED, self.on_order)
        bus.subscribe(Topic.ORDER_FILLED, self.on_order)
        bus.subscribe(Topic.ORDER_REJECTED, self.on_order_rejected)
        bus.subscribe(Topic.ORDER_UPDATED, self.on_order)
        bus.subscribe(Topic.RISK_ALERT, self.on_risk_alert)
        bus.subscribe(Topic.SYSTEM_STATUS, self.on_system_status)


class ClusterDetector:
    """Detects opportunity clusters from multiple signals on same symbol."""

    def __init__(self) -> None:
        self._recent_signals: dict[str, list[datetime]] = {}
        self.clusters: list[dict[str, Any]] = []

    async def on_signal(self, event: Event) -> None:
        d = event.data
        symbol = d.get("symbol", "UNKNOWN")
        now = event.timestamp

        if symbol not in self._recent_signals:
            self._recent_signals[symbol] = []
        self._recent_signals[symbol].append(now)

        cutoff = now.replace(tzinfo=None)
        from datetime import timedelta
        window = [t for t in self._recent_signals[symbol]
                  if (cutoff - t.replace(tzinfo=None)).total_seconds() < 300]
        self._recent_signals[symbol] = window

        if len(window) >= 2:
            self.clusters.append({
                "symbol": symbol,
                "cluster_type": "multi_signal",
                "strength": min(len(window) / 5.0, 1.0),
                "source_count": len(window),
                "sources": ["signal_engine"] * len(window),
            })
            if len(self.clusters) > 50:
                self.clusters = self.clusters[-50:]

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.SIGNAL_GENERATED, self.on_signal)
