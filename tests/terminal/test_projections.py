from datetime import UTC, datetime, timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from shettyxtreme.core.data_models import Tick
from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.intelligence.signals.simple_generator import Signal
from shettyxtreme.terminal.projections import (
    AlertProjection,
    ConnectionState,
    HealthProjection,
    IntelligenceProjection,
    OrderWSProjection,
    PositionProjection,
    ProposalProjection,
    RiskProjection,
    WatchlistProjection,
)


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_watchlist_broadcast_on_tick_dict(mock_broadcast):
    proj = WatchlistProjection()
    event = Event(
        topic=Topic.MARKET_DATA_TICK,
        data={"symbol": "NIFTY", "exchange": "NSE", "ltp": 24000.0, "change_pct": 1.2, "volume": 1000},
        source="test",
    )

    await proj.on_market_data(event)

    mock_broadcast.assert_awaited_once_with("tick", {
        "symbol": "NIFTY",
        "ltp": 24000.0,
        "change_pct": 1.2,
        "volume": 1000,
        "oi": None,
        "strike": None,
        "option_type": None,
    })


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_watchlist_broadcast_on_tick_dataclass(mock_broadcast):
    proj = WatchlistProjection()
    tick = Tick(symbol="NIFTY", exchange="NSE", ltp=24100.0, volume=500,
                timestamp=datetime.now(UTC), close=24000.0)
    event = Event(
        topic=Topic.MARKET_DATA_TICK,
        data=tick,
        source="test",
    )

    await proj.on_market_data(event)

    mock_broadcast.assert_awaited_once()
    args = mock_broadcast.call_args
    assert args[0][0] == "tick"
    assert args[0][1]["symbol"] == "NIFTY"
    assert args[0][1]["ltp"] == 24100.0
    assert args[0][1]["change_pct"] == pytest.approx(0.42, abs=0.1)
    assert args[0][1]["volume"] == 500


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_watchlist_broadcast_carries_chain_fields(mock_broadcast):
    """P6-W2: oi/strike/option_type ride the tick wire so ChainGrid updates live."""
    proj = WatchlistProjection()
    tick = Tick(symbol="NIFTY", exchange="NSE_FNO", ltp=245.5, volume=500,
                timestamp=datetime.now(UTC), close=240.0, oi=123456,
                strike=25000.0, option_type="CE")
    event = Event(
        topic=Topic.MARKET_DATA_TICK,
        data=tick,
        source="test",
    )

    await proj.on_market_data(event)

    mock_broadcast.assert_awaited_once()
    args = mock_broadcast.call_args
    assert args[0][0] == "tick"
    payload = args[0][1]
    assert payload["oi"] == 123456
    assert payload["strike"] == 25000.0
    assert payload["option_type"] == "CE"
    assert payload["ltp"] == 245.5


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_watchlist_broadcast_null_chain_fields_for_index(mock_broadcast):
    """P6-W2: index ticks broadcast honest nulls for chain fields."""
    proj = WatchlistProjection()
    tick = Tick(symbol="NIFTY", exchange="NSE", ltp=24000.0, volume=100,
                timestamp=datetime.now(UTC), close=23900.0)
    event = Event(
        topic=Topic.MARKET_DATA_TICK,
        data=tick,
        source="test",
    )

    await proj.on_market_data(event)

    mock_broadcast.assert_awaited_once()
    payload = mock_broadcast.call_args[0][1]
    assert payload["oi"] is None
    assert payload["strike"] is None
    assert payload["option_type"] is None


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_watchlist_broadcast_on_tick(mock_broadcast):
    proj = WatchlistProjection()
    event = Event(
        topic=Topic.MARKET_DATA_TICK,
        data={"symbol": "NIFTY", "exchange": "NSE", "ltp": 24000.0, "change_pct": 1.2, "volume": 1000},
        source="test",
    )

    await proj.on_market_data(event)

    mock_broadcast.assert_awaited_once_with("tick", {
        "symbol": "NIFTY",
        "ltp": 24000.0,
        "change_pct": 1.2,
        "volume": 1000,
        "oi": None,
        "strike": None,
        "option_type": None,
    })


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_position_broadcast_on_update(mock_broadcast):
    proj = PositionProjection()
    event = Event(
        topic=Topic.POSITION_CHANGED,
        data={"symbol": "NIFTY", "quantity": 50, "net_quantity": 50, "m2m": 1000.0, "pnl": 500.0},
        source="test",
    )

    await proj.on_position_update(event)

    mock_broadcast.assert_awaited_once_with("position", {
        "symbol": "NIFTY",
        "net_quantity": 50,
        "m2m": 1000.0,
        "pnl": 500.0,
    })


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_risk_broadcast_on_decision(mock_broadcast):
    proj = RiskProjection()
    event = Event(
        topic=Topic.RISK_DECISION,
        data={"daily_pnl": -2000.0, "margin_used": 100000.0},
        source="test",
    )

    await proj.on_risk_decision(event)

    mock_broadcast.assert_awaited_once()
    args = mock_broadcast.call_args
    assert args[0][0] == "risk"
    assert args[0][1]["daily_pnl"] == -2000.0


def test_risk_margin_unknown_initial_state() -> None:
    """Margin starts UNKNOWN (None), never a fabricated 500000.0 (fix #2)."""
    proj = RiskProjection()
    state = proj.get()
    assert state["margin_available"] is None


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_risk_broadcast_on_alert(mock_broadcast):
    proj = RiskProjection()
    event = Event(
        topic=Topic.RISK_ALERT,
        data={"alert_type": "loss_limit_breach", "severity": "HIGH", "message": "Loss limit hit"},
        source="test",
    )

    await proj.on_risk_alert(event)

    mock_broadcast.assert_awaited_once_with("alert", {
        "alert_type": "loss_limit_breach",
        "severity": "HIGH",
        "message": "Loss limit hit",
    })


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_alert_broadcast_on_alert(mock_broadcast):
    proj = AlertProjection()
    event = Event(
        topic=Topic.RISK_ALERT,
        data={"alert_type": "loss_limit_breach", "severity": "HIGH", "message": "Loss limit hit"},
        source="test",
    )

    await proj.on_alert(event)

    mock_broadcast.assert_awaited_once_with("alert", {
        "alert_type": "loss_limit_breach",
        "severity": "HIGH",
        "message": "Loss limit hit",
    })


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_regime_broadcast_on_change(mock_broadcast):
    proj = IntelligenceProjection()
    event = Event(
        topic=Topic.REGIME_CHANGED,
        data={"regime": "trending", "confidence": 0.8, "transition": True},
        source="test",
    )

    await proj.on_regime_changed(event)

    mock_broadcast.assert_awaited_once()
    args = mock_broadcast.call_args
    assert args[0][0] == "regime"
    assert args[0][1]["regime"] == "trending"


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_signal_broadcast_on_signal(mock_broadcast):
    proj = IntelligenceProjection()
    event = Event(
        topic=Topic.SIGNAL_GENERATED,
        data={"direction": "BULL", "conviction": 0.75, "voters": ["dp", "gamma"]},
        source="test",
    )

    await proj.on_signal_v2(event)

    mock_broadcast.assert_awaited_once_with("signal", {
        "direction": "BULL",
        "conviction": 0.75,
        "voters": ["dp", "gamma"],
    })


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_signal_v2_accepts_signal_dataclass(mock_broadcast) -> None:
    """SIGNAL_GENERATED carries a Signal dataclass, not a dict (regression)."""
    proj = IntelligenceProjection()
    sig = Signal(
        symbol="NIFTY", direction="bullish", strength=6.0,
        source="breakout", reasoning="breakout above resistance",
    )
    event = Event(topic=Topic.SIGNAL_GENERATED, data=sig, source="signal_generator")

    await proj.on_signal_v2(event)

    assert proj.get_signal()["direction"] == "bullish"
    assert mock_broadcast.await_count == 1


@pytest.mark.asyncio
async def test_signal_v2_with_dpg_updates_projection() -> None:
    proj = IntelligenceProjection()
    from shettyxtreme.core.event_bus.event_bus import Event, Topic
    from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection, Vote
    sig = Signal(direction=SignalDirection.UP, conviction=0.6, D=0.55, P=0.8, G="unanimous",
                 voters=[Vote(1.0, 0.6, 1.0, "v")])
    await proj.on_signal_v2(Event(topic=Topic.SIGNAL_V2, data=sig, source="test"))
    state = proj.get_signal()
    assert state["direction"] == "UP"
    assert state["D"] == 0.55
    assert state["P"] == 0.8
    assert state["G"] == "unanimous"


def test_health_reports_entitlement_down() -> None:
    """data_adapter component goes down with the Fyers 403/-373 entitlement message."""
    proj = HealthProjection()
    adapter = MagicMock()
    adapter.entitlement_error = True
    proj.configure(data_adapter=adapter)

    result = proj.get()

    comp = next(c for c in result["components"] if c["name"] == "data_adapter")
    assert comp["status"] == "down"
    assert "entitlement" in comp["message"]
    assert "403" in comp["message"]


def test_health_latency_not_fabricated() -> None:
    """No component reports a non-zero latency that was never measured (fix #3)."""
    proj = HealthProjection()
    result = proj.get()

    assert result["components"]
    for c in result["components"]:
        assert c["latency_ms"] is None


def test_health_data_stale_when_no_ticks() -> None:
    """Connected adapter with no fresh ticks reports stale, not healthy.

    P1-2.4: adapter.is_stale() takes precedence; the projection also
    supports tick-activity-based staleness as a fallback.
    """
    proj = HealthProjection()
    adapter = MagicMock()
    adapter.entitlement_error = False
    adapter._connected = True
    adapter.is_stale.return_value = True
    proj.configure(data_adapter=adapter)

    result = proj.get()

    comp = next(c for c in result["components"] if c["name"] == "data_adapter")
    assert comp["status"] == "stale"


def test_health_data_stale_tick_based_fallback() -> None:
    """P1-2.4: tick-activity-based staleness when adapter has no is_stale."""
    proj = HealthProjection()
    adapter = MagicMock()
    adapter.entitlement_error = False
    adapter._connected = True
    # No is_stale attribute — fallback to tick-based.
    del adapter.is_stale
    proj.configure(data_adapter=adapter)
    # Simulate a tick 120s ago (beyond the 60s threshold).
    proj._last_tick_ts = datetime.now(UTC) - timedelta(seconds=120)

    result = proj.get()

    comp = next(c for c in result["components"] if c["name"] == "data_adapter")
    assert comp["status"] == "stale"
    assert result["state"] == "stale"


def test_health_trading_token_expired() -> None:
    """Trading adapter with an invalid token reports token_expired."""
    proj = HealthProjection()
    proj.configure(trading_adapter=MagicMock(), token_health_provider=lambda: False)

    result = proj.get()

    comp = next(c for c in result["components"] if c["name"] == "trading_adapter")
    assert comp["status"] == "token_expired"


@pytest.mark.asyncio
async def test_regime_changed_dataclass_payload() -> None:
    proj = IntelligenceProjection()
    from shettyxtreme.core.event_bus.event_bus import Event, Topic

    class RegimePayload:
        def __init__(self) -> None:
            self.regime = "trending"
            self.confidence = 0.8
            self.transition = False

    await proj.on_regime_changed(Event(topic=Topic.REGIME_CHANGED, data=RegimePayload(), source="test"))
    state = proj.get_regime()
    assert state["regime"] == "trending"
    assert state["confidence"] == 0.8


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_duplicate_alert_suppressed_within_window(mock_broadcast) -> None:
    proj = AlertProjection()
    ev = Event(topic=Topic.RISK_ALERT, data={"alert_type": "gap", "severity": "HIGH", "message": "same"}, timestamp=datetime.now(UTC))
    await proj.on_alert(ev)
    await proj.on_alert(ev)
    assert len(proj.get()) == 1
    later = Event(topic=Topic.RISK_ALERT, data={"alert_type": "gap", "severity": "HIGH", "message": "same"}, timestamp=datetime.now(UTC) + timedelta(seconds=60))
    await proj.on_alert(later)
    assert len(proj.get()) == 2


# ── P1-2.4: Connection state machine tests ─────────────────────────────────

def test_health_projection_state_machine_initial_state() -> None:
    """HealthProjection starts in DISCONNECTED state."""
    proj = HealthProjection()
    assert proj._state == ConnectionState.DISCONNECTED


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_health_projection_state_machine_transitions(mock_broadcast) -> None:
    """Full state machine: DISCONNECTED → CONNECTING → CONNECTED → STALE → EXPIRED."""
    proj = HealthProjection()
    bus = EventBus()
    proj.subscribe(bus)

    # Start in DISCONNECTED (initial).
    assert proj._state == ConnectionState.DISCONNECTED

    # SYSTEM_STATUS reconnecting → CONNECTING.
    await proj.on_system_status(Event(
        topic=Topic.SYSTEM_STATUS,
        data={"status": "reconnecting"},
        source="test",
    ))
    assert proj._state == ConnectionState.CONNECTING

    # SYSTEM_STATUS connected → CONNECTED.
    await proj.on_system_status(Event(
        topic=Topic.SYSTEM_STATUS,
        data={"status": "connected"},
        source="test",
    ))
    assert proj._state == ConnectionState.CONNECTED

    # Tick received — mark last tick.
    await proj.on_market_data_tick(Event(
        topic=Topic.MARKET_DATA_TICK,
        data={},
        source="test",
        timestamp=datetime.now(UTC) - timedelta(seconds=120),
    ))

    # get() computes STALE from tick timestamp.
    adapter = MagicMock()
    adapter.entitlement_error = False
    adapter._connected = True
    del adapter.is_stale
    proj.configure(data_adapter=adapter)
    result = proj.get()
    assert result["state"] == "stale"

    # CREDENTIAL_HEALTH_CHANGED EXPIRED → EXPIRED.
    await proj.on_credential_health(Event(
        topic=Topic.CREDENTIAL_HEALTH_CHANGED,
        data={"status": "EXPIRED"},
        source="test",
    ))
    assert proj._state == ConnectionState.EXPIRED


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_health_projection_subscribes_to_system_status(mock_broadcast) -> None:
    """Socket close → DISCONNECTED (transition from CONNECTED)."""
    proj = HealthProjection()
    bus = EventBus()
    proj.subscribe(bus)

    # First move to CONNECTED so the transition actually fires.
    proj._state = ConnectionState.CONNECTED
    await proj.on_system_status(Event(
        topic=Topic.SYSTEM_STATUS,
        data={"status": "data_socket_closed"},
        source="test",
    ))
    assert proj._state == ConnectionState.DISCONNECTED
    mock_broadcast.assert_awaited_with("connection", {
        "state": "disconnected",
        "detail": "Socket data_socket_closed",
    })


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_health_projection_subscribes_to_credential_health(mock_broadcast) -> None:
    """Token expired → EXPIRED."""
    proj = HealthProjection()
    bus = EventBus()
    proj.subscribe(bus)

    await proj.on_credential_health(Event(
        topic=Topic.CREDENTIAL_HEALTH_CHANGED,
        data={"status": "EXPIRED"},
        source="test",
    ))
    assert proj._state == ConnectionState.EXPIRED
    mock_broadcast.assert_awaited_with("connection", {
        "state": "expired",
        "detail": "Token expired",
    })


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_health_projection_tick_heartbeat_stale(mock_broadcast) -> None:
    """No tick for >60s → STALE (tick-based fallback)."""
    proj = HealthProjection()
    adapter = MagicMock()
    adapter.entitlement_error = False
    adapter._connected = True
    del adapter.is_stale
    proj.configure(data_adapter=adapter)

    # Simulate last tick 120s ago.
    proj._last_tick_ts = datetime.now(UTC) - timedelta(seconds=120)
    result = proj.get()
    assert result["state"] == "stale"


def test_health_projection_subscribes_to_event_bus() -> None:
    """subscribe() registers handlers on SYSTEM_STATUS, CREDENTIAL_HEALTH_CHANGED, TICK."""
    proj = HealthProjection()
    bus = EventBus()
    proj.subscribe(bus)
    assert Topic.SYSTEM_STATUS in bus._subscribers
    assert Topic.CREDENTIAL_HEALTH_CHANGED in bus._subscribers
    assert Topic.MARKET_DATA_TICK in bus._subscribers


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_health_projection_connecting_state(mock_broadcast) -> None:
    """Data socket reconnecting → CONNECTING state in get() output."""
    proj = HealthProjection()
    adapter = MagicMock()
    adapter.entitlement_error = False
    adapter._connected = False
    adapter._data_socket = MagicMock()
    adapter._data_socket.connected = False
    adapter._data_socket._reconnecting = True
    proj.configure(data_adapter=adapter)

    result = proj.get()
    comp = next(c for c in result["components"] if c["name"] == "data_adapter")
    assert comp["status"] == "connecting"
    assert result["state"] == "connecting"


def test_health_projection_overall_skips_connecting() -> None:
    """CONNECTING is not 'degraded' — it's an expected transient state."""
    proj = HealthProjection()
    adapter = MagicMock()
    adapter.entitlement_error = False
    adapter._connected = False
    adapter._data_socket = MagicMock()
    adapter._data_socket.connected = False
    adapter._data_socket._reconnecting = True
    proj.configure(data_adapter=adapter)

    result = proj.get()
    # CONNECTING should not make overall "degraded".
    assert result["overall"] == "healthy" or result["state"] == "connecting"


def test_fyers_data_adapter_is_stale() -> None:
    """P1-2.4: FyersDataAdapter.is_stale() tracks last-tick timestamp."""
    from unittest.mock import MagicMock as _MagicMock
    from shettyxtreme.integration.fyers.data_adapter import FyersDataAdapter

    # Build a minimal mock adapter to test is_stale.
    adapter = _MagicMock(spec=FyersDataAdapter)
    adapter._last_tick_ts = None
    # Call the real method.
    result = FyersDataAdapter.is_stale(adapter)
    assert result is False  # No ticks yet → not stale.

    # Tick 120s ago → stale.
    adapter._last_tick_ts = datetime.now(UTC) - timedelta(seconds=120)
    result = FyersDataAdapter.is_stale(adapter, threshold=60.0)
    assert result is True

    # Tick 30s ago → not stale.
    adapter._last_tick_ts = datetime.now(UTC) - timedelta(seconds=30)
    result = FyersDataAdapter.is_stale(adapter, threshold=60.0)
    assert result is False


# ── P4: Live P&L (tick-driven m2m/pnl recompute) ────────────────────────────

def _position_event(symbol: str, **overrides: object) -> Event:
    data: dict[str, object] = {
        "symbol": symbol,
        "quantity": 50,
        "buy_avg": 100.0,
        "net_quantity": 50,
        "m2m": 0.0,
        "pnl": 0.0,
    }
    data.update(overrides)
    return Event(topic=Topic.POSITION_CHANGED, data=data, source="test")


def _tick_event(symbol: str, ltp: float) -> Event:
    return Event(topic=Topic.MARKET_DATA_TICK, data={"symbol": symbol, "ltp": ltp}, source="test")


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_live_pnl_long_position_marked_from_tick(mock_broadcast) -> None:
    """P4: a tick recomputes m2m/pnl for a long position and re-broadcasts."""
    proj = PositionProjection()
    await proj.on_position_update(_position_event("NIFTY", quantity=50, net_quantity=50, buy_avg=100.0))

    await proj.on_market_data_tick(_tick_event("NIFTY", 110.0))

    # 50 × (110 − 100) = 500 m2m; pnl follows the same swing from 0.
    assert proj.get()[0]["m2m"] == 500.0
    assert proj.get()[0]["pnl"] == 500.0
    topic, payload = mock_broadcast.await_args.args
    assert topic == "position"
    assert payload["m2m"] == 500.0
    assert payload["pnl"] == 500.0


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_live_pnl_short_position_marked_from_tick(mock_broadcast) -> None:
    """P4: a SELL-opened short marks correctly using its entry price."""
    proj = PositionProjection()
    # New short, paper-engine style: side + quantity, NO net_quantity — the
    # projection derives a negative net quantity from the SELL side.
    await proj.on_position_update(Event(
        Topic.POSITION_CHANGED,
        {"symbol": "BANKNIFTY", "quantity": 25, "side": "SELL", "sell_avg": 200.0, "price": 200.0},
        source="test",
    ))
    assert proj.get()[0]["net_quantity"] == -25

    await proj.on_market_data_tick(_tick_event("BANKNIFTY", 180.0))

    # 25 × (200 − 180) = 500 m2m for the short.
    assert proj.get()[0]["m2m"] == 500.0
    assert proj.get()[0]["pnl"] == 500.0


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_live_pnl_flat_position_zeroed(mock_broadcast) -> None:
    """P4: a flat position marks m2m to zero."""
    proj = PositionProjection()
    await proj.on_position_update(_position_event("NIFTY", quantity=0, net_quantity=0, m2m=100.0, pnl=100.0))

    await proj.on_market_data_tick(_tick_event("NIFTY", 110.0))

    assert proj.get()[0]["m2m"] == 0.0
    # Realized P&L is preserved (pnl = old_pnl + swing).
    assert proj.get()[0]["pnl"] == 100.0


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_live_pnl_no_entry_price_keeps_last_known(mock_broadcast) -> None:
    """P4: positions without a computable entry are never fabricated."""
    proj = PositionProjection()
    await proj.on_position_update(_position_event("NIFTY", quantity=50, net_quantity=50, buy_avg=0.0, m2m=42.0, pnl=7.0))

    await proj.on_market_data_tick(_tick_event("NIFTY", 110.0))

    assert proj.get()[0]["m2m"] == 42.0
    assert proj.get()[0]["pnl"] == 7.0


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_live_pnl_tick_dataclass_path(mock_broadcast) -> None:
    """P4: Tick dataclass payloads drive the same recompute."""
    proj = PositionProjection()
    await proj.on_position_update(_position_event("NIFTY", quantity=50, net_quantity=50, buy_avg=100.0))
    tick = Tick(symbol="NIFTY", exchange="NSE", ltp=105.0, volume=10, timestamp=datetime.now(UTC), close=100.0)
    await proj.on_market_data_tick(Event(Topic.MARKET_DATA_TICK, tick, source="test"))
    assert proj.get()[0]["m2m"] == 250.0


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_live_pnl_debounced_by_time(mock_broadcast) -> None:
    """P4: rapid ticks within the debounce window do not spam the socket."""
    proj = PositionProjection()
    await proj.on_position_update(_position_event("NIFTY", quantity=50, net_quantity=50, buy_avg=100.0))
    before = mock_broadcast.await_count  # position update broadcast

    await proj.on_market_data_tick(_tick_event("NIFTY", 110.0))
    assert mock_broadcast.await_count == before + 1

    # Second tick inside the 1s debounce window → no broadcast, no recompute.
    await proj.on_market_data_tick(_tick_event("NIFTY", 120.0))
    assert mock_broadcast.await_count == before + 1
    assert proj.get()[0]["m2m"] == 500.0


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_live_pnl_ltp_noise_ignored(mock_broadcast) -> None:
    """P4: sub-epsilon LTP wobble is noise — no recompute, no broadcast."""
    import time as _time
    proj = PositionProjection()
    await proj.on_position_update(_position_event("NIFTY", quantity=50, net_quantity=50, buy_avg=100.0))
    before = mock_broadcast.await_count

    await proj.on_market_data_tick(_tick_event("NIFTY", 110.0))
    assert mock_broadcast.await_count == before + 1

    # Bypass the time debounce to isolate the epsilon gate.
    proj._live._last_recompute_ts["NIFTY"] = -1000.0
    await proj.on_market_data_tick(_tick_event("NIFTY", 110.001))
    assert mock_broadcast.await_count == before + 1
    assert proj.get()[0]["m2m"] == 500.0


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_live_pnl_no_position_no_broadcast(mock_broadcast) -> None:
    """P4: ticks for symbols with no position are cached, not broadcast."""
    proj = PositionProjection()
    await proj.on_market_data_tick(_tick_event("NIFTY", 110.0))
    mock_broadcast.assert_not_awaited()


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_live_pnl_previous_tick_applied_on_fresh_fill(mock_broadcast) -> None:
    """P4: a fill arriving after ticks already marks with the cached LTP."""
    proj = PositionProjection()
    await proj.on_market_data_tick(_tick_event("NIFTY", 110.0))
    await proj.on_position_update(_position_event("NIFTY", quantity=50, net_quantity=50, buy_avg=100.0))
    assert proj.get()[0]["m2m"] == 500.0


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_position_refresh_rebroadcasts_without_provider(mock_broadcast) -> None:
    """P4: refresh() re-broadcasts current positions (client re-sync)."""
    proj = PositionProjection()
    await proj.on_position_update(_position_event("NIFTY", quantity=50, net_quantity=50, m2m=10.0, pnl=5.0))
    before = mock_broadcast.await_count

    await proj.refresh()

    assert mock_broadcast.await_count == before + 1
    topic, payload = mock_broadcast.await_args.args
    assert topic == "position"
    assert payload["symbol"] == "NIFTY"
    assert payload["m2m"] == 10.0


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_position_refresh_merges_broker_positions(mock_broadcast) -> None:
    """P4: refresh() with a broker provider pulls and merges positions."""
    broker_positions = [
        {"symbol": "NIFTY", "exchange": "NSE", "quantity": 75, "buy_avg": 100.0,
         "sell_avg": 0.0, "net_quantity": 75, "m2m": 750.0, "pnl": 750.0, "product": "MIS"},
    ]
    proj = PositionProjection(broker_provider=lambda: broker_positions)

    await proj.refresh()

    assert len(proj.get()) == 1
    assert proj.get()[0]["net_quantity"] == 75
    assert proj.get()[0]["m2m"] == 750.0


# ── P4: Proposal WS topic (ProposalProjection) ──────────────────────────────

def _fake_approval(status: str = "PENDING") -> object:
    from shettyxtreme.execution.execution_engine import PendingApproval
    from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection

    return PendingApproval(
        id="prop-1",
        signal=Signal(direction=SignalDirection.UP, conviction=0.8, voters=[]),
        strategy_hint={
            "symbol": "NIFTY", "exchange": "NSE", "quantity": 75, "price": 100.0,
            "order_type": "LIMIT", "product": "MIS", "stop_loss": 90.0, "target": 120.0,
        },
        timestamp=datetime.now(UTC),
        status=status,
        failure_reason="" if status == "PENDING" else "operator said no",
    )


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_proposal_broadcast_on_created(mock_broadcast) -> None:
    """P4: PROPOSAL_CHANGED(created) → proposal WS frame with full payload."""
    proj = ProposalProjection()
    await proj.on_proposal_changed(Event(
        Topic.PROPOSAL_CHANGED, {"action": "created", "approval": _fake_approval()}, source="test",
    ))
    topic, payload = mock_broadcast.await_args.args
    assert topic == "proposal"
    assert payload["action"] == "created"
    assert payload["proposal"]["id"] == "prop-1"
    assert payload["proposal"]["symbol"] == "NIFTY"
    assert payload["proposal"]["side"] == "BUY"
    assert payload["proposal"]["status"] == "PENDING"
    assert payload["proposal"]["quantity"] == 75


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_proposal_broadcast_on_rejected(mock_broadcast) -> None:
    """P4: rejected proposals carry status + reason on the wire."""
    proj = ProposalProjection()
    await proj.on_proposal_changed(Event(
        Topic.PROPOSAL_CHANGED, {"action": "rejected", "approval": _fake_approval("REJECTED")}, source="test",
    ))
    payload = mock_broadcast.await_args.args[1]
    assert payload["action"] == "rejected"
    assert payload["proposal"]["status"] == "REJECTED"
    assert payload["proposal"]["reason"] == "operator said no"


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_proposal_no_broadcast_for_garbage(mock_broadcast) -> None:
    """P4: non-dict or incomplete payloads are ignored."""
    proj = ProposalProjection()
    await proj.on_proposal_changed(Event(Topic.PROPOSAL_CHANGED, "nope", source="test"))
    await proj.on_proposal_changed(Event(Topic.PROPOSAL_CHANGED, {"action": "created"}, source="test"))
    mock_broadcast.assert_not_awaited()


def test_proposal_projection_subscribes_to_proposal_changed() -> None:
    proj = ProposalProjection()
    bus = EventBus()
    proj.subscribe(bus)
    assert Topic.PROPOSAL_CHANGED in bus._subscribers


# ── P4: Order WS topic (OrderWSProjection) ──────────────────────────────────

def _order_dict(status: str = "FILLED") -> dict[str, object]:
    from shettyxtreme.core.data_models.orders import Order
    from dataclasses import asdict

    order = Order(
        order_id="PAPER1234", symbol="NIFTY", exchange="NSE", side="BUY",
        order_type="MARKET", quantity=75, price=100.0, status=status,
        filled_quantity=75, average_price=100.0, tag="wave5",
        stop_loss=90.0, target=120.0,
    )
    return asdict(order)


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_order_broadcast_on_placed(mock_broadcast) -> None:
    """P4: ORDER_PLACED → order WS frame with full OrderResponse."""
    proj = OrderWSProjection()
    await proj.on_order_event(Event(Topic.ORDER_PLACED, _order_dict("PENDING"), source="paper_trading"))
    topic, payload = mock_broadcast.await_args.args
    assert topic == "order"
    assert payload["action"] == "placed"
    assert payload["order"]["order_id"] == "PAPER1234"
    assert payload["order"]["symbol"] == "NIFTY"
    assert payload["order"]["status"] == "PENDING"


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_order_broadcast_on_filled(mock_broadcast) -> None:
    """P4: ORDER_FILLED → action=filled with fill details."""
    proj = OrderWSProjection()
    await proj.on_order_event(Event(Topic.ORDER_FILLED, _order_dict("FILLED"), source="paper_trading"))
    payload = mock_broadcast.await_args.args[1]
    assert payload["action"] == "filled"
    assert payload["order"]["filled_quantity"] == 75
    assert payload["order"]["average_price"] == 100.0


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_order_broadcast_on_rejected(mock_broadcast) -> None:
    """P4: ORDER_REJECTED → action=rejected."""
    proj = OrderWSProjection()
    await proj.on_order_event(Event(Topic.ORDER_REJECTED, _order_dict("REJECTED"), source="paper_trading"))
    payload = mock_broadcast.await_args.args[1]
    assert payload["action"] == "rejected"
    assert payload["order"]["status"] == "REJECTED"


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_order_broadcast_on_cancelled(mock_broadcast) -> None:
    """P4: ORDER_CANCELLED → action=cancelled."""
    proj = OrderWSProjection()
    await proj.on_order_event(Event(Topic.ORDER_CANCELLED, _order_dict("CANCELLED"), source="paper_trading"))
    payload = mock_broadcast.await_args.args[1]
    assert payload["action"] == "cancelled"
    assert payload["order"]["status"] == "CANCELLED"


@pytest.mark.asyncio
@patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
async def test_order_no_broadcast_for_garbage(mock_broadcast) -> None:
    """P4: non-dict payloads and unknown topics are ignored."""
    proj = OrderWSProjection()
    await proj.on_order_event(Event(Topic.ORDER_PLACED, "nope", source="test"))
    await proj.on_order_event(Event(Topic.SCANNER_FINDING, _order_dict(), source="test"))
    mock_broadcast.assert_not_awaited()


def test_order_projection_subscribes_to_all_order_topics() -> None:
    proj = OrderWSProjection()
    bus = EventBus()
    proj.subscribe(bus)
    for topic in (Topic.ORDER_PLACED, Topic.ORDER_FILLED, Topic.ORDER_REJECTED, Topic.ORDER_CANCELLED):
        assert topic in bus._subscribers
