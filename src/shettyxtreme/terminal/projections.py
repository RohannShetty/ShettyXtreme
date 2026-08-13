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
from shettyxtreme.options.max_pain import compute_max_pain
from shettyxtreme.terminal.api import ws_bridge
from shettyxtreme.terminal.api.greeks_store import GreeksStore
from shettyxtreme.terminal.connection_state import (
    ConnectionState,
    _TICK_STALE_SECONDS,
)
from shettyxtreme.terminal.data_adapter_health import (
    data_adapter_connected,
    data_adapter_reconnecting,
    data_adapter_stale,
)
from shettyxtreme.terminal.hint_outcome import (
    close_pnl,
    closing_directions,
    is_closed,
    maybe_record_hint_outcome,
)
from shettyxtreme.terminal.live_pnl import LivePnlTracker
from shettyxtreme.terminal.scanner_bridge import (
    build_scanner_proposal,
    make_scanner_proposal_bridge,
    scanner_bridge_enabled,
    set_scanner_bridge_config,
)
from shettyxtreme.terminal.ws_projections import OrderWSProjection, ProposalProjection

logger = logging.getLogger(__name__)


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

# Greeks history store wiring (3A.4): set by the app lifespan, consumed by
# PositionProjection to persist portfolio greeks snapshots on position changes.
_greeks_store: GreeksStore | None = None


def set_greeks_store(store: GreeksStore | None) -> None:
    """Wire the greeks history store into the projections (app lifespan)."""
    global _greeks_store
    _greeks_store = store


class PositionProjection:
    """Subscribes to POSITION_CHANGED + MARKET_DATA_TICK, updates positions list.

    Phase 4 live P&L: every market tick for a held symbol recomputes the
    position's mark-to-market against the last known entry and re-broadcasts
    on the ``position`` WS topic. Recomputation is debounced (see
    :class:`~shettyxtreme.terminal.live_pnl.LivePnlTracker`) so tick storms
    never flood the socket or the event loop. Positions whose entry price is
    unknown (e.g. a short without an entry recorded) keep their last known
    P&L — the projection never fabricates a number it cannot compute.
    """

    def __init__(self, broker_provider: Any | None = None) -> None:
        self._positions: list[dict[str, Any]] = []
        self._index: dict[str, int] = {}  # symbol -> list index
        self._hint_store: Any = None  # optional HintStore (3A.2 outcome hook)
        # P4 live P&L: LTP cache + debounced m2m math (no position state).
        self._live = LivePnlTracker()
        # Optional positions source for the periodic refresh loop (5s cadence,
        # wired by the app lifespan). Returns raw position dicts.
        self._broker_provider = broker_provider

    def set_hint_store(self, store: Any) -> None:
        """Attach the hint outcome store (3A.2).

        Once attached, closing positions record their outcome against any
        matching recorded hint (win/loss + actual PnL).
        """
        self._hint_store = store

    async def on_position_update(self, event: Event) -> None:
        d = event.data
        symbol = d.get("symbol", "")
        idx = self._index.get(symbol)
        # P3-4.3: merge trade context from fill event into the position
        # projection so the API can surface SL/TGT/rationale/confidence.
        existing = self._positions[idx] if idx is not None else {}
        net_qty = d.get("net_quantity", d.get("quantity", 0))
        # P4: paper fills report side + quantity without net_quantity; a SELL
        # that opens a new short must not be recorded as a long.
        if "net_quantity" not in d and "side" in d and idx is None:
            side = str(d.get("side", "")).upper()
            if side == "SELL":
                net_qty = -int(net_qty or 0)
        pos = {
            "symbol": symbol,
            "exchange": d.get("exchange", existing.get("exchange", "NSE")),
            "quantity": d.get("quantity", 0),
            "buy_avg": d.get("buy_avg", d.get("avg_price", 0.0)),
            "sell_avg": d.get("sell_avg", existing.get("sell_avg", 0.0)),
            "net_quantity": net_qty,
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
        # Recompute from the freshest tick already seen for this symbol.
        last_ltp = self._live.last_ltp(symbol)
        if last_ltp:
            self._live.apply_m2m(pos, last_ltp)
        await self._broadcast_position(pos)
        # 3A.2: when this update closes the position, score any matching
        # hint (win/loss + actual PnL) in the hint outcome store.
        maybe_record_hint_outcome(self._hint_store, d, pos)
        self._record_greeks_snapshot()

    async def on_market_data_tick(self, event: Event) -> None:
        """MARKET_DATA_TICK: recompute m2m/pnl for held symbols (live P&L).

        Delegates debounce + math to :class:`LivePnlTracker`; only positions
        for the ticked symbol are re-marked, and only when the tracker says
        the move is worth broadcasting.
        """
        d = event.data
        if isinstance(d, Tick):
            symbol, ltp = d.symbol, d.ltp
        elif isinstance(d, dict):
            symbol, ltp = d.get("symbol", ""), d.get("ltp")
        else:
            return
        if not symbol or not ltp or float(ltp) <= 0:
            return
        ltp = float(ltp)
        idx = self._index.get(symbol)
        if idx is None:
            self._live.note_tick(symbol, ltp)  # cache even without a position
            return
        recompute_ltp = self._live.note_tick(symbol, ltp)
        if recompute_ltp is None:
            return  # noise or inside the debounce window
        pos = self._positions[idx]
        self._live.apply_m2m(pos, recompute_ltp)
        await self._broadcast_position(pos)

    async def _broadcast_position(self, pos: dict[str, Any]) -> None:
        await ws_bridge.broadcast("position", {
            "symbol": pos["symbol"],
            "net_quantity": pos.get("net_quantity", 0),
            "m2m": pos.get("m2m", 0.0),
            "pnl": pos.get("pnl", 0.0),
        })

    async def refresh(self) -> None:
        """Periodic refresh (5s loop, wired by the app lifespan).

        With a ``broker_provider`` wired, pulls the latest positions from the
        broker/paper engine and merges them into the projection (reusing the
        POSITION_CHANGED pipeline, so the WS broadcast + greeks/hint hooks
        fire). Without a provider it simply re-broadcasts the current list so
        clients that missed an event re-sync.
        """
        if self._broker_provider is not None:
            try:
                raw_positions = self._broker_provider()
            except Exception:
                logger.exception("position refresh: broker provider failed")
                return
            for raw in raw_positions:
                try:
                    await self.on_position_update(Event(
                        Topic.POSITION_CHANGED, raw, source="position_refresh",
                    ))
                except Exception:
                    logger.exception("position refresh: apply failed for %s",
                                     raw.get("symbol", "?"))
            return
        for pos in list(self._positions):
            try:
                await self._broadcast_position(pos)
            except Exception:
                logger.debug("position refresh broadcast failed", exc_info=True)

    def _record_greeks_snapshot(self) -> None:
        """Record the portfolio net greeks into the history store (3A.4).

        Called after every position update. Uses the same IV-cache based
        per-position computation as the execution router; when IV/spot data
        is unavailable the snapshot is skipped (greeks unknown — never
        fabricated). An empty book is recorded as a zeroed snapshot so the
        chart reflects a flat portfolio.
        """
        store = _greeks_store
        if store is None:
            return
        try:
            if not self._positions:
                store.record(0.0, 0.0, 0.0, 0.0, 0)
                return
            from shettyxtreme.integration.fyers.symbols import from_fyers
            from shettyxtreme.terminal.api.execution_router import (
                _compute_position_greeks,
            )

            net_delta = net_gamma = net_theta = net_vega = 0.0
            enriched = 0
            for p in self._positions:
                symbol = p.get("symbol", "")
                net_qty = p.get("net_quantity", 0)
                try:
                    parsed = from_fyers(symbol)
                except (ValueError, ImportError):
                    continue
                if parsed.get("instrument_type") != "OPTION":
                    continue
                strike = parsed.get("strike")
                option_type = parsed.get("option_type")
                expiry = parsed.get("expiry")
                if strike is None or not option_type or expiry is None:
                    continue
                greeks = _compute_position_greeks(strike, option_type, expiry, net_qty)
                if greeks is None:
                    continue
                net_delta += greeks.delta
                net_gamma += greeks.gamma
                net_theta += greeks.theta
                net_vega += greeks.vega
                enriched += 1
            if enriched == 0:
                return
            store.record(net_delta, net_gamma, net_theta, net_vega, len(self._positions))
        except Exception:
            logger.exception("greeks snapshot recording failed")

    def get(self) -> list[dict[str, Any]]:
        return list(self._positions)

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.POSITION_CHANGED, self.on_position_update)
        # P4 live P&L: recompute m2m/pnl from market ticks.
        bus.subscribe(Topic.MARKET_DATA_TICK, self.on_market_data_tick)


# ── Order Projection ─────────────────────────────────────────────────────────

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
    """Subscribes to REGIME_CHANGED / SIGNAL_V2, maintains current regime + signal.

    Phase 3A.3: when an ``analytics_store`` is wired (via constructor or
    :meth:`set_analytics_store`), regime changes are persisted for the
    regime-history chart and option-chain payloads on ``MARKET_DATA_BAR`` are
    reduced to max-pain snapshots for the max-pain chart. Recording failures
    are logged, never raised — analytics must not break live intelligence.
    """

    def __init__(self, analytics_store: Any = None) -> None:
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
        self._analytics_store = analytics_store

    def set_analytics_store(self, store: Any) -> None:
        """Wire the analytics store used for max-pain / regime recording."""
        self._analytics_store = store

    async def on_regime_changed(self, event: Event) -> None:
        d = event.data
        values = getattr(d, "__dict__", d) if not isinstance(d, dict) else d
        if values is None:
            return
        for key in ("regime", "confidence", "transition", "adx", "di_plus", "di_minus"):
            if key in values:
                self._regime[key] = values[key]
        self._record_regime()
        self._mark_received(event.timestamp)
        await ws_bridge.broadcast("regime", dict(self._regime))

    def _record_regime(self) -> None:
        """Persist the current regime snapshot for the regime-history chart."""
        if self._analytics_store is None:
            return
        try:
            self._analytics_store.record_regime(
                regime=str(self._regime.get("regime", "")),
                confidence=float(self._regime.get("confidence", 0.0) or 0.0),
                adx=self._regime.get("adx"),
                di_plus=self._regime.get("di_plus"),
                di_minus=self._regime.get("di_minus"),
            )
        except Exception:
            logger.exception("Regime history recording failed")

    async def on_market_data(self, event: Event) -> None:
        """Persist max pain when an option-chain payload arrives.

        Chain pollers publish ``{symbol, expiry, contracts, spot?}`` dicts on
        ``MARKET_DATA_BAR``; the max pain strike is computed and recorded for
        the max-pain history chart. Non-chain payloads (plain bars, ticks)
        are ignored.
        """
        if self._analytics_store is None:
            return
        data = event.data
        if not isinstance(data, dict):
            return
        contracts = data.get("contracts")
        symbol = data.get("symbol", "")
        if not contracts or not symbol:
            return
        try:
            max_pain = compute_max_pain(contracts)
            if max_pain is None:
                return
            spot_raw = data.get("spot")
            spot_price: float | None = None
            if spot_raw not in (None, ""):
                try:
                    spot_price = float(spot_raw)
                except (TypeError, ValueError):
                    spot_price = None
            self._analytics_store.record_max_pain(
                symbol=symbol,
                expiry=str(data.get("expiry", "")),
                max_pain=max_pain,
                spot_price=spot_price,
            )
        except Exception:
            logger.exception("Max pain history recording failed")

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
        bus.subscribe(Topic.MARKET_DATA_BAR, self.on_market_data)


# ── Scanner Projection ─────────────────────────────────────────────────────

#: Persistent findings store, wired by the lifespan (Phase 3A.1). None when
#: no store exists (unit tests) — recording is skipped silently.
_scanner_store: Any | None = None


def set_scanner_store(store: Any | None) -> None:
    """Attach/detach the persistent scanner-findings store (lifespan wires it)."""
    global _scanner_store
    _scanner_store = store


class ScannerProjection:
    """Subscribes to SCANNER_FINDING, stores capped per-type finding lists.

    Each finding carries ``scanner_type`` (a string matching ScannerType
    values), ``symbol``, ``severity``, ``detail``, and ``timestamp``.
    The projection groups findings by scanner_type so the REST endpoint
    can filter by type.

    Each finding is also pushed to WS clients (topic ``scanner_finding``)
    and recorded in the persistent SQLite store when one is wired.
    """

    MAX_PER_TYPE = 100

    def __init__(self) -> None:
        self._findings: dict[str, list[dict[str, Any]]] = {}
        # P4 scanner→proposal bridge: callable(finding) -> proposal_id | None.
        # The bridge (scanner_bridge.make_scanner_proposal_bridge) owns its
        # own cooldown dedup; None = bridge disabled.
        self._proposal_bridge: Any | None = None

    def set_proposal_bridge(self, bridge: Any | None) -> None:
        """Attach the scanner→proposal bridge (lifespan wires it; opt-in)."""
        self._proposal_bridge = bridge

    async def on_scanner_finding(self, event: Event) -> None:
        d = event.data
        if not isinstance(d, dict):
            return
        scanner_type = d.get("scanner_type", "unknown")
        if scanner_type not in self._findings:
            self._findings[scanner_type] = []
        stored = {
            "scanner_type": scanner_type,
            "symbol": d.get("symbol", ""),
            "severity": d.get("severity", "MEDIUM"),
            "detail": d.get("detail", {}),
            "timestamp": d.get("timestamp", event.timestamp),
        }
        self._findings[scanner_type].append(stored)
        if len(self._findings[scanner_type]) > self.MAX_PER_TYPE:
            self._findings[scanner_type] = self._findings[scanner_type][-self.MAX_PER_TYPE:]
        # Phase 3A.1: real-time alert push + durable history record.
        try:
            await ws_bridge.broadcast("scanner_finding", stored)
        except Exception:
            logger.exception("scanner_finding WS broadcast failed")
        if _scanner_store is not None:
            try:
                _scanner_store.record(stored)
            except Exception:
                logger.exception("scanner finding store record failed")
        # P4: optionally auto-generate an OBSERVER proposal for actionable
        # findings (config-gated, OFF by default — see configs/default.yaml;
        # the bridge factory applies severity/type gates + cooldown dedup).
        if self._proposal_bridge is not None:
            try:
                self._proposal_bridge(stored)
            except Exception:
                logger.exception("scanner proposal bridge failed")

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

        connected = data_adapter_connected(da)
        if connected is False:
            if data_adapter_reconnecting(da):
                return ConnectionState.CONNECTING, "Reconnecting data socket…"
            return ConnectionState.DISCONNECTED, "Data socket disconnected"
        if data_adapter_stale(da, tick_timestamp=self._last_tick_ts):
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
        elif data_adapter_connected(self._data_adapter) is False:
            if data_adapter_reconnecting(self._data_adapter):
                da_status = "connecting"
                da_msg = "Reconnecting data socket…"
            else:
                da_status = "disconnected"
                da_msg = "WebSocket not connected"
        elif data_adapter_stale(self._data_adapter, tick_timestamp=self._last_tick_ts):
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
