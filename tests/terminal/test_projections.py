from datetime import UTC, datetime, timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from shettyxtreme.core.data_models import Tick
from shettyxtreme.core.event_bus.event_bus import Event, Topic
from shettyxtreme.intelligence.signals.simple_generator import Signal
from shettyxtreme.terminal.projections import (
    AlertProjection,
    HealthProjection,
    IntelligenceProjection,
    PositionProjection,
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
    """Connected adapter with no fresh ticks reports stale, not healthy."""
    proj = HealthProjection()
    adapter = MagicMock()
    adapter.entitlement_error = False
    adapter._connected = True
    adapter.is_stale.return_value = True
    proj.configure(data_adapter=adapter)

    result = proj.get()

    comp = next(c for c in result["components"] if c["name"] == "data_adapter")
    assert comp["status"] == "stale"


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
