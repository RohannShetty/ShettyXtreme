"""Tests for the runtime learning loop (shadow_loop wiring, P4c)."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.intelligence.signals.signal_engine import SignalDirection
from shettyxtreme.intelligence.signals.shadow_manager import ShadowManager
from shettyxtreme.learning.outcome_tracker import OutcomeLabel, OutcomeTracker
from shettyxtreme.learning.shadow_loop import SHADOW_VOTERS, ShadowLoop, session_outcome_label

_EXPECTED_NAMES = [
    "shadow_dpg_vote",
    "shadow_orb_decay",
    "shadow_signal_drift_ev",
    "shadow_time_bucketed_oi",
]


def _make_loop(tmp_path) -> ShadowLoop:
    return ShadowLoop(
        shadow_db_path=str(tmp_path / "shadow.db"),
        learning_db_path=str(tmp_path / "learning.db"),
        session_id_provider=lambda: "sess-1",
        feature_provider=lambda: {"adx": 22.0, "rsi": 55.0},
        regime_provider=lambda: {"regime": "trending_up"},
    )


def _signal_event(direction: str = "UP", conviction: float = 0.6) -> Event:
    return Event(
        topic=Topic.SIGNAL_V2,
        data={
            "direction": direction,
            "conviction": conviction,
            "D": 0.4,
            "P": 0.8,
            "G": "contested",
            "voters": [],
            "timestamp": datetime.now(UTC),
        },
        source="test",
    )


async def _publish_and_drain(
    bus: EventBus, event: Event, ready=None, settle: float = 0.3
) -> None:
    """Publish one event and drain the bus (cancel pattern per P4a tests).

    The bus task is cancelled rather than awaited: under this repo's
    pytest-asyncio Runner, awaiting a running EventBus task never completes.
    """
    task = asyncio.create_task(bus.start())
    try:
        await bus.publish(event)
        if ready is not None:
            for _ in range(100):
                if ready():
                    return
                await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(settle)
    finally:
        await bus.stop()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


def test_register_registers_all_exported_shadow_voters(tmp_path) -> None:
    assert {n for n, _ in SHADOW_VOTERS} == set(_EXPECTED_NAMES)
    loop = _make_loop(tmp_path)
    names = loop.register()
    assert names == _EXPECTED_NAMES
    loop.close()


@pytest.mark.asyncio
async def test_signal_event_records_decision_and_shadow_votes(tmp_path) -> None:
    bus = EventBus()
    loop = _make_loop(tmp_path)
    loop.register()
    loop.subscribe(bus)

    def ready() -> bool:
        tracker = OutcomeTracker(str(tmp_path / "learning.db"))
        try:
            return bool(tracker.get_all_decisions())
        finally:
            tracker.close()

    await _publish_and_drain(bus, _signal_event(), ready=ready)
    loop.close()

    tracker = OutcomeTracker(str(tmp_path / "learning.db"))
    decisions = tracker.get_all_decisions()
    tracker.close()
    assert len(decisions) == 1
    assert decisions[0].signal.direction == SignalDirection.UP
    assert decisions[0].signal.conviction == pytest.approx(0.6)
    assert decisions[0].strategy_hint["kind"] == "signal"
    assert decisions[0].strategy_hint["session_id"] == "sess-1"

    mgr = ShadowManager(db_path=str(tmp_path / "shadow.db"))
    status = {s["name"]: s for s in mgr.graduation_status()}
    mgr.close()
    assert set(status) == set(_EXPECTED_NAMES)
    assert all(s["sessions"] == 1 for s in status.values())
    assert all(s["evaluated"] == 0 for s in status.values())
    assert all(s["graduated"] is False for s in status.values())


@pytest.mark.asyncio
async def test_signal_event_ignores_unknown_direction(tmp_path) -> None:
    bus = EventBus()
    loop = _make_loop(tmp_path)
    loop.register()
    loop.subscribe(bus)
    await _publish_and_drain(bus, _signal_event(direction="SIDEWAYS"))
    loop.close()

    tracker = OutcomeTracker(str(tmp_path / "learning.db"))
    decisions = tracker.get_all_decisions()
    tracker.close()
    assert decisions == []


@pytest.mark.asyncio
async def test_evaluate_session_compares_shadows_and_stays_under_graduation_gate(
    tmp_path,
) -> None:
    bus = EventBus()
    loop = _make_loop(tmp_path)
    loop.register()
    loop.subscribe(bus)
    await loop._on_signal(_signal_event(direction="UP", conviction=0.6))
    loop.evaluate_session("sess-1", OutcomeLabel.WIN)
    loop.close()

    mgr = ShadowManager(db_path=str(tmp_path / "shadow.db"))
    status = {s["name"]: s for s in mgr.graduation_status()}
    mgr.close()
    assert set(status) == set(_EXPECTED_NAMES)
    assert all(s["evaluated"] == 1 for s in status.values())
    assert all(s["sessions"] == 1 for s in status.values())
    assert all(s["graduated"] is False for s in status.values())
    assert all(s["registered"] is False for s in status.values())


@pytest.mark.asyncio
async def test_evaluate_session_without_outcome_skips_comparison(tmp_path) -> None:
    bus = EventBus()
    loop = _make_loop(tmp_path)
    loop.register()
    loop.subscribe(bus)
    await loop._on_signal(_signal_event())
    loop.evaluate_session("sess-1", None)
    loop.close()

    mgr = ShadowManager(db_path=str(tmp_path / "shadow.db"))
    status = {s["name"]: s for s in mgr.graduation_status()}
    mgr.close()
    assert set(status) == set(_EXPECTED_NAMES)
    assert all(s["evaluated"] == 0 for s in status.values())


def test_session_outcome_label_from_fills() -> None:
    def fill(side: str, price: float, recorded_at: str) -> dict:
        return {
            "symbol": "NIFTY",
            "side": side,
            "quantity": 1,
            "price": price,
            "recorded_at": recorded_at,
        }

    assert session_outcome_label(
        [fill("BUY", 100.0, "t1"), fill("SELL", 110.0, "t2")]
    ) == OutcomeLabel.WIN
    assert session_outcome_label(
        [fill("BUY", 110.0, "t1"), fill("SELL", 100.0, "t2")]
    ) == OutcomeLabel.LOSS
    assert session_outcome_label([]) is None
    assert session_outcome_label([fill("BUY", 100.0, "t1")]) is None
    assert session_outcome_label(
        [fill("BUY", 100.0, "t1"), fill("SELL", 100.0, "t2")]
    ) is None


@pytest.mark.asyncio
async def test_signal_direction_mapping_used_for_comparison(tmp_path) -> None:
    """A DOWN signal compared against a WIN is incorrect unless votes agree."""
    bus = EventBus()
    loop = _make_loop(tmp_path)
    loop.register()
    loop.subscribe(bus)
    await loop._on_signal(_signal_event(direction="DOWN", conviction=0.5))
    loop.evaluate_session("sess-1", OutcomeLabel.WIN)
    loop.close()

    mgr = ShadowManager(db_path=str(tmp_path / "shadow.db"))
    rows = mgr.graduation_status()
    mgr.close()
    hits = sum(r["hit_rate"] * r["evaluated"] for r in rows)
    assert hits == 0, "live_direction must flow into correctness checks"
