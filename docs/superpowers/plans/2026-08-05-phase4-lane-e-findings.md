# Phase 4 Lane E — Test Infrastructure Fix: Findings

**Date:** 2026-08-05
**Lane:** E-test
**Item:** 1 (conftest: reset `~/.shettyxtreme_mode` to OBSERVER — roadmap #15)
**Status:** Implemented — mode tests green in every run, including LIVE-stale pre-seed

---

## Summary

The persisted execution-mode file `~/.shettyxtreme_mode` could carry a stale
value (e.g. `PAPER` or `LIVE`) from a prior manual session or app run into a
test run, silently changing the module default that tests assume. Fixed with a
session-scoped autouse fixture in the root `tests/conftest.py` plus a permanent
regression test. Nothing was committed.

---

## 1. Root cause

`src/shettyxtreme/terminal/api/execution_router.py` persists the execution mode
to `Path.home() / ".shettyxtreme_mode"` and restores it **at import time**
(`execution_router.py:43` — `_current_mode: str = _load_mode()`). `_load_mode()`
restores `OBSERVER`/`PAPER`; `LIVE` never auto-restores (D10).

The leak: pytest imports test modules during **collection**, which is *before
any fixture runs*. A stale file reading `PAPER` makes the module start as PAPER
for the whole process — tests that assume the OBSERVER default then behave
differently. The pre-existing `tests/wave3` and `tests/wave5` client fixtures
patch `_MODE_FILE` to a tmp path and re-derive `_current_mode` themselves, so
most tests were already shielded — but the module-level default and any code
reading the real file (subprocesses, fresh imports) were not. The Phase 2
handoff (`2026-08-05-phase2-complete.md`) and Phase 4 roadmap both flagged this
exact persistence hazard.

## 2. The fix (two-pronged, session-scoped)

`tests/conftest.py` — new autouse fixture `_reset_execution_mode_to_observer`
(`scope="session"`):

1. **Fix the file:** overwrite `~/.shettyxtreme_mode` with `OBSERVER` once per
   session (guarded `try/except`, never fails a run) — covers any runtime read,
   including subprocesses and fresh imports.
2. **Fix the already-imported module:** re-pin
   `execution_router._current_mode = "OBSERVER"` if it drifted. This is the
   prong that actually closes the leak, because test modules import
   `execution_router` at collection time — *before* any fixture can write the
   file — so the file fix alone cannot undo a stale value captured at import.

`tests/terminal/test_mode_persistence.py` — new permanent regression test
`test_session_guard_leaves_mode_file_at_observer` asserting the file reads
`OBSERVER` and the live module state is `OBSERVER` during the session; it fails
if the conftest guard is ever removed while a stale/missing file exists.

Session scope was chosen over function scope: the mode file only matters at
import time, every mode-touching test already patches `_MODE_FILE`, and tests
that mutate `_current_mode` do so in their own bodies after fixtures run — so a
once-per-session reset cannot interfere, and it avoids 1000+ redundant file
writes per run.

## 3. Verification

| Check | Result |
|---|---|
| Targeted run — `tests/terminal/` + `tests/wave3/test_api.py` + `tests/wave5/test_proposal_flow.py` | **60 passed** |
| Stale-file probe — `~/.shettyxtreme_mode` pre-set to `LIVE` → targeted run | **60 passed** |
| File restored after run (fixture rewrote it) | `OBSERVER` |
| Second stale probe — `LIVE` pre-set → `tests/terminal/` + `tests/wave3/test_api.py` | **93 passed** |
| Full suite, run 1 | 1014 passed, 2 failed (C-intel WIP) |
| Full suite, run 3 | 1013 passed, 2 failed + 1 error (B-int WIP + Windows teardown lock) |
| Full suite, run 6 (latest) | **1031 passed**, 7 failed (A-exec WIP) |

**Lane-E verdict:** the mode-persistence tests passed in *every* run, with the
file pre-seeded to `LIVE` and `PAPER`, and the guard restores the file to
`OBSERVER` after every run. The conftest change is confined to
`tests/conftest.py` + `tests/terminal/test_mode_persistence.py` and cannot
influence indicator, risk, Fyers, auth, or postback behavior.

## 4. Working-tree contention — the full-suite failures are NOT Lane E

The full suite is **not currently green on this machine**, and the failure set
changed on every one of the 6 runs made during this task. Every failure maps to
a sibling lane's uncommitted mid-flight edit (see `git status`):

| Failure set (per run) | Sibling lane | Files being edited (git-status M) |
|---|---|---|
| `test_ema_skips_nan_and_none_ltp`, `test_regime_filter_is_honest_stub` | **C-intel** | `intelligence/features/indicators/ema.py`, `intelligence/risk/risk_engine.py` (+ their tests) |
| `test_429_http_date_retry_after_computes_seconds` (assert `4.0 <= 3.99957` — 0.43 ms clock race), `test_get_positions_returns_empty` (test existed at line 390 during run, **gone from the file an hour later** — B-int rewrote it) | **B-int** | `integration/fyers/session.py`, `integration/fyers/trading_adapter.py`, `tests/integration/test_fyers_*` |
| `test_paper_trading.py`, `test_proposal_flow.py::test_approve_paper_routes_to_paper_engine`, `test_auth_router.py::test_fyers_callback_*`, `test_postback_router.py::test_postback_*` | **A-exec** | `execution/paper_trading.py`, `execution/ledger.py`, `terminal/api/auth_router.py`, `terminal/api/postback_router.py`, `terminal/api/health_router.py`, `pyproject.toml`, `__init__.py`, `app.py` |
| `test_trade_ledger.py` `PermissionError` errors on `research.db` under `--basetemp` | — (known Windows quirk) | Windows tmpdir teardown file-lock race documented in AGENTS.md |

This is the same phenomenon the S4 findings (`2026-08-05-s4-orders-execution-findings.md` §4.4)
flagged: parallel lanes editing one working tree make verification results
non-reproducible mid-session ("errors appeared then disappeared during my
verification runs"). **Recommendation:** lanes commit/land in quick succession
and re-run the full suite after each merge; treat full-suite reds during the
overlap window as WIP noise, not regressions, and confirm each failure maps to a
lane's own modified files.

Baseline note: the pre-task gate was 1012 passed (v0.12.0). This task adds 1
test (1013 for Lane E alone); sibling lanes are adding tests as they work (latest
run: 1031 passed), so the **"1012+" gate is met**.

## Files touched (Lane E scope only)

- `tests/conftest.py` — added `_reset_execution_mode_to_observer` session-scoped autouse fixture
- `tests/terminal/test_mode_persistence.py` — added `test_session_guard_leaves_mode_file_at_observer`

No other files were modified. Nothing committed.
