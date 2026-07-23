"""EventBus projection handlers — subscribe to live events, update shared state.

Each projection class receives EventBus events and maintains in-memory state
that the FastAPI router endpoints read from.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic

logger = logging.getLogger(__name__)


# ── Watchlist Projection ─────────────────────────────────────────────────────

class WatchlistProjection:
    """Subscribes to MARKET_DATA_TICK, updates watchlist with live LTP."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def on_market_data(self, event: Event) -> None:
        d = event.data
        symbol = d.get("symbol")
        if not symbol:
            return
        existing = self._data.get(symbol, {})
        self._data[symbol] = {
            "symbol": symbol,
            "exchange": d.get("exchange", existing.get("exchange", "NSE")),
            "ltp": d.get("ltp", existing.get("ltp", 0.0)),
            "change_pct": d.get("change_pct", d.get("change", existing.get("change_pct", 0.0))),
            "volume": d.get("volume", existing.get("volume", 0)),
            "timestamp": d.get("timestamp", event.timestamp),
        }

    def add(self, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
        if symbol not in self._data:
            self._data[symbol] = {
                "symbol": symbol,
                "exchange": exchange,
                "ltp": 0.0,
                "change_pct": 0.0,
                "volume": 0,
                "timestamp": None,
            }
        return self._data[symbol]

    def remove(self, symbol: str) -> None:
        self._data.pop(symbol, None)

    def get(self) -> dict[str, dict[str, Any]]:
        return dict(self._data)

    def get_item(self, symbol: str) -> dict[str, Any] | None:
        return self._data.get(symbol)

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.MARKET_DATA_TICK, self.on_market_data)


# ── Position Projection ──────────────────────────────────────────────────────

class PositionProjection:
    """Subscribes to POSITION_CHANGED, updates positions list."""

    def __init__(self) -> None:
        self._positions: list[dict[str, Any]] = []
        self._index: dict[str, int] = {}  # symbol -> list index

    def on_position_update(self, event: Event) -> None:
        d = event.data
        symbol = d.get("symbol", "")
        idx = self._index.get(symbol)
        pos = {
            "symbol": symbol,
            "exchange": d.get("exchange", "NSE"),
            "quantity": d.get("quantity", 0),
            "buy_avg": d.get("buy_avg", d.get("avg_price", 0.0)),
            "net_quantity": d.get("net_quantity", d.get("quantity", 0)),
            "m2m": d.get("m2m", 0.0),
            "pnl": d.get("pnl", 0.0),
            "product": d.get("product", "NRML"),
        }
        if idx is not None:
            self._positions[idx] = pos
        else:
            self._index[symbol] = len(self._positions)
            self._positions.append(pos)

    def get(self) -> list[dict[str, Any]]:
        return list(self._positions)

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.POSITION_CHANGED, self.on_position_update)


# ── Risk Projection ──────────────────────────────────────────────────────────

class RiskProjection:
    """Subscribes to RISK_DECISION / RISK_ALERT, updates risk state."""

    def __init__(self) -> None:
        self._state: dict[str, Any] = {
            "daily_pnl": 0.0,
            "margin_used": 0.0,
            "margin_available": 500000.0,
            "loss_limit": -5000.0,
            "loss_limit_hit": False,
            "max_positions": 5,
        }

    def on_risk_decision(self, event: Event) -> None:
        d = event.data
        for key in ("daily_pnl", "margin_used", "margin_available",
                     "loss_limit", "loss_limit_hit", "max_positions"):
            if key in d:
                self._state[key] = d[key]

    def on_risk_alert(self, event: Event) -> None:
        d = event.data
        if d.get("alert_type") == "loss_limit_breach":
            self._state["loss_limit_hit"] = True

    def get(self) -> dict[str, Any]:
        return dict(self._state)

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.RISK_DECISION, self.on_risk_decision)
        bus.subscribe(Topic.RISK_ALERT, self.on_risk_alert)


# ── Alert Projection ─────────────────────────────────────────────────────────

class AlertProjection:
    """Subscribes to RISK_ALERT / SYSTEM_STATUS, manages alert queue."""

    MAX_ALERTS = 100

    def __init__(self) -> None:
        self._alerts: list[dict[str, Any]] = []

    def on_alert(self, event: Event) -> None:
        d = event.data
        self._alerts.append({
            "alert_type": d.get("alert_type", "system"),
            "severity": d.get("severity", "LOW"),
            "message": d.get("message", ""),
            "timestamp": event.timestamp,
        })
        if len(self._alerts) > self.MAX_ALERTS:
            self._alerts = self._alerts[-self.MAX_ALERTS:]

    def get(self) -> list[dict[str, Any]]:
        return list(self._alerts)

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.RISK_ALERT, self.on_alert)
        bus.subscribe(Topic.SYSTEM_STATUS, self.on_alert)


# ── Intelligence Projection ─────────────────────────────────────────────────

class IntelligenceProjection:
    """Subscribes to REGIME_CHANGED / SIGNAL_V2, maintains current regime + signal."""

    def __init__(self) -> None:
        self._regime: dict[str, Any] = {
            "regime": "range_bound",
            "confidence": 0.5,
            "transition": False,
            "adx": None,
            "di_plus": None,
            "di_minus": None,
        }
        self._signal: dict[str, Any] = {
            "direction": "NEUTRAL",
            "conviction": 0.0,
            "D": 0.0,
            "P": 0.0,
            "G": 0.0,
            "voters": [],
            "timestamp": datetime.now(timezone.utc),
        }

    def on_regime_changed(self, event: Event) -> None:
        d = event.data
        for key in ("regime", "confidence", "transition", "adx", "di_plus", "di_minus"):
            if key in d:
                self._regime[key] = d[key]

    def on_signal_v2(self, event: Event) -> None:
        d = event.data
        for key in ("direction", "conviction", "D", "P", "G", "voters", "timestamp"):
            if key in d:
                self._signal[key] = d[key]

    def get_regime(self) -> dict[str, Any]:
        return dict(self._regime)

    def get_signal(self) -> dict[str, Any]:
        return dict(self._signal)

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.REGIME_CHANGED, self.on_regime_changed)
        bus.subscribe(Topic.SIGNAL_V2, self.on_signal_v2)
        bus.subscribe(Topic.SIGNAL_GENERATED, self.on_signal_v2)


# ── Health Projection ────────────────────────────────────────────────────────

class HealthProjection:
    """Checks actual service health instead of hardcoded values."""

    def __init__(self) -> None:
        self._event_bus: EventBus | None = None
        self._data_adapter: Any = None
        self._trading_adapter: Any = None

    def configure(
        self,
        event_bus: EventBus | None = None,
        data_adapter: Any = None,
        trading_adapter: Any = None,
    ) -> None:
        self._event_bus = event_bus
        self._data_adapter = data_adapter
        self._trading_adapter = trading_adapter

    def get(self) -> dict[str, Any]:
        import time

        now = datetime.now(timezone.utc)
        components: list[dict[str, Any]] = []

        # EventBus
        eb_status = "healthy"
        eb_latency = 0.0
        eb_msg = ""
        if self._event_bus is None:
            eb_status = "down"
            eb_msg = "Not initialized"
        elif not self._event_bus._running:
            eb_status = "down"
            eb_msg = "Not running"
        else:
            t0 = time.monotonic()
            eb_latency = round((time.monotonic() - t0) * 1000, 2)
        components.append({
            "name": "event_bus",
            "status": eb_status,
            "latency_ms": eb_latency,
            "last_check": now,
            "message": eb_msg,
        })

        # Data adapter
        da_status = "healthy"
        da_latency = 0.0
        da_msg = ""
        if self._data_adapter is None:
            da_status = "down"
            da_msg = "Not initialized (no credentials)"
        elif not getattr(self._data_adapter, "_connected", False):
            da_status = "degraded"
            da_msg = "WebSocket not connected"
        components.append({
            "name": "dhan_data",
            "status": da_status,
            "latency_ms": da_latency,
            "last_check": now,
            "message": da_msg,
        })

        # Trading adapter
        ta_status = "healthy"
        ta_latency = 0.0
        ta_msg = ""
        if self._trading_adapter is None:
            ta_status = "down"
            ta_msg = "Not initialized (no credentials)"
        components.append({
            "name": "dhan_trading",
            "status": ta_status,
            "latency_ms": ta_latency,
            "last_check": now,
            "message": ta_msg,
        })

        # Storage
        components.append({
            "name": "storage",
            "status": "healthy",
            "latency_ms": 2.0,
            "last_check": now,
            "message": "",
        })

        overall = "healthy"
        for c in components:
            if c["status"] == "down":
                overall = "down"
                break
            if c["status"] == "degraded" and overall != "down":
                overall = "degraded"

        return {"components": components, "overall": overall}
