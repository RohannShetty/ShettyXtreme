"""Tests for PositionManager — CRITICAL: TP3 reachable, TSL favourable-only."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from shettyxtreme.execution.position_manager import (
    Action,
    ManagedPosition,
    PositionManager,
)
from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
)


def _make_signal() -> Signal:
    return Signal(direction=SignalDirection.UP, conviction=0.8, D=0.6, P=1.0, G=0.1, voters=[])


@pytest.mark.asyncio
async def test_tp3_reachable_before_tsl() -> None:
    """TP3 must win even when TSL would also trigger at same LTP."""
    pm = PositionManager()
    pos = ManagedPosition(
        symbol="NIFTY",
        entry_price=100.0,
        quantity=75,
        direction=1,
        atr=5.0,
        ltp=210.0,  # hits tp3=200
    )
    action = await pm.manage_position(pos, _make_signal())
    assert action.action == Action.EXIT_TP3
    assert action.action != Action.EXIT_TSL


@pytest.mark.asyncio
async def test_tp1_and_tp2_hit() -> None:
    pm = PositionManager()
    pos1 = ManagedPosition(symbol="X", entry_price=100.0, quantity=75, direction=1, atr=5.0, ltp=131.0)  # tp1=130
    action1 = await pm.manage_position(pos1, _make_signal())
    assert action1.action == Action.EXIT_TP1

    pos2 = ManagedPosition(symbol="X", entry_price=100.0, quantity=75, direction=1, atr=5.0, ltp=161.0)  # tp2=160
    action2 = await pm.manage_position(pos2, _make_signal())
    assert action2.action == Action.EXIT_TP2


@pytest.mark.asyncio
async def test_short_tp_hit() -> None:
    pm = PositionManager()
    # short: tp1=70, tp2=40, tp3=0. ltp=69 hits tp1 (nearest in profit) first.
    pos = ManagedPosition(symbol="X", entry_price=100.0, quantity=75, direction=-1, atr=5.0, ltp=69.0)
    action = await pm.manage_position(pos, _make_signal())
    assert action.action == Action.EXIT_TP1

    # deeper: ltp=39 is past tp1(70) and tp2(40)? 39<=40 -> tp2 reached
    pos2 = ManagedPosition(symbol="X", entry_price=100.0, quantity=75, direction=-1, atr=5.0, ltp=39.0)
    action2 = await pm.manage_position(pos2, _make_signal())
    assert action2.action == Action.EXIT_TP2


@pytest.mark.asyncio
async def test_tsl_hit_without_tp(monkeypatch: pytest.MonkeyPatch) -> None:
    pm = PositionManager()
    # Pre-set an activated trailing stop below entry; ltp drops to it.
    pos = ManagedPosition(
        symbol="X",
        entry_price=100.0,
        quantity=75,
        direction=1,
        atr=5.0,
        ltp=93.0,  # below pre-set tsl, no TP hit
        tsl=95.0,
    )

    class _FakeDT:
        @staticmethod
        def now(tz=None) -> datetime:
            return datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)

    monkeypatch.setattr("shettyxtreme.execution.position_manager.datetime", _FakeDT)
    action = await pm.manage_position(pos, _make_signal())
    assert action.action == Action.EXIT_TSL
    assert pos.tsl is not None


@pytest.mark.asyncio
async def test_eod_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    pm = PositionManager()
    pos = ManagedPosition(symbol="X", entry_price=100.0, quantity=75, direction=1, atr=5.0, ltp=101.0)

    class _FakeDT:
        @staticmethod
        def now(tz=None) -> datetime:
            return datetime(2026, 1, 1, 15, 30, tzinfo=timezone.utc)

    monkeypatch.setattr("shettyxtreme.execution.position_manager.datetime", _FakeDT)
    action = await pm.manage_position(pos, _make_signal())
    assert action.action == Action.EXIT_EOD


@pytest.mark.asyncio
async def test_hold_when_nothing_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    pm = PositionManager()
    pos = ManagedPosition(symbol="X", entry_price=100.0, quantity=75, direction=1, atr=5.0, ltp=100.5)

    class _FakeDT:
        @staticmethod
        def now(tz=None) -> datetime:
            return datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)

    monkeypatch.setattr("shettyxtreme.execution.position_manager.datetime", _FakeDT)
    action = await pm.manage_position(pos, _make_signal())
    assert action.action == Action.HOLD


@pytest.mark.asyncio
async def test_tsl_only_moves_favourably() -> None:
    pm = PositionManager()
    pos = ManagedPosition(symbol="X", entry_price=100.0, quantity=75, direction=1, atr=5.0, ltp=120.0)
    pm._update_tsl(pos)
    first_tsl = pos.tsl
    assert first_tsl is not None
    # Improve price (more profit) -> TSL should only increase
    pos.ltp = 130.0
    pm._update_tsl(pos)
    assert pos.tsl is not None
    assert pos.tsl >= first_tsl
    # Worsen price (price drops) -> TSL must NOT widen
    pos.ltp = 115.0
    pm._update_tsl(pos)
    assert pos.tsl == first_tsl


@pytest.mark.asyncio
async def test_tsl_not_activated_before_min_profit() -> None:
    pm = PositionManager()
    pos = ManagedPosition(symbol="X", entry_price=100.0, quantity=75, direction=1, atr=5.0, ltp=100.05)
    pm._update_tsl(pos)
    assert pos.tsl is None


def test_config_defaults_and_custom() -> None:
    pm = PositionManager()
    assert pm.tp1_percent == 0.30
    assert pm.tp3_percent == 1.00
    pm2 = PositionManager(config={"tp1_percent": 0.5, "tsl_atr_multiplier": 2.0})
    assert pm2.tp1_percent == 0.5
    assert pm2.tsl_atr_multiplier == 2.0
