"""EventBus projection handlers — subscribe to live events, update shared state.

Each projection class receives EventBus events and maintains in-memory state
that the FastAPI router endpoints read from.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from shettyxtreme.core.data_models import Tick
from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.core.settings import get_settings_store
from shettyxtreme.terminal.api import ws_bridge

logger = logging.getLogger(__name__)


# ── Connection State (P1-2.4) ──────────────────────────────────────────────

# Tick-staleness threshold in seconds: if no market-data tick arrives within
# this window the data-adapter component transitions to STALE.
_TICK_STALE_SECONDS: float = 60.0


class ConnectionState(str, Enum):
    """Single source of truth for the connection pip in the header.

    Transitions:
        DISCONNECTED → CONNECTING → CONNECTED → STALE → EXPIRED
        EXPIRED supersedes all; token re-auth returns to CONNECTING.
    """
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STALE = "stale"
    EXPIRED = "expired"


# ── Watchlist Projection ─────────────────────────────────────────────────────

class WatchlistProjection:
    """Subscribes to MARKET_DATA_TICK, updates watchlist with live LTP."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    async def on_market_data(self, event: Event) -> None:
        d = event.data
        if isinstance(d, Tick):
            change_pct = 0.0
            if d.close and d.close > 0:
                change_pct = round(((d.ltp - d.close) / d.close) * 100, 2)
            d = {
                "symbol": d.symbol,
                "exchange": d.exchange,
                "ltp": d.ltp,
                "volume": d.volume,
                "change_pct": change_pct,
                # P6-W2: chain fields ride the wire so ChainGrid updates live
                # without REST polling. iv stays REST-only (HSM feed limit).
                "oi": d.oi,
                "strike": d.strike,
                "option_type": d.option_type,
                "timestamp": d.timestamp,
            }
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
            "oi": d.get("oi", existing.get("oi")),
            "strike": d.get("strike", existing.get("strike")),
            "option_type": d.get("option_type", existing.get("option_type")),
            "security_id": d.get("security_id", existing.get("security_id")),
            "expiry": existing.get("expiry"),
            "lot_size": existing.get("lot_size"),
            "timestamp": d.get("timestamp", event.timestamp),
        }
        await ws_bridge.broadcast("tick", {
            "symbol": symbol,
            "ltp": self._data[symbol]["ltp"],
            "change_pct": self._data[symbol]["change_pct"],
            "volume": self._data[symbol]["volume"],
            "oi": self._data[symbol]["oi"],
            "strike": self._data[symbol]["strike"],
            "option_type": self._data[symbol]["option_type"],
        })

    def add(
        self,
        symbol: str,
        exchange: str = "NSE",
        security_id: str | None = None,
        expiry: str | None = None,
        lot_size: int | None = None,
    ) -> dict[str, Any]:
        if symbol not in self._data:
            self._data[symbol] = {
                "symbol": symbol,
                "exchange": exchange,
                "ltp": 0.0,
                "change_pct": 0.0,
                "volume": 0,
                "oi": None,
                "strike": None,
                "option_type": None,
                "security_id": security_id,
                "expiry": expiry,
                "lot_size": lot_size,
                "timestamp": None,
            }
        else:
            # Update metadata on re-add (e.g. persistence reload)
            if expiry is not None:
                self._data[symbol]["expiry"] = expiry
            if lot_size is not None:
                self._data[symbol]["lot_size"] = lot_size
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

    async def on_position_update(self, event: Event) -> None:
        d = event.data
        symbol = d.get("symbol", "")
        idx = self._index.get(symbol)
        # P3-4.3: merge trade context from fill event into the position
        # projection so the API can surface SL/TGT/rationale/confidence.
        existing = self._positions[idx] if idx is not None else {}
        pos = {
            "symbol": symbol,
            "exchange": d.get("exchange", existing.get("exchange", "NSE")),
            "quantity": d.get("quantity", 0),
            "buy_avg": d.get("buy_avg", d.get("avg_price", 0.0)),
            "net_quantity": d.get("net_quantity", d.get("quantity", 0)),
            "m2m": d.get("m2m", 0.0),
            "pnl": d.get("pnl", 0.0),
            "product": d.get("product", existing.get("product", "NRML")),
        }
        # Carry trade context if present (from paper engine fill event).
        for ctx_key in ("signal_id", "stop_loss", "target", "rationale",
                        "confidence", "lot_size"):
            val = d.get(ctx_key)
            if val is not None:
                pos[ctx_key] = val
            elif ctx_key in existing:
                pos[ctx_key] = existing[ctx_key]
        if idx is not None:
            self._positions[idx] = pos
        else:
            self._index[symbol] = len(self._positions)
            self._positions.append(pos)
        await ws_bridge.broadcast("position", {
            "symbol": symbol,
            "net_quantity": pos["net_quantity"],
            "m2m": pos["m2m"],
            "pnl": pos["pnl"],
        })

    def get(self) -> list[dict[str, Any]]:
        return list(self._positions)

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.POSITION_CHANGED, self.on_position_update)


# ── Risk Projection ──────────────────────────────────────────────────────────

class RiskProjection:
    """Subscribes to RISK_DECISION / RISK_ALERT, updates risk state."""

    def __init__(self) -> None:
        # Risk caps come from the shared settings store (P7-W3) so the
        # initial state reflects persisted operator settings, not constants.
        store = get_settings_store()
        self._state: dict[str, Any] = {
            "daily_pnl": 0.0,
            "margin_used": 0.0,
            # Margin is UNKNOWN until the broker reports it (fix #2). A
            # fabricated default would silently admit trades on phantom
            # capital; None is the honest "no data yet" state.
            "margin_available": None,
            "loss_limit": store.loss_limit(),
            "loss_limit_hit": False,
            "max_positions": store.max_positions(),
        }

    async def on_risk_decision(self, event: Event) -> None:
        d = event.data
        for key in ("daily_pnl", "margin_used", "margin_available",
                     "loss_limit", "loss_limit_hit", "max_positions"):
            if key in d:
                self._state[key] = d[key]
        await ws_bridge.broadcast("risk", dict(self._state))

    async def on_risk_alert(self, event: Event) -> None:
        d = event.data
        if d.get("alert_type") == "loss_limit_breach":
            self._state["loss_limit_hit"] = True
        await ws_bridge.broadcast("alert", {
            "alert_type": d.get("alert_type", "system"),
            "severity": d.get("severity", "LOW"),
            "message": d.get("message", ""),
        })

    def get(self) -> dict[str, Any]:
        return dict(self._state)

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.RISK_DECISION, self.on_risk_decision)
        bus.subscribe(Topic.RISK_ALERT, self.on_risk_alert)


# ── Alert Projection ─────────────────────────────────────────────────────────

_DEDUP_WINDOW_SECONDS = 30.0


class AlertProjection:
    """Subscribes to RISK_ALERT / SYSTEM_STATUS, manages alert queue."""

    MAX_ALERTS = 100

    def __init__(self) -> None:
        self._alerts: list[dict[str, Any]] = []
        self._last_key: tuple[str, str] | None = None
        self._last_ts: datetime | None = None

    async def on_alert(self, event: Event) -> None:
        d = event.data
        key = (str(d.get("alert_type", "system")), str(d.get("message", "")))
        now = event.timestamp
        if key == self._last_key and self._last_ts is not None and (now - self._last_ts).total_seconds() < _DEDUP_WINDOW_SECONDS:
            return
        self._last_key, self._last_ts = key, now
        self._alerts.append({
            "alert_type": d.get("alert_type", "system"),
            "severity": d.get("severity", "LOW"),
            "message": d.get("message", ""),
            "timestamp": event.timestamp,
        })
        if len(self._alerts) > self.MAX_ALERTS:
            self._alerts = self._alerts[-self.MAX_ALERTS:]
        await ws_bridge.broadcast("alert", {
            "alert_type": d.get("alert_type", "system"),
            "severity": d.get("severity", "LOW"),
            "message": d.get("message", ""),
        })

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
            "timestamp": datetime.now(UTC),
        }
        self._has_data = False
        self._last_update: datetime | None = None

    async def on_regime_changed(self, event: Event) -> None:
        d = event.data
        values = getattr(d, "__dict__", d) if not isinstance(d, dict) else d
        if values is None:
            return
        for key in ("regime", "confidence", "transition", "adx", "di_plus", "di_minus"):
            if key in values:
                self._regime[key] = values[key]
        self._mark_received(event.timestamp)
        await ws_bridge.broadcast("regime", dict(self._regime))

    async def on_signal_v2(self, event: Event) -> None:
        d = event.data
        values = getattr(d, "__dict__", d) if not isinstance(d, dict) else d
        if values is None:
            return
        for key in ("direction", "conviction", "D", "P", "G", "voters", "timestamp"):
            if key in values:
                value = values[key]
                if isinstance(value, Enum):
                    value = value.name
                self._signal[key] = value
        self._mark_received(event.timestamp)
        await ws_bridge.broadcast("signal", {
            "direction": self._signal["direction"],
            "conviction": self._signal["conviction"],
            "voters": self._signal["voters"],
        })

    def _mark_received(self, timestamp: datetime | None) -> None:
        """Record that a live event was received (honest no-data detection)."""
        self._has_data = True
        self._last_update = timestamp

    def has_data(self) -> bool:
        """True once any live regime/signal event has been received."""
        return self._has_data

    def last_update(self) -> datetime | None:
        return self._last_update

    def get_regime(self) -> dict[str, Any]:
        return dict(self._regime)

    def get_signal(self) -> dict[str, Any]:
        return dict(self._signal)

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.REGIME_CHANGED, self.on_regime_changed)
        bus.subscribe(Topic.SIGNAL_V2, self.on_signal_v2)
        bus.subscribe(Topic.SIGNAL_GENERATED, self.on_signal_v2)


# ── Scanner Projection ─────────────────────────────────────────────────────

class ScannerProjection:
    """Subscribes to SCANNER_FINDING, stores capped per-type finding lists.

    Each finding carries ``scanner_type`` (a string matching ScannerType
    values), ``symbol``, ``severity``, ``detail``, and ``timestamp``.
    The projection groups findings by scanner_type so the REST endpoint
    can filter by type.
    """

    MAX_PER_TYPE = 100

    def __init__(self) -> None:
        self._findings: dict[str, list[dict[str, Any]]] = {}

    async def on_scanner_finding(self, event: Event) -> None:
        d = event.data
        if not isinstance(d, dict):
            return
        scanner_type = d.get("scanner_type", "unknown")
        if scanner_type not in self._findings:
            self._findings[scanner_type] = []
        self._findings[scanner_type].append({
            "scanner_type": scanner_type,
            "symbol": d.get("symbol", ""),
            "severity": d.get("severity", "MEDIUM"),
            "detail": d.get("detail", {}),
            "timestamp": d.get("timestamp", event.timestamp),
        })
        if len(self._findings[scanner_type]) > self.MAX_PER_TYPE:
            self._findings[scanner_type] = self._findings[scanner_type][-self.MAX_PER_TYPE:]

    def get(self, scanner_type: str | None = None) -> list[dict[str, Any]]:
        """Return findings, optionally filtered by scanner_type."""
        if scanner_type:
            return list(self._findings.get(scanner_type, []))
        result: list[dict[str, Any]] = []
        for findings in self._findings.values():
            result.extend(findings)
        # Sort by timestamp descending (most recent first)
        result.sort(key=lambda f: str(f.get("timestamp", "")), reverse=True)
        return result

    def count_by_type(self) -> dict[str, int]:
        """Return count of findings per scanner type."""
        return {k: len(v) for k, v in self._findings.items()}

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.SCANNER_FINDING, self.on_scanner_finding)


def _data_adapter_connected(adapter: Any) -> bool | None:
    """Sync connectivity view that works for both adapter shapes.

    Dhan-era adapters expose ``_connected``; the Fyers data adapter holds
    the HSM data-socket wrapper (``_data_socket``) whose ``connected``
    property is the live link. Returns None when neither exists — the
    health projection must not claim "disconnected" without evidence.
    """
    connected = getattr(adapter, "_connected", None)
    if connected is not None:
        return bool(connected)
    socket = getattr(adapter, "_data_socket", None)
    if socket is not None:
        return bool(getattr(socket, "connected", False))
    return None


def _data_adapter_reconnecting(adapter: Any) -> bool:
    """True when the data-socket supervisor is actively retrying.

    The Fyers data socket sets ``_reconnecting = True`` during backoff
    (``data_socket.py:288``).  During reconnect the ``connected`` property
    returns False, but the UI should show CONNECTING, not DISCONNECTED.
    """
    if getattr(adapter, "_reconnecting", False):
        return True
    socket = getattr(adapter, "_data_socket", None)
    if socket is not None:
        return bool(getattr(socket, "_reconnecting", False))
    return False


def _data_adapter_stale(
    adapter: Any,
    threshold: float = _TICK_STALE_SECONDS,
    tick_timestamp: datetime | None = None,
) -> bool:
    """True when no fresh ticks have arrived past the threshold.

    P1-2.4: now checks the adapter's own ``is_stale`` method first (for
    adapters that implement it), then falls back to a tick-activity-based
    check using the projection's ``tick_timestamp`` (set by the
    ``MARKET_DATA_TICK`` subscriber).
    """
    is_stale = getattr(adapter, "is_stale", None)
    if is_stale is not None:
        try:
            return bool(is_stale(threshold=threshold))
        except (TypeError, AttributeError):
            pass
    # Fallback: tick-activity-based staleness (P1-2.4).
    if tick_timestamp is not None:
        return (datetime.now(UTC) - tick_timestamp).total_seconds() > threshold
    return False


# ── Health Projection ────────────────────────────────────────────────────────

class HealthProjection:
    """Stateful, event-driven health projection (P1-2.4).

    Subscribes to ``SYSTEM_STATUS``, ``CREDENTIAL_HEALTH_CHANGED``, and
    ``MARKET_DATA_TICK`` on the EventBus and maintains a single
    :class:`ConnectionState` value as the canonical connection status.
    Pushes state transitions to the browser via ``ws_bridge.broadcast()``
    so the UI is event-driven, not purely polled.
    """

    def __init__(self) -> None:
        self._event_bus: EventBus | None = None
        self._data_adapter: Any = None
        self._trading_adapter: Any = None
        self._feature_engine: Any = None
        self._signal_engine: Any = None
        self._token_health_provider: Any = None
        # P1-2.4: stateful connection tracking.
        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._last_credential_status: str = "UNKNOWN"
        self._last_tick_ts: datetime | None = None
        self._last_transition_detail: str = ""

    def subscribe(self, event_bus: EventBus) -> None:
        """Store the bus reference AND subscribe to health-relevant topics."""
        self._event_bus = event_bus
        event_bus.subscribe(Topic.SYSTEM_STATUS, self.on_system_status)
        event_bus.subscribe(Topic.CREDENTIAL_HEALTH_CHANGED, self.on_credential_health)
        event_bus.subscribe(Topic.MARKET_DATA_TICK, self.on_market_data_tick)

    def configure(
        self,
        event_bus: EventBus | None = None,
        data_adapter: Any = None,
        trading_adapter: Any = None,
        feature_engine: Any = None,
        signal_engine: Any = None,
        token_health_provider: Any = None,
    ) -> None:
        """Configure live references; ``token_health_provider`` is a zero-arg
        callable returning True while the trading token is valid."""
        self._event_bus = event_bus
        self._data_adapter = data_adapter
        self._trading_adapter = trading_adapter
        self._feature_engine = feature_engine
        self._signal_engine = signal_engine
        self._token_health_provider = token_health_provider

    # ── Event handlers (P1-2.4) ────────────────────────────────────────────

    async def on_system_status(self, event: Event) -> None:
        """SYSTEM_STATUS handler: socket connected / closed / error / reconnecting."""
        status = event.data.get("status", "") if isinstance(event.data, dict) else ""
        old = self._state
        if status in ("connected", "data_socket_connected"):
            self._state = ConnectionState.CONNECTED
            self._last_transition_detail = "Data socket connected"
        elif status in ("reconnecting", "data_socket_reconnecting"):
            self._state = ConnectionState.CONNECTING
            self._last_transition_detail = "Reconnecting…"
        elif status in ("disconnected", "data_socket_closed", "error", "data_socket_error", "stopped"):
            self._state = ConnectionState.DISCONNECTED
            detail = str(event.data.get("error", "")) if isinstance(event.data, dict) else ""
            self._last_transition_detail = detail or f"Socket {status}"
        if self._state != old:
            await self._broadcast_transition()

    async def on_credential_health(self, event: Event) -> None:
        """CREDENTIAL_HEALTH_CHANGED handler: EXPIRED / EXPIRING_SOON / HEALTHY."""
        status = event.data.get("status", "UNKNOWN") if isinstance(event.data, dict) else "UNKNOWN"
        self._last_credential_status = status
        old = self._state
        if status in ("EXPIRED", "EXPIRING_SOON"):
            self._state = ConnectionState.EXPIRED
            self._last_transition_detail = f"Token {status.lower()}"
        elif status == "HEALTHY" and old == ConnectionState.EXPIRED:
            # Token refreshed after EXPIRED — return to CONNECTING while the
            # socket re-establishes.
            self._state = ConnectionState.CONNECTING
            self._last_transition_detail = "Token refreshed — reconnecting"
        if self._state != old:
            await self._broadcast_transition()

    async def on_market_data_tick(self, event: Event) -> None:
        """MARKET_DATA_TICK handler: track last-tick timestamp for STALE detection."""
        self._last_tick_ts = event.timestamp

    async def _broadcast_transition(self) -> None:
        """Push the current state to all connected WS clients."""
        await ws_bridge.broadcast("connection", {
            "state": self._state.value,
            "detail": self._last_transition_detail,
        })

    # ── State computation ──────────────────────────────────────────────────

    def _compute_state(self) -> tuple[ConnectionState, str]:
        """Derive the canonical connection state from all inputs.

        Priority (highest first):
          EXPIRED  — token is dead, nothing else matters
          DISCONNECTED — data socket is down (not reconnecting)
          CONNECTING — data socket is reconnecting
          STALE — connected but no ticks for >60s
          CONNECTED — all systems nominal
        """
        # Token expiry supersedes everything.
        if self._last_credential_status in ("EXPIRED", "EXPIRING_SOON"):
            return ConnectionState.EXPIRED, "Token expired — re-authentication required"
        # Token health provider (callable) as fallback.
        if (self._token_health_provider is not None
                and not self._token_health_provider()):
            return ConnectionState.EXPIRED, "Token expired — re-authentication required"

        da = self._data_adapter
        if da is None:
            return ConnectionState.DISCONNECTED, "Data adapter not initialized"
        if getattr(da, "entitlement_error", False):
            return ConnectionState.DISCONNECTED, "Data API entitlement missing"

        connected = _data_adapter_connected(da)
        if connected is False:
            if _data_adapter_reconnecting(da):
                return ConnectionState.CONNECTING, "Reconnecting data socket…"
            return ConnectionState.DISCONNECTED, "Data socket disconnected"
        if _data_adapter_stale(da, tick_timestamp=self._last_tick_ts):
            return ConnectionState.STALE, "No market data ticks for >60s"

        return ConnectionState.CONNECTED, ""

    # ── Public API ─────────────────────────────────────────────────────────

    def get(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        components: list[dict[str, Any]] = []

        # EventBus — running state only; latency is not measured here (never fabricated).
        eb_status = "healthy"
        eb_msg = ""
        if self._event_bus is None:
            eb_status = "down"
            eb_msg = "Not initialized"
        elif not self._event_bus._running:
            eb_status = "down"
            eb_msg = "Not running"
        components.append({
            "name": "event_bus",
            "status": eb_status,
            "latency_ms": None,
            "last_check": now,
            "message": eb_msg,
        })

        # Data adapter — now with CONNECTING and tick-based STALE.
        da_status = "healthy"
        da_msg = ""
        if self._data_adapter is None:
            da_status = "down"
            da_msg = "Not initialized (no credentials)"
        elif getattr(self._data_adapter, "entitlement_error", False):
            da_status = "down"
            da_msg = "Data API entitlement missing (Fyers 403/-373) — subscribe to Data APIs"
        elif _data_adapter_connected(self._data_adapter) is False:
            if _data_adapter_reconnecting(self._data_adapter):
                da_status = "connecting"
                da_msg = "Reconnecting data socket…"
            else:
                da_status = "disconnected"
                da_msg = "WebSocket not connected"
        elif _data_adapter_stale(self._data_adapter, tick_timestamp=self._last_tick_ts):
            da_status = "stale"
            da_msg = f"No market data ticks for >{int(_TICK_STALE_SECONDS)}s"
        components.append({
            "name": "data_adapter",
            "status": da_status,
            "latency_ms": None,
            "last_check": now,
            "message": da_msg,
        })

        # Trading adapter — now also checks is_connected() (P1-2.4).
        ta_status = "healthy"
        ta_msg = ""
        if self._trading_adapter is None:
            ta_status = "down"
            ta_msg = "Not initialized (no credentials)"
        elif self._token_health_provider is not None and not self._token_health_provider():
            ta_status = "token_expired"
            ta_msg = "Token expired — re-authentication required"
        elif hasattr(self._trading_adapter, "is_connected"):
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Can't await in sync context — use is_session_valid as
                    # a cheap proxy (FyersTradingAdapter.is_connected delegates
                    # to session.is_valid anyway).
                    if hasattr(self._trading_adapter, "is_session_valid"):
                        if not self._trading_adapter.is_session_valid():
                            ta_status = "disconnected"
                            ta_msg = "Trading session invalid"
                # If loop is not running, we could await, but get() is sync —
                # fall through to is_session_valid as the safe proxy.
            except RuntimeError:
                if hasattr(self._trading_adapter, "is_session_valid"):
                    if not self._trading_adapter.is_session_valid():
                        ta_status = "disconnected"
                        ta_msg = "Trading session invalid"
        components.append({
            "name": "trading_adapter",
            "status": ta_status,
            "latency_ms": None,
            "last_check": now,
            "message": ta_msg,
        })

        # Intelligence pipeline (features/signal engines)
        ip_status = "healthy"
        ip_msg = ""
        if self._feature_engine is None or self._signal_engine is None:
            ip_status = "disconnected"
            ip_msg = "Intelligence pipeline not initialized"
        components.append({
            "name": "intelligence",
            "status": ip_status,
            "latency_ms": None,
            "last_check": now,
            "message": ip_msg,
        })

        # Storage — no latency probe wired yet; never fabricate a value.
        components.append({
            "name": "storage",
            "status": "healthy",
            "latency_ms": None,
            "last_check": now,
            "message": "",
        })

        overall = "healthy"
        for c in components:
            if c["status"] == "down":
                overall = "down"
                break
            if c["status"] not in ("healthy", "connecting") and overall != "down":
                overall = "degraded"

        # P1-2.4: derive and store the canonical connection state.
        self._state, self._last_transition_detail = self._compute_state()

        return {
            "components": components,
            "overall": overall,
            "state": self._state.value,
            "detail": self._last_transition_detail,
        }
