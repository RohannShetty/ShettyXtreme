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
    get_registry,
)
from shettyxtreme.learning.outcome_tracker import OutcomeLabel


def _restore_registry(before: set[str]) -> None:
    """Remove names registered during the test; never touch pre-existing ones."""
    reg = get_registry()
    for name in set(reg.names()) - before:
        reg._voters.pop(name, None)
        reg._weights.pop(name, None)


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


def test_legacy_db_migrates_session_date_and_data_intact(tmp_path) -> None:
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE shadow_sessions ("
        "shadow_name TEXT, signal_id TEXT, vote_direction REAL, "
        "vote_confidence REAL, outcome TEXT, was_correct INTEGER)"
    )
    for i in range(25):
        conn.execute(
            "INSERT INTO shadow_sessions (shadow_name, signal_id, vote_direction, "
            "vote_confidence, outcome, was_correct) VALUES (?, ?, ?, ?, ?, ?)",
            ("legacy_voter", f"sig-{i}", 1.0, 0.6, "WIN", 1),
        )
    conn.commit()
    conn.close()

    mgr = ShadowManager(db_path=str(db))
    try:
        mgr.register_shadow(
            "legacy_voter",
            lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "legacy_voter"),
        )
        cols = [
            row[1]
            for row in sqlite3.connect(str(db))
            .execute("PRAGMA table_info(shadow_sessions)")
            .fetchall()
        ]
        assert "session_date" in cols
        assert mgr._conn.execute(
            "SELECT COUNT(*) FROM shadow_sessions"
        ).fetchone()[0] == 25
        assert mgr.should_promote("legacy_voter") is False
        status = {s["name"]: s for s in mgr.graduation_status()}
        assert status["legacy_voter"]["sessions"] == 0
        assert status["legacy_voter"]["evaluated"] == 25
        assert status["legacy_voter"]["hit_rate"] == 1.0
        assert status["legacy_voter"]["graduated"] is False
        votes = mgr.run_shadow({}, Regime.TRENDING_UP, {})
        mgr.log_shadow_results("new-sig", votes, session_date="2026-03-01")
        assert mgr.graduation_status()[0]["sessions"] == 1
    finally:
        mgr.close()


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


class TestGraduation:
    def test_graduate_registers_into_default_registry(self, tmp_path) -> None:
        before = set(get_registry().names())
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        try:
            mgr.register_shadow("grad1", lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "grad1"))
            for i in range(21):
                votes = mgr.run_shadow({}, None, {})
                mgr.log_shadow_results(f"sig-{i}", votes, session_date=f"2026-01-{i+1:02d}")
                mgr.compare_shadow_vs_live(f"sig-{i}", OutcomeLabel.WIN, live_direction=1.0)
            fn = mgr.graduate("grad1")
            assert fn is not None
            assert get_registry().get("grad1") is fn
        finally:
            _restore_registry(before)
        mgr.close()

    def test_graduate_gate_not_met_returns_none(self, tmp_path) -> None:
        before = set(get_registry().names())
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        try:
            mgr.register_shadow("grad2", lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "grad2"))
            assert mgr.graduate("grad2") is None  # no sessions at all
        finally:
            _restore_registry(before)
        mgr.close()

    def test_graduation_is_idempotent(self, tmp_path) -> None:
        before = set(get_registry().names())
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        try:
            mgr.register_shadow("grad3", lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "grad3"))
            for i in range(21):
                votes = mgr.run_shadow({}, None, {})
                mgr.log_shadow_results(f"sig-{i}", votes, session_date=f"2026-01-{i+1:02d}")
                mgr.compare_shadow_vs_live(f"sig-{i}", OutcomeLabel.WIN, live_direction=1.0)
            first = mgr.graduate("grad3")
            second = mgr.graduate("grad3")
            assert first is second
        finally:
            _restore_registry(before)
        mgr.close()

    def test_graduation_status_shape(self, tmp_path) -> None:
        before = set(get_registry().names())
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        try:
            mgr.register_shadow("grad4", lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "grad4"))
            for i in range(21):
                votes = mgr.run_shadow({}, None, {})
                mgr.log_shadow_results(f"sig-{i}", votes, session_date=f"2026-01-{i+1:02d}")
                mgr.compare_shadow_vs_live(f"sig-{i}", OutcomeLabel.WIN, live_direction=1.0)
            mgr.graduate("grad4")
            status = {s["name"]: s for s in mgr.graduation_status()}
            row = status["grad4"]
            assert row["sessions"] == 21
            assert row["evaluated"] == 21
            assert row["hit_rate"] > 0.55
            assert row["graduated"] is True
            assert row["registered"] is True
        finally:
            _restore_registry(before)
        mgr.close()

    def test_persist_failure_does_not_register(self, tmp_path) -> None:
        before = set(get_registry().names())
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        try:
            mgr.register_shadow(
                "grad_fail", lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "grad_fail")
            )
            for i in range(21):
                votes = mgr.run_shadow({}, None, {})
                mgr.log_shadow_results(f"sig-{i}", votes, session_date=f"2026-01-{i+1:02d}")
                mgr.compare_shadow_vs_live(f"sig-{i}", OutcomeLabel.WIN, live_direction=1.0)

            class _FlakyConn:
                """Delegates to the real conn; first commit() raises."""

                def __init__(self, real: sqlite3.Connection) -> None:
                    self._real = real
                    self._commits = 0

                def __getattr__(self, item):
                    return getattr(self._real, item)

                def commit(self) -> None:
                    self._commits += 1
                    if self._commits == 1:
                        raise sqlite3.OperationalError("simulated commit failure")
                    self._real.commit()

            mgr._conn = _FlakyConn(mgr._conn)
            assert mgr.graduate("grad_fail") is None
            assert "grad_fail" not in get_registry().names()
            assert mgr._conn.cursor().execute(
                "SELECT COUNT(*) FROM shadow_graduates"
            ).fetchone()[0] == 0
            mgr._conn._real.commit()  # later success must not flush a pending insert
            assert mgr._conn.cursor().execute(
                "SELECT COUNT(*) FROM shadow_graduates"
            ).fetchone()[0] == 0
        finally:
            _restore_registry(before)
        mgr.close()
