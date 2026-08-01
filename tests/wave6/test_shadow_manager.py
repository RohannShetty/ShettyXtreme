"""Tests for ShadowManager."""
from __future__ import annotations

import sqlite3

from datetime import datetime

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.shadow_manager import (
    ShadowComparison,
    ShadowManager,
)
from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
    Vote,
)
from shettyxtreme.learning.outcome_tracker import OutcomeLabel


def _dummy_vote(features, regime, options_context) -> Vote:
    return Vote(direction=1.0, confidence=0.7, weight=1.0, name="dummy_shadow")


def _make_signal() -> Signal:
    return Signal(
        direction=SignalDirection.UP,
        conviction=0.7,
        voters=[],
        timestamp=datetime.now(),
    )


def test_run_shadow_returns_vote_and_does_not_affect_live(tmp_data_dir) -> None:
    db = str(tmp_data_dir / "shadow.db")
    mgr = ShadowManager(db_path=db)
    mgr.register_shadow("dummy_shadow", _dummy_vote)
    feats: dict[str, float] = {"x": 1.0}
    out = mgr.run_shadow(feats, Regime.TRENDING_UP, {})
    assert "dummy_shadow" in out
    assert out["dummy_shadow"].name == "dummy_shadow"
    assert out["dummy_shadow"].direction == 1.0
    # Live signal is untouched (we never pass it in)
    live = _make_signal()
    assert live.conviction == 0.7
    assert live.voters == []


def test_log_shadow_results_stores_sqlite(tmp_data_dir) -> None:
    db = str(tmp_data_dir / "shadow.db")
    mgr = ShadowManager(db_path=db)
    mgr.register_shadow("dummy_shadow", _dummy_vote)
    votes = mgr.run_shadow({}, Regime.TRENDING_UP, {})
    mgr.log_shadow_results("sig1", votes)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM shadow_sessions WHERE signal_id = ?", ("sig1",)
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["shadow_name"] == "dummy_shadow"
    assert rows[0]["vote_direction"] == 1.0
    assert rows[0]["vote_confidence"] == 0.7


def test_compare_shadow_vs_live_was_correct(tmp_data_dir) -> None:
    db = str(tmp_data_dir / "shadow.db")
    mgr = ShadowManager(db_path=db)
    mgr.register_shadow("dummy_shadow", _dummy_vote)
    votes = mgr.run_shadow({}, Regime.TRENDING_UP, {})
    mgr.log_shadow_results("sig2", votes)

    comps = mgr.compare_shadow_vs_live("sig2", OutcomeLabel.WIN, live_direction=1.0)
    assert "dummy_shadow" in comps
    c = comps["dummy_shadow"]
    assert isinstance(c, ShadowComparison)
    assert c.vote_direction == 1.0
    assert c.actual_outcome == OutcomeLabel.WIN
    assert c.was_correct is True


def test_should_promote_false_under_20_sessions(tmp_data_dir) -> None:
    db = str(tmp_data_dir / "shadow.db")
    mgr = ShadowManager(db_path=db)

    def up(features, regime, ctx) -> Vote:
        return Vote(direction=1.0, confidence=0.6, weight=1.0, name="candidate")

    mgr.register_shadow("candidate", up)
    for i in range(15):
        v = mgr.run_shadow({}, Regime.TRENDING_UP, {})
        mgr.log_shadow_results(f"s{i}", v, session_date=f"2026-01-{i+1:02d}")
        mgr.compare_shadow_vs_live(f"s{i}", OutcomeLabel.WIN, live_direction=1.0)
    assert mgr.should_promote("candidate") is False


def test_should_promote_true_over_20_with_high_hitrate(tmp_data_dir) -> None:
    db = str(tmp_data_dir / "shadow.db")
    mgr = ShadowManager(db_path=db)

    def up(features, regime, ctx) -> Vote:
        return Vote(direction=1.0, confidence=0.6, weight=1.0, name="candidate")

    mgr.register_shadow("candidate", up)
    # 25 sessions, all correct (vote up, outcome WIN, live direction up)
    for i in range(25):
        v = mgr.run_shadow({}, Regime.TRENDING_UP, {})
        mgr.log_shadow_results(f"s{i}", v, session_date=f"2026-01-{i+1:02d}")
        mgr.compare_shadow_vs_live(f"s{i}", OutcomeLabel.WIN, live_direction=1.0)
    assert mgr.should_promote("candidate") is True


class TestSessionGate:
    def test_promote_requires_twenty_distinct_sessions(self, tmp_path) -> None:
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        mgr.register_shadow("s1", lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "s1"))
        for i in range(19):  # 19 distinct sessions
            votes = mgr.run_shadow({}, None, {})
            mgr.log_shadow_results(f"sig-{i}", votes, session_date=f"2026-01-{i % 28 + 1:02d}")
        # 19 distinct dates: some dates repeat across the 19 signals
        mgr.compare_shadow_vs_live("sig-0", OutcomeLabel.WIN, live_direction=1.0)
        assert mgr.should_promote("s1") is False
        mgr.close()

    def test_promote_after_twenty_sessions_with_hit_rate(self, tmp_path) -> None:
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        mgr.register_shadow("s2", lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "s2"))
        for i in range(21):
            votes = mgr.run_shadow({}, None, {})
            mgr.log_shadow_results(f"sig-{i}", votes, session_date=f"2026-01-{i+1:02d}")
            mgr.compare_shadow_vs_live(f"sig-{i}", OutcomeLabel.WIN, live_direction=1.0)
        assert mgr.should_promote("s2") is True
        mgr.close()

    def test_low_hit_rate_blocks_promotion(self, tmp_path) -> None:
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        mgr.register_shadow("s3", lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "s3"))
        for i in range(21):
            votes = mgr.run_shadow({}, None, {})
            mgr.log_shadow_results(f"sig-{i}", votes, session_date=f"2026-01-{i+1:02d}")
            outcome = OutcomeLabel.LOSS if i % 2 == 0 else OutcomeLabel.WIN  # ~50% hit
            live_direction = 1.0 if i % 2 == 1 else -1.0
            mgr.compare_shadow_vs_live(f"sig-{i}", outcome, live_direction=live_direction)
        assert mgr.should_promote("s3") is False
        mgr.close()

    def test_direction_aware_correctness(self, tmp_path) -> None:
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        mgr.register_shadow("s4", lambda fe, rg, oc: Vote(-1.0, 0.6, 1.0, "s4"))
        votes = mgr.run_shadow({}, None, {})
        mgr.log_shadow_results("sig-x", votes, session_date="2026-01-01")
        comps = mgr.compare_shadow_vs_live("sig-x", OutcomeLabel.WIN, live_direction=1.0)
        assert comps["s4"].was_correct is False  # bearish vote, long trade won
        mgr.close()

    def test_legacy_rows_without_session_never_graduate(self, tmp_path) -> None:
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        mgr.register_shadow("s5", lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "s5"))
        for i in range(25):
            votes = mgr.run_shadow({}, None, {})
            mgr.log_shadow_results(f"sig-{i}", votes)  # no session_date
            mgr.compare_shadow_vs_live(f"sig-{i}", OutcomeLabel.WIN, live_direction=1.0)
        assert mgr.should_promote("s5") is False
        mgr.close()
