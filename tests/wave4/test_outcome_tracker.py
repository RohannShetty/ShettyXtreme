"""Tests for the outcome tracker."""
from __future__ import annotations

import os
from datetime import date, datetime

import pytest

from shettyxtreme.core.data_models.orders import Order
from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
)
from shettyxtreme.learning.outcome_tracker import (
    OutcomeLabel,
    OutcomeTracker,
    SignalDecision,
)


def _make_signal(conviction: float = 0.7) -> Signal:
    return Signal(
        direction=SignalDirection.UP,
        conviction=conviction,
        D=0.5,
        P=1.0,
        G=0.1,
        voters=[],
        timestamp=datetime.now(),
    )


def test_record_signal_decision_persists(tmp_data_dir: str) -> None:
    db = os.path.join(tmp_data_dir, "ot.db")
    tracker = OutcomeTracker(db)
    sig = _make_signal()
    decision_id = tracker.record_signal_decision(sig, {"regime": Regime.TRENDING_UP})
    tracker.close()

    tracker2 = OutcomeTracker(db)
    d = tracker2.get_decision(decision_id)
    tracker2.close()
    assert d is not None
    assert d.id == decision_id
    assert d.signal.direction == SignalDirection.UP
    assert d.signal.conviction == pytest.approx(0.7)
    assert d.outcome is None
    assert d.strategy_hint == {"regime": "trending_up"}


def test_record_execution_attempt_links(tmp_data_dir: str) -> None:
    db = os.path.join(tmp_data_dir, "ot.db")
    tracker = OutcomeTracker(db)
    decision_id = tracker.record_signal_decision(_make_signal())
    order = Order(
        order_id="o1",
        symbol="NIFTY",
        exchange="NSE",
        side="BUY",
        order_type="MARKET",
        quantity=75,
        price=100.0,
        status="FILLED",
    )
    attempt_id = tracker.record_execution_attempt(decision_id, order)
    tracker.close()

    tracker2 = OutcomeTracker(db)
    d = tracker2.get_decision(decision_id)
    tracker2.close()
    assert attempt_id
    assert d is not None
    assert len(d.execution_attempts) == 1
    assert d.execution_attempts[0]["order_id"] == "o1"


def test_record_outcome_links(tmp_data_dir: str) -> None:
    db = os.path.join(tmp_data_dir, "ot.db")
    tracker = OutcomeTracker(db)
    decision_id = tracker.record_signal_decision(_make_signal())
    tracker.record_outcome(decision_id, OutcomeLabel.WIN)
    tracker.close()

    tracker2 = OutcomeTracker(db)
    d = tracker2.get_decision(decision_id)
    tracker2.close()
    assert d is not None
    assert d.outcome == OutcomeLabel.WIN


def test_outcome_immutability(tmp_data_dir: str) -> None:
    db = os.path.join(tmp_data_dir, "ot.db")
    tracker = OutcomeTracker(db)
    decision_id = tracker.record_signal_decision(_make_signal())
    tracker.record_outcome(decision_id, OutcomeLabel.WIN)
    with pytest.raises(ValueError):
        tracker.record_outcome(decision_id, OutcomeLabel.LOSS)
    tracker.close()


def test_get_decisions_by_date(tmp_data_dir: str) -> None:
    db = os.path.join(tmp_data_dir, "ot.db")
    tracker = OutcomeTracker(db)
    ts = datetime(2026, 3, 15, 10, 30, 0)
    sig = _make_signal()
    sig.timestamp = ts
    decision_id = tracker.record_signal_decision(sig)
    other = tracker.record_signal_decision(_make_signal())
    tracker.close()

    tracker2 = OutcomeTracker(db)
    same_day = tracker2.get_decisions_by_date(date(2026, 3, 15))
    tracker2.close()
    ids = {d.id for d in same_day}
    assert decision_id in ids
    assert other not in ids
    assert len(same_day) == 1
