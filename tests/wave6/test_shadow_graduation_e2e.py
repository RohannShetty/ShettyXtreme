"""End-to-end graduation via synthetic sessions (spec §3.2)."""
from __future__ import annotations

from shettyxtreme.intelligence.signals.signal_engine import get_registry
from shettyxtreme.learning.outcome_tracker import OutcomeLabel
from tests.wave6.session_simulator import (
    SimulatedSession, SimulatedSignal, make_shadow_manager, run_sessions,
)

_N = 21  # sessions >= MIN_SESSIONS


def _restore_registry(before: set[str]) -> None:
    """Remove names registered during the test; never touch pre-existing ones."""
    reg = get_registry()
    for name in set(reg.names()) - before:
        reg._voters.pop(name, None)
        reg._weights.pop(name, None)


def _build_sessions(sessions: int, wins: int) -> list[SimulatedSession]:
    """wins of the first `wins` sessions produce WIN outcomes; rest LOSS."""
    out = []
    for i in range(sessions):
        outcome = OutcomeLabel.WIN if i < wins else OutcomeLabel.LOSS
        sig = SimulatedSignal(
            features={"orb_high": 100.0, "orb_low": 90.0, "ltp": 95.0 + i},
            regime=None, options_context={}, live_direction=1.0, outcome=outcome,
        )
        out.append(SimulatedSession(date=f"2026-01-{i+1:02d}", signals=[sig]))
    return out


def test_good_voter_graduates_after_21_sessions(tmp_path) -> None:
    before = set(get_registry().names())
    mgr = make_shadow_manager(str(tmp_path / "s.db"))
    try:
        run_sessions(mgr, _build_sessions(_N, wins=_N))  # 100% agreement
        assert mgr.should_promote("good_voter") is True
        assert mgr.graduate("good_voter") is not None
        assert get_registry().get("good_voter") is not None
        assert mgr.graduation_status()[0]["graduated"] is True
    finally:
        _restore_registry(before)
    mgr.close()


def test_poor_voter_never_graduates(tmp_path) -> None:
    before = set(get_registry().names())
    mgr = make_shadow_manager(str(tmp_path / "s.db"))
    try:
        run_sessions(mgr, _build_sessions(_N, wins=_N))
        assert mgr.should_promote("poor_voter") is False  # always votes against
        assert mgr.graduate("poor_voter") is None
    finally:
        _restore_registry(before)
    mgr.close()


def test_19_sessions_insufficient(tmp_path) -> None:
    before = set(get_registry().names())
    mgr = make_shadow_manager(str(tmp_path / "s.db"))
    try:
        run_sessions(mgr, _build_sessions(19, wins=19))
        assert mgr.should_promote("good_voter") is False
        assert mgr.graduate("good_voter") is None
    finally:
        _restore_registry(before)
    mgr.close()
