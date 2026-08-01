# Phase 3A — Advanced Intelligence Implementation Plan

> **STATUS: EXECUTED 2026-08-01 — COMPLETE.** All 8 tasks + final-review fix wave landed on branch `phase3a-advanced-intelligence` @ 65e735d; suite 563 passed / 0 failed / 3 skipped; final whole-branch review verdict: READY TO MERGE (YES). Execution ledger: `.superpowers/sdd/progress.md`. **Correctness-semantics decision (user):** the approved SPEC governs — a shadow vote is correct iff sign(vote) == sign(live direction) AND outcome WIN (Task-1 step 5 in this plan described direction-agreement-only; superseded by user decision on 2026-08-01, matching spec §3.1.4).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Graduate the intelligence layer from display to validated edge — session-aware shadow-voter graduation (≥20 sessions), calibration consumed by sizing, correlation block caps + conviction D/P/G wired into the live signal path, walkforward depth, learning status endpoints — plus the Phase-2 review follow-ups.

**Architecture:** Surgical extension of the existing, tested learning machinery (`ShadowManager`, `VoterCorrelation`, `CalibrationCurve`, `OutcomeTracker`, `ConvictionEngine`, `WalkforwardEvaluator`). No new dependencies, no LLM surface (D3). Synthetic-session validation proves the graduation path now; real graduation happens automatically once ≥20 real OBSERVER sessions accumulate.

**Tech Stack:** Python 3.11, stdlib + existing modules (sqlite3, dataclasses), pytest + pytest-asyncio, FastAPI.

## Global Constraints

- **D3:** no LLM/agent surface in this phase — all deterministic/statistical.
- **No-import rule (D1):** zero `import openalgo` / `from openalgo` in `src/`.
- **Zero new runtime dependencies** (stdlib + existing packages; test helpers may use pytest only).
- **≤500 lines per file** (new/modified).
- **Suite gate:** 527 passed / 0 failed → never shrinks; run with `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-phase3a -p no:cacheprovider` (never bare `pytest`).
- **Dirty file:** `docs/superpowers/plans/2026-07-31-graphify-upgrade.md` is pre-existing unstaged — never stage or commit it.
- **Backward compatibility:** `Signal` dataclass gains fields with defaults (positional constructions keep working); `log_shadow_results` gains an OPTIONAL `session_date` (default None — legacy rows can never falsely graduate); DB migrations are guarded ALTER TABLE.
- **No secrets:** never read/print credential files or `.env`; no client IDs/tokens in code or output.
- Shell is Windows PowerShell 5.1; git CRLF warnings cosmetic; graphify hook rebuilds per commit (background).

---

## Step 0: Branch

- [ ] `git checkout master` → `git branch phase3a-advanced-intelligence` → `git checkout phase3a-advanced-intelligence`
- [ ] Verify `git log --oneline -1` = 6ff0a77 (spec commit) on the new branch.

---

## Task 1: Session-aware shadow gate (shadow_sessions + direction-aware correctness)

**Files:**
- Modify: `src/shettyxtreme/intelligence/signals/shadow_manager.py`
- Modify: `tests/wave6/test_shadow_manager.py`

**Interfaces:**
- Consumes: existing `ShadowManager` (register_shadow/run_shadow/log_shadow_results/compare_shadow_vs_live/should_promote), `OutcomeLabel`, `Vote`.
- Produces:
  - `MIN_SESSIONS: int = 20`, `PROMOTION_HIT_RATE: float = 0.55` module constants.
  - `shadow_sessions` table gains `session_date TEXT` (guarded migration).
  - `log_shadow_results(signal_id, shadow_votes, session_date: str | None = None)` — inserts session_date.
  - `compare_shadow_vs_live(signal_id, live_outcome, live_direction: float = 1.0) -> dict[str, ShadowComparison]` — direction-aware correctness.
  - `should_promote(name) -> bool` — distinct session_date count ≥ MIN_SESSIONS AND hit rate > PROMOTION_HIT_RATE.

- [ ] **Step 1: Write the failing tests** (update existing + append to `tests/wave6/test_shadow_manager.py`):

```python
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
            mgr.compare_shadow_vs_live(f"sig-{i}", outcome, live_direction=1.0)
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
```

- [ ] **Step 2: Run to verify they fail** — `& .\.venv\Scripts\python.exe -m pytest tests/wave6/test_shadow_manager.py -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-phase3a -p no:cacheprovider` — expected RED on the new session-gate semantics (rows-count vs sessions, direction-agnostic correctness).

- [ ] **Step 3: Implement** (`shadow_manager.py`):
  1. Module constants `MIN_SESSIONS = 20`, `PROMOTION_HIT_RATE = 0.55`.
  2. `_init_schema`: add `session_date TEXT` to the CREATE TABLE; then a guarded migration — `cur.execute("PRAGMA table_info(shadow_sessions)")`; if no `session_date` column, `ALTER TABLE shadow_sessions ADD COLUMN session_date TEXT`.
  3. `log_shadow_results(self, signal_id, shadow_votes, session_date: str | None = None)` — include session_date in the INSERT.
  4. `compare_shadow_vs_live(self, signal_id, live_outcome, live_direction: float = 1.0)` — `was_correct = self._is_correct(direction, live_direction)`.
  5. `_is_correct(vote_direction: float, live_direction: float) -> bool` (replace the outcome-based static) — `vote_direction != 0.0 and sign(vote_direction) == sign(live_direction) and live_direction != 0.0`. (Outcome WIN/LOSS is still recorded; correctness now measures agreement with the trade direction. Neutral live direction → never correct.)
  6. `should_promote(name)`: `SELECT COUNT(DISTINCT session_date) FROM shadow_sessions WHERE shadow_name = ? AND session_date IS NOT NULL` → sessions; `sessions < MIN_SESSIONS` → False; evaluated rows (`was_correct IS NOT NULL`) → hit rate; `<= PROMOTION_HIT_RATE` → False; else True.
  7. Update any existing wave6 tests that relied on the old `_is_correct(outcome)` semantics (they now pass `live_direction`).

- [ ] **Step 4: Run the file** — all pass, pristine.
- [ ] **Step 5: Commit** — `feat: session-aware shadow gate (>=20 sessions) + direction-aware correctness`.

---

## Task 2: Shadow graduation + status

**Files:**
- Modify: `src/shettyxtreme/intelligence/signals/shadow_manager.py`
- Modify: `tests/wave6/test_shadow_manager.py`

**Interfaces:**
- Consumes: Task 1 gate, `get_registry()` from `signal_engine.py`.
- Produces:
  - `graduate(name: str) -> ShadowFn | None` — registers the shadow into the default `VoterRegistry` (weight 1.0), persists to a new `shadow_graduates` table (shadow_name PRIMARY KEY, graduated_at), idempotent, returns None when the gate is not met.
  - `graduation_status() -> list[dict]` — per shadow: `{name, sessions, evaluated, hit_rate, graduated, registered}` (registered = name in default registry).

- [ ] **Step 1: Write the failing tests** (append):

```python
class TestGraduation:
    def test_graduate_registers_into_default_registry(self, tmp_path) -> None:
        from shettyxtreme.intelligence.signals.signal_engine import get_registry
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        mgr.register_shadow("grad1", lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "grad1"))
        for i in range(21):
            votes = mgr.run_shadow({}, None, {})
            mgr.log_shadow_results(f"sig-{i}", votes, session_date=f"2026-01-{i+1:02d}")
            mgr.compare_shadow_vs_live(f"sig-{i}", OutcomeLabel.WIN, live_direction=1.0)
        fn = mgr.graduate("grad1")
        assert fn is not None
        assert get_registry().get("grad1") is fn
        mgr.close()

    def test_graduate_gate_not_met_returns_none(self, tmp_path) -> None:
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        mgr.register_shadow("grad2", lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "grad2"))
        assert mgr.graduate("grad2") is None  # no sessions at all
        mgr.close()

    def test_graduation_is_idempotent(self, tmp_path) -> None:
        from shettyxtreme.intelligence.signals.signal_engine import get_registry
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
        mgr.register_shadow("grad3", lambda fe, rg, oc: Vote(1.0, 0.6, 1.0, "grad3"))
        for i in range(21):
            votes = mgr.run_shadow({}, None, {})
            mgr.log_shadow_results(f"sig-{i}", votes, session_date=f"2026-01-{i+1:02d}")
            mgr.compare_shadow_vs_live(f"sig-{i}", OutcomeLabel.WIN, live_direction=1.0)
        first = mgr.graduate("grad3")
        second = mgr.graduate("grad3")
        assert first is second
        mgr.close()

    def test_graduation_status_shape(self, tmp_path) -> None:
        mgr = ShadowManager(db_path=str(tmp_path / "s.db"))
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
        mgr.close()
```

- [ ] **Step 2: Run to verify they fail** — `graduate`/`graduation_status` don't exist yet.
- [ ] **Step 3: Implement** (`shadow_manager.py`):
  1. `_init_schema`: add `CREATE TABLE IF NOT EXISTS shadow_graduates (shadow_name TEXT PRIMARY KEY, graduated_at TEXT)`.
  2. `graduate(self, name)`: `if not self.should_promote(name): return None`; `fn = self._shadows.get(name); if fn is None: return None`; `get_registry().register(name, fn, weight=1.0)`; `INSERT OR REPLACE INTO shadow_graduates ...`; return fn. Import `get_registry` at module top from `shettyxtreme.intelligence.signals.signal_engine` (no circular import — signal_engine does not import shadow_manager).
  3. `graduation_status(self)`: query per shadow: distinct sessions, evaluated count, hits, hit_rate, graduated (row in shadow_graduates), registered (`name in get_registry().names()`).
- [ ] **Step 4: Run the file** — all pass, pristine.
- [ ] **Step 5: Commit** — `feat: shadow voter graduation into live registry + graduation status`.

---

## Task 3: Synthetic session simulator + end-to-end graduation tests

**Files:**
- Create: `tests/wave6/session_simulator.py` (test helper — NOT a pytest file; no `test_` prefix on the module)
- Create: `tests/wave6/test_shadow_graduation_e2e.py`

**Interfaces:**
- Consumes: Tasks 1-2 (`ShadowManager`), `Vote`, `OutcomeLabel`.
- Produces (used by Task 7 too):
  - `SimulatedSignal(features: dict, regime: object, options_context: dict, live_direction: float, outcome: OutcomeLabel)`
  - `SimulatedSession(date: str, signals: list[SimulatedSignal])`
  - `make_shadow_manager(db_path) -> ShadowManager` with 2 registered shadows: `good_voter` (agrees with live_direction ≥60%) and `poor_voter` (agrees <45%).
  - `run_sessions(manager: ShadowManager, sessions: list[SimulatedSession]) -> None` — runs/logs/compares every signal.

- [ ] **Step 1: Write the helper + tests:**

```python
# tests/wave6/session_simulator.py
"""Deterministic synthetic-session simulator for shadow-voter testing.

Test-only. Scripted vote/outcome patterns; no randomness.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from shettyxtreme.intelligence.signals.signal_engine import Vote
from shettyxtreme.intelligence.signals.shadow_manager import ShadowManager
from shettyxtreme.learning.outcome_tracker import OutcomeLabel


@dataclass
class SimulatedSignal:
    features: dict[str, float]
    regime: Any
    options_context: dict[str, Any]
    live_direction: float
    outcome: OutcomeLabel


@dataclass
class SimulatedSession:
    date: str
    signals: list[SimulatedSignal] = field(default_factory=list)


def make_shadow_manager(db_path: str) -> ShadowManager:
    mgr = ShadowManager(db_path=db_path)
    mgr.register_shadow("good_voter", _good_vote)
    mgr.register_shadow("poor_voter", _poor_vote)
    return mgr


def _good_vote(features: dict[str, float], regime: Any, options_context: dict) -> Vote:
    return Vote(direction=float(features.get("_live_direction", 0.0)), confidence=0.7, weight=1.0, name="good_voter")


def _poor_vote(features: dict[str, float], regime: Any, options_context: dict) -> Vote:
    return Vote(direction=-float(features.get("_live_direction", 0.0)), confidence=0.7, weight=1.0, name="poor_voter")


def run_sessions(manager: ShadowManager, sessions: list[SimulatedSession]) -> None:
    sig_idx = 0
    for session in sessions:
        for sig in session.signals:
            features = dict(sig.features)
            features["_live_direction"] = sig.live_direction
            votes = manager.run_shadow(features, sig.regime, sig.options_context)
            sid = f"sig-{sig_idx}"
            manager.log_shadow_results(sid, votes, session_date=session.date)
            manager.compare_shadow_vs_live(sid, sig.outcome, live_direction=sig.live_direction)
            sig_idx += 1
```

```python
# tests/wave6/test_shadow_graduation_e2e.py
"""End-to-end graduation via synthetic sessions (spec §3.2)."""
from __future__ import annotations

from shettyxtreme.intelligence.signals.signal_engine import get_registry
from shettyxtreme.learning.outcome_tracker import OutcomeLabel
from tests.wave6.session_simulator import (
    SimulatedSession, SimulatedSignal, make_shadow_manager, run_sessions,
)

_N = 21  # sessions >= MIN_SESSIONS


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
    mgr = make_shadow_manager(str(tmp_path / "s.db"))
    run_sessions(mgr, _build_sessions(_N, wins=_N))  # 100% agreement
    assert mgr.should_promote("good_voter") is True
    assert mgr.graduate("good_voter") is not None
    assert get_registry().get("good_voter") is not None
    assert mgr.graduation_status()[0]["graduated"] is True
    mgr.close()


def test_poor_voter_never_graduates(tmp_path) -> None:
    mgr = make_shadow_manager(str(tmp_path / "s.db"))
    run_sessions(mgr, _build_sessions(_N, wins=_N))
    assert mgr.should_promote("poor_voter") is False  # always votes against
    assert mgr.graduate("poor_voter") is None
    mgr.close()


def test_19_sessions_insufficient(tmp_path) -> None:
    mgr = make_shadow_manager(str(tmp_path / "s.db"))
    run_sessions(mgr, _build_sessions(19, wins=19))
    assert mgr.should_promote("good_voter") is False
    assert mgr.graduate("good_voter") is None
    mgr.close()
```

- [ ] **Step 2: Run to verify they fail** — the simulator's `_good_vote`/`_poor_vote` semantics are exercised against Tasks 1-2 behavior; first run proves the negative paths (19 sessions, poor voter).
- [ ] **Step 3: Fix** — should pass with Tasks 1-2 implemented; adjust only if a test exposes a real gap (report DONE_WITH_CONCERNS if you had to change production code).
- [ ] **Step 4: Run** `tests/wave6/` — all pass, pristine.
- [ ] **Step 5: Commit** — `test: synthetic session simulator + end-to-end shadow graduation`.

---

## Task 4: Calibration → sizing

**Files:**
- Create: `src/shettyxtreme/learning/sizing.py`
- Modify: `src/shettyxtreme/intelligence/hints/strategy_hints.py`
- Create: `tests/wave6/test_sizing.py`
- Modify: `tests/wave2/test_strategy_hints.py`

**Interfaces:**
- Consumes: `CalibrationCurve` (fit/predict/is_reliable/get_curve).
- Produces:
  - `CalibratedSizing(curve: CalibrationCurve, base_rate: float = 0.5, min_multiplier: float = 0.25, max_multiplier: float = 2.0)` with `active: bool` property (set by caller via `set_active(bool)` — sizing never touches the DB) and `adjust(base_quantity: int, conviction: float) -> int` (clamped multiplier; `ValueError` on `base_quantity <= 0`; conviction clamped to [0,1]).
  - `StrategyHint.quantity: int | None = None`; `StrategyHints.__init__` gains `sizing: CalibratedSizing | None = None` and `base_quantity: int = 75`; when `sizing` is set AND active AND direction is not neutral, `generate()` sets `hint.quantity = sizing.adjust(base_quantity, conviction)`.

- [ ] **Step 1: Write the failing tests:**

`tests/wave6/test_sizing.py`:
```python
"""Tests for calibrated position sizing (spec §3.3)."""
from __future__ import annotations
import pytest
from shettyxtreme.learning.calibration import CalibrationCurve
from shettyxtreme.learning.sizing import CalibratedSizing


class TestCalibratedSizing:
    def test_adjust_uses_calibrated_win_rate(self) -> None:
        curve = CalibrationCurve()
        # 100% win decisions at high conviction -> predict returns 1.0 in that bin
        curve.fit([_decision(0.8) for _ in range(40)])  # helper below
        sizing = CalibratedSizing(curve, base_rate=0.5)
        sizing.set_active(True)
        assert sizing.adjust(100, 0.8) == pytest.approx(200, rel=0.05)  # 1.0/0.5 * 100

    def test_clamps_to_max_multiplier(self) -> None:
        curve = CalibrationCurve()
        curve.fit([_decision(0.9) for _ in range(40)])
        sizing = CalibratedSizing(curve, base_rate=0.1, max_multiplier=2.0)
        sizing.set_active(True)
        assert sizing.adjust(100, 0.9) <= 200

    def test_clamps_to_min_multiplier(self) -> None:
        curve = CalibrationCurve()
        curve.fit([_decision(0.1) for _ in range(40)])
        sizing = CalibratedSizing(curve, base_rate=0.9, min_multiplier=0.25)
        sizing.set_active(True)
        assert sizing.adjust(100, 0.1) >= 25

    def test_inactive_returns_base(self) -> None:
        curve = CalibrationCurve()
        sizing = CalibratedSizing(curve)
        assert sizing.adjust(75, 0.8) == 75

    def test_positive_quantity_required(self) -> None:
        sizing = CalibratedSizing(CalibrationCurve())
        with pytest.raises(ValueError):
            sizing.adjust(0, 0.8)


def _decision(conviction: float):
    from datetime import UTC, datetime
    from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection, Vote
    from shettyxtreme.learning.outcome_tracker import OutcomeLabel, SignalDecision
    sig = Signal(direction=SignalDirection.UP, conviction=conviction,
                 voters=[Vote(1.0, conviction, 1.0, "v")], timestamp=datetime.now(UTC))
    return SignalDecision(id="x", signal=sig, timestamp=datetime.now(UTC), outcome=OutcomeLabel.WIN)
```

Modify `tests/wave2/test_strategy_hints.py` — append:
```python
def test_sizing_hook_sets_quantity(self) -> None:
    from shettyxtreme.learning.calibration import CalibrationCurve
    from shettyxtreme.learning.sizing import CalibratedSizing
    curve = CalibrationCurve()
    curve.fit([_cal_decision(0.8) for _ in range(40)])
    sizing = CalibratedSizing(curve, base_rate=0.5)
    sizing.set_active(True)
    hint = StrategyHints(signal=BULLISH_SIGNAL, chain=None, current_price=24000.0,
                         sizing=sizing, base_quantity=100).generate()
    assert hint.quantity == pytest.approx(200, rel=0.05)

def test_no_sizing_no_quantity(self) -> None:
    hint = StrategyHints(signal=BULLISH_SIGNAL).generate()
    assert hint.quantity is None
```
(The `_cal_decision` helper mirrors `_decision` — define it locally in the test file to avoid cross-test imports; note the hint with `current_price` and no chain still hits the neutral direction? No — BULLISH_SIGNAL is UP with conviction 0.7 → bullish; sizing hook applies. But with `chain=None`, `_select_strike` returns None → the no-strike hint path — quantity must still be set there. Implement accordingly: set quantity on BOTH hint return paths (with and without strike).)

- [ ] **Step 2: Run to verify they fail** — `sizing.py` missing; `StrategyHint.quantity` missing.
- [ ] **Step 3: Implement** (`sizing.py` + `strategy_hints.py`):
  1. `sizing.py` per Interfaces: `set_active(bool)`, `adjust` computes `p = self._curve.predict(conviction)`, `mult = p / base_rate` clamped, `max(1, round(base_quantity * mult))`.
  2. `strategy_hints.py`: `StrategyHint.quantity: int | None = None`; `__init__` params `sizing`/`base_quantity`; in `generate()`, after computing `conviction` (and only for non-neutral directions), `if self._sizing is not None and self._sizing.active and hint_dir != "neutral": qty = self._sizing.adjust(self._base_quantity, conviction)` — set `quantity=qty` on BOTH return objects (with-strike and no-strike paths).
- [ ] **Step 4: Run** `tests/wave6/test_sizing.py tests/wave2/test_strategy_hints.py` — all pass.
- [ ] **Step 5: Commit** — `feat: calibrated position sizing (CalibratedSizing) + hint quantity`.

---

## Task 5: Signal path wiring — correlation block caps + conviction D/P/G

**Files:**
- Modify: `src/shettyxtreme/intelligence/signals/signal_engine.py`
- Modify: `src/shettyxtreme/intelligence/signals/voter_correlation.py` (only if a small helper is needed — prefer no changes)
- Modify: `tests/wave2/test_signal_engine.py`
- Modify: `tests/terminal/test_projections.py` (SIGNAL_V2 with D/P/G)

**Interfaces:**
- Consumes: `VoterCorrelation`, `ConvictionEngine`.
- Produces:
  - `Signal` gains `D: float = 0.0`, `P: float = 1.0`, `G: str = "contested"` (append-only defaults).
  - `SignalEngine.__init__(feature_engine, correlation: VoterCorrelation | None = None, history_window: int = 50, **kwargs)`.
  - `compute_signal` order: raw votes → (correlation: rolling history, matrix at ≥5 signals, groups threshold 0.7, caps map, `apply_block_caps`) → weights → conviction via `ConvictionEngine.compute([asdict(v) for v in votes], eligible=len(self.voters))` → attach `signal.D/P/G`.

- [ ] **Step 1: Write the failing tests** (append to `tests/wave2/test_signal_engine.py`):

```python
class TestSignalPathWiring:
    def setup_method(self) -> None:
        mock_fe = MagicMock()
        mock_fe.features = {}
        self.engine = SignalEngine(feature_engine=mock_fe)

    def test_correlation_block_caps_scale_group_weights(self) -> None:
        from shettyxtreme.intelligence.signals.voter_correlation import VoterCorrelation
        engine = SignalEngine(feature_engine=MagicMock(features={}),
                              correlation=VoterCorrelation(block_cap=1.0))
        def v1(fe): return Vote(1.0, 0.8, 1.0, "v1")
        def v2(fe): return Vote(1.0, 0.8, 1.0, "v2")
        def v3(fe): return Vote(-1.0, 0.8, 1.0, "v3")
        engine.register_voter("v1", v1)
        engine.register_voter("v2", v2)
        engine.register_voter("v3", v3)
        for _ in range(6):  # build history so matrix is computed
            engine.compute_signal()
        sig = engine.compute_signal()
        # v1+v2 always agree -> correlated group capped at 1.0 total weight
        assert sig.conviction < 0.8  # capped group cannot dominate
        assert sig.P == pytest.approx(1.0)

    def test_signal_carries_dpg(self) -> None:
        self.engine.register_voter("u", lambda fe: Vote(1.0, 0.8, 1.0, "u"))
        sig = self.engine.compute_signal()
        assert sig.D > 0
        assert sig.P == pytest.approx(1.0)
        assert sig.G in ("unanimous", "contested")

    def test_dpg_defaults_when_no_voters(self) -> None:
        sig = self.engine.compute_signal()
        assert sig.D == 0.0 and sig.P == 1.0 and sig.G == "contested"
```

Append to `tests/terminal/test_projections.py` (follow the file's existing patterns):
```python
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
```

- [ ] **Step 2: Run to verify they fail** — D/P/G not on Signal; correlation param missing.
- [ ] **Step 3: Implement** (`signal_engine.py`):
  1. `Signal` fields D/P/G (defaults, appended last).
  2. `SignalEngine.__init__` gains `correlation` + `history_window`; store `self._vote_history: list[list[Vote]] = []`.
  3. In `compute_signal`, after building `votes`: if `self._correlation is not None`: append `list(votes)` to history (trim to last `history_window`); if `len(history) >= 5`: `matrix = self._correlation.compute_correlation_matrix(self._vote_history)`; groups = `get_correlation_groups(0.7)`; `caps = {name: self._correlation.get_block_cap(g) for g in groups for name in g}`; `votes = self._correlation.apply_block_caps(votes, caps)`.
  4. After weighting: `from dataclasses import asdict; result = ConvictionEngine().compute([asdict(v) for v in votes], eligible=len(self.voters))`; attach `D=result.D, P=result.P, G=result.G` on the returned Signal (both the zero-weight early return and the normal return; zero-weight early return keeps defaults).
  5. Keep `compute_signal_from_votes = compute_signal`.
- [ ] **Step 4: Run** `tests/wave2/test_signal_engine.py tests/terminal/test_projections.py tests/wave2/test_conviction_engine.py tests/wave6/test_voter_correlation.py` — all pass (existing tests must be untouched-green).
- [ ] **Step 5: Commit** — `feat: wire correlation block caps + conviction D/P/G into signal path`.

---

## Task 6: Walkforward depth — per-voter + per-regime breakdowns

**Files:**
- Modify: `src/shettyxtreme/learning/walkforward.py`
- Modify: `tests/wave4/test_walkforward.py`

**Interfaces:**
- Consumes: existing `WalkforwardEvaluator.evaluate(signals, entry_prices, exit_prices) -> WalkforwardResult` (already premium-based, TP/SL/EOD exits, cost-netted).
- Produces: `WalkforwardResult` gains `per_voter: dict[str, dict]` and `per_regime: dict[str, dict]` (defaults `field(default_factory=dict)`); `evaluate` gains optional `regimes: dict[str, str] | None = None` (decision_id → regime label); per-voter: `{signals, correct, directional_hit_rate}` computed from `decision.signal.voters` vs the realized direction; per-regime: `{signals, wins, win_rate}` grouped by the regime label (skipped entirely when `regimes` is None or a decision has no label).

- [ ] **Step 1: Write the failing tests** (append to `tests/wave4/test_walkforward.py`, following its fixture pattern):
```python
def test_breakdowns_present(report) -> None:
    assert "per_voter" in report.__dict__
    assert "per_regime" in report.__dict__
```
(Adapt to the file's existing fixture; also add a per-regime assertion when `regimes` is passed — one decision labeled "trending" with a WIN must appear as `per_regime["trending"]["wins"] == 1`.)
- [ ] **Step 2: Run to verify they fail** — fields missing.
- [ ] **Step 3: Implement** (`walkforward.py`): extend `WalkforwardResult`; in `evaluate`, inside the decision loop, accumulate per-voter stats (voter vote sign vs realized `direction` → correct), and per-regime stats when `regimes` provides a label. Guard division by zero (0 signals → 0.0 hit/win rate).
- [ ] **Step 4: Run** `tests/wave4/test_walkforward.py` — all pass.
- [ ] **Step 5: Commit** — `feat: walkforward per-voter + per-regime breakdowns`.

---

## Task 7: Learning status endpoints

**Files:**
- Create: `src/shettyxtreme/terminal/api/learning_router.py`
- Modify: `src/shettyxtreme/terminal/api/models.py` (response models)
- Modify: `src/shettyxtreme/terminal/api/app.py` (include router)
- Create: `tests/wave3/test_learning_api.py`

**Interfaces:**
- Consumes: `CalibrationCurve`, `OutcomeTracker` (decisions source), `ShadowManager.graduation_status()`.
- Produces:
  - `GET /api/learning/calibration` → `CalibrationResponse{reliable: bool, points: list[CalibrationPointResponse{conviction_bin: [float,float], actual_win_rate: float, sample_size: int, confidence_interval: [float,float]}]}`.
  - `GET /api/learning/shadows` → `ShadowStatusResponse{shadows: list[ShadowStatusItem{name, sessions, evaluated, hit_rate, graduated, registered}]}`.
  - Module constants `LEARNING_DB_PATH` / `SHADOW_DB_PATH` (default `data/learning.db` / `data/shadow.db`); DB missing/unreadable → 200 with empty/neutral payload, never 500.

- [ ] **Step 1: Write the failing tests** (`tests/wave3/test_learning_api.py`, following `test_api.py`'s `client` fixture):
```python
@pytest.mark.asyncio
async def test_calibration_empty_without_db(client: AsyncClient) -> None:
    import shettyxtreme.terminal.api.learning_router as lr
    lr.LEARNING_DB_PATH = "C:/nonexistent/learning.db"
    resp = await client.get("/api/learning/calibration")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reliable"] is False
    assert data["points"] == []

@pytest.mark.asyncio
async def test_shadows_empty_without_db(client: AsyncClient) -> None:
    import shettyxtreme.terminal.api.learning_router as lr
    lr.SHADOW_DB_PATH = "C:/nonexistent/shadow.db"
    resp = await client.get("/api/learning/shadows")
    assert resp.status_code == 200
    assert resp.json()["shadows"] == []

@pytest.mark.asyncio
async def test_calibration_with_populated_db(client: AsyncClient, tmp_path) -> None:
    import shettyxtreme.terminal.api.learning_router as lr
    db = tmp_path / "learning.db"
    tracker = OutcomeTracker(str(db))
    from tests.wave6.session_simulator import _build_decision  # reuse or inline helper
    for _ in range(40):
        tracker.record_signal_decision(_build_decision(0.8), {})
        # record_outcome needs the decision id; adapt helper to return ids
    tracker.close()
    lr.LEARNING_DB_PATH = str(db)
    resp = await client.get("/api/learning/calibration")
    assert resp.status_code == 200
    assert resp.json()["reliable"] is True
    assert len(resp.json()["points"]) > 0
```
(Design the DB-reading helper in the router as a module-level function `_fit_calibration(db_path) -> CalibrationCurve` and `_shadow_status(db_path) -> list[dict]` so tests can monkeypatch the constants; the populated-DB test may use a small inline fixture instead of the simulator if the simulator's helper doesn't fit — keep the test honest: decisions WITH outcomes must be recorded for a reliable curve.)
- [ ] **Step 2: Run to verify they fail** — router/models missing.
- [ ] **Step 3: Implement**: models (3 classes above), `learning_router.py` (two GET handlers + `_fit_calibration`/`_shadow_status` helpers with try/except → empty), register in `app.py`.
- [ ] **Step 4: Run** `tests/wave3/test_learning_api.py tests/wave3/test_api.py tests/terminal/` — all pass.
- [ ] **Step 5: Commit** — `feat: learning status endpoints (calibration + shadow graduation)`.

---

## Task 8: Phase-2 deferred minors

**Files:**
- Modify: `src/shettyxtreme/intelligence/hints/strategy_hints.py` (strike_price/drv_option_type aliases in `_select_strike`)
- Modify: `tests/terminal/test_integration.py` or `tests/wave3/test_api.py` (endpoint-level 503 test)
- Modify: `src/shettyxtreme/terminal/api/intelligence_router.py` (remove dead `_fetch_chain` wrapper)
- Modify: `tests/terminal/test_projections.py` (on_regime_changed dataclass-path test)

**Interfaces:** none new.

- [ ] **Step 1: Tests first:**
  1. `_select_strike` alias test: a chain row `{"strike_price": 24000, "drv_option_type": "CE", "premium": 150.0, "iv": 15.0}` with `current_price=24000, slippage=0, brokerage=0` yields `strike == 24000.0` (same as the Phase-2 `test_bullish_selects_positive_ev_strike` but with aliased keys).
  2. 503 test: with `app.state.data_adapter` returning `{"status": "error", "entitlement": True, "message": "subscribe to Data APIs — Dhan error 806"}`, `GET /api/intelligence/options?symbol=NIFTY` → 503 with the entitlement detail; `GET /api/intelligence/strategy-hint` → 503.
  3. `on_regime_changed` dataclass-path test mirroring the `on_signal_v2` one (a dataclass payload with regime/confidence attributes updates the projection).
  4. Dead-wrapper removal: no test — verified by grep (no references) + suite.
- [ ] **Step 2: Run to verify they fail** — aliases not normalized (strike 0.0 → EV path misses), no 503 handler, dataclass regime test fails.
- [ ] **Step 3: Implement:** alias normalization (a small local `_row_value(row, *keys)` helper or inline; prefer extracting a shared helper in `intelligence_router.py` if clean, else duplicate 4 lines in `strategy_hints.py`); 503 conversion in `_fetch_chain_with_spot` (raise `HTTPException(503, detail=...)` when the adapter error dict has `entitlement: True` — check `_fetch_chain` callers first: if the entitlement error comes back from `_fetch_chain` as a dict, convert at the endpoints); remove `_fetch_chain` (verify zero callers).
- [ ] **Step 4: Run** `tests/wave3 tests/terminal tests/wave2/test_strategy_hints.py` — all pass.
- [ ] **Step 5: Commit** — `fix: phase-2 deferred minors (chain key aliases, 503 entitlement, dead wrapper, regime dataclass)`.

---

## Final Gate (verification-before-completion)

- [ ] Full suite: `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-phase3a -p no:cacheprovider` → **0 failures** (527+ grows).
- [ ] Grep gate: `rg "import openalgo|from openalgo" src/ -g "*.py"` → zero.
- [ ] Line rule: no new/modified file > 500 lines.
- [ ] No new runtime deps (`git diff` on `pyproject.toml` = empty).
- [ ] Whole-branch review + fixes; ledger `.superpowers/sdd/progress.md` updated; CHANGELOG entry + roadmap §17 Phase 3 row update + README feature-list touch; handoff doc.
- [ ] Merge decision presented to the user (do not merge without explicit request).

## Execution notes

- SDD loop per task (briefs under `C:\Users\rohan\AppData\Local\Temp\opencode\phase3a\`; review packages written manually via `git diff -U10 BASE HEAD` — the skill helper script paths contain literal backslashes on Windows).
- Base commit for each review = the commit recorded before that task's implementer dispatch (never `HEAD~1`).
- `tests/wave6/session_simulator.py` is a helper module; pytest must NOT collect it as tests (no `test_` in the filename).
- The simulator's `_build_decision`-style helpers may be shared between test files via `from tests.wave6.session_simulator import ...` (tests/ has `__init__.py` packages — verify importability; if the import path fails, duplicate the small helper inline instead).
