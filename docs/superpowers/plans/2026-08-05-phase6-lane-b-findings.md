# Phase 6 Lane B — Findings: Kill switch TOCTOU race fix

**Date:** 2026-08-05
**Status:** Complete · full suite green (1182 passed / 0 failed) · roadmap #9 (Oracle #4)
**Scope:** `execution/mode_router.py` + `terminal/api/execution_router.py` + related test files (per lane ownership)
**Files changed:**
- `src/shettyxtreme/execution/kill_switch.py` (new — shared `KillSwitchGate`)
- `src/shettyxtreme/execution/mode_router.py`
- `src/shettyxtreme/terminal/api/execution_router.py`
- `tests/execution/test_kill_switch_gate.py` (new — 14 gate unit tests)
- `tests/execution/test_mode_router.py` (+7 TOCTOU race regression tests)
- `tests/wave3/test_api.py` (+4 API-level kill-switch tests)
- **Out-of-scope touches (flagged):** `src/shettyxtreme/terminal/api/app.py` (wires
  the shared gate into `ModeRoutingExecutor` — 1 import + 1 kwarg) and
  `src/shettyxtreme/terminal/api/models.py` (`KillSwitchResponse.placements_in_flight`
  — 1 defaulted field). Both are required by the mission's mandatory deliverables
  ("shared gate wired in production" and "surface placements that crossed the wire
  during the arm window"); both are backward-compatible defaults.
- `docs/superpowers/plans/2026-08-05-phase6-lane-b-findings.md` (this file)

---

## 1. What was implemented

### 1.1 `KillSwitchGate` — asyncio.Event gate + atomic file persistence

New module `src/shettyxtreme/execution/kill_switch.py`. The kill switch now has
**two layers** behind one shared object:

| Layer | Mechanism | Role |
|-------|-----------|------|
| In-process | `asyncio.Event` | Set on `arm()`, cleared on `disarm()` — consulted by the mode router immediately before the broker await, no filesystem round-trip |
| Durable | `~/.shetty_kill_switch` file | Written/removed **atomically** (`tempfile.mkstemp` + `os.replace`); survives restarts (a file armed by a previous process sets the event at construction); honored cross-process (`is_armed()` is `event OR file`) |

- `arm()` writes the file **first**, then sets the event — `is_armed()` (OR of both
  layers) can never observe a false-open gap.
- `disarm()` clears the event, then removes the file. Ordering is conservative in
  both directions (transient over-blocking during disarm is safe; never under-blocking).
- `_write_file` cleans up the temp file on failure and re-raises (an arm that
  cannot persist must surface as an HTTP 500, not a silent "armed").

### 1.2 `mode_router.py` — double-check immediately before the wire

`ModeRoutingExecutor.__init__` gains an optional `kill_gate: KillSwitchGate | None`.
`app.py` wires the gate created by `execution_router` (`get_kill_switch_gate()`), so
production shares one object between both enforcement points.

- `_kill_armed()` — armed via **either** the legacy `kill_switch_provider` callable
  **or** the shared gate (provider kept for backward compat with existing callers).
- `place_order` LIVE now ends in `_dispatch_live()`: re-check `_kill_armed()` **after
  any pre-await and immediately before `live.place_order`**, then record wire
  entry/exit on the gate. An arm that lands while the coroutine was suspended
  (concurrent HTTP arm request, or a future pre-wire await) blocks the placement
  instead of reaching the broker.
- Same final check added to the PAPER path (`_place_paper`) and to LIVE `modify_order`
  (before `live.modify_order`). `cancel_order` keeps its entry check only — cancels
  are risk-reducing; a cancel that slips through during an arm window is acceptable
  and the entry check already blocks when armed at start.
- After dispatch, if the gate is armed, a warning is logged:
  `"order <symbol> crossed the wire during the kill-switch arm window"`.

### 1.3 `execution_router.py` — gate-backed arm/disarm + arm-window reporting

- Module-level `_kill_gate` rebuilt lazily when `_kill_switch_path` changes (keeps
  every existing test that monkeypatches the path working; the path is never
  changed in production).
- `is_kill_switch_armed()` and `GET /kill-switch` read through the gate (event OR
  file) instead of a raw `os.path.exists`.
- `activate_kill_switch` now calls `gate.arm()` / `gate.disarm()` (atomic file
  write instead of `Path.touch()`). The arm response carries
  `placements_in_flight` — how many placements were already dispatched to the
  broker when the switch was armed — and logs a WARNING when that count is > 0
  ("placed just before kill", honesty-first).

### 1.4 Wire accounting semantics

- `note_wire_entry()` is called only for **LIVE** placements that pass the final
  gate (paper is simulated — not the wire).
- `arm()` snapshots `placements_in_flight` and `total_placements_at_arm`. A
  placement that dispatched before the arm and completes after it is reported as
  having crossed the wire in the arm window — surfaced, not hidden. This is the
  "honest reporting" half of the fix (recon §5.3).

## 2. Findings

### 2.1 The LIVE-mode check-to-wire path is already synchronous — the double-check is defense-in-depth

Reading the current `place_order` LIVE branch: the entry kill check (line ~74) →
adapter resolution → session-validity probe → `await live.place_order` contains
**no await in between**. So today, an arm cannot interleave between the check and
the wire — the race is the inherent one where an arm after dispatch can't stop an
in-flight order. The double-check matters in two real places:

1. **`approve_proposal` → `engine.approve` → `place_order`**: there ARE awaits
   between `execution_router`'s check and `mode_router`'s entry check. The gate
   closes that gap with zero file I/O.
2. **Future pre-wire awaits**: any refactor that adds an await before the broker
   call inherits the protection for free — the check is right next to the wire.

### 2.2 The gate re-consulted at the wire is what makes the second check meaningful

`_dispatch_live` calls `_kill_armed()` again (provider + gate). Because the
provider in production (`is_kill_switch_armed`) is itself gate-backed, the two
checks collapse to "check the event, dispatch" with the event armed synchronously
by `arm()`. The regression test `test_live_place_double_check_blocks_arm_between_checks`
proves the re-check fires even when only the provider flips state between the two
checks (deterministic simulation of an arm landing mid-flight).

### 2.3 In-flight placement: inherent TOCTOU, now surfaced

`test_in_flight_placement_surfaces_in_arm_report` mocks a slow broker
`place_order` that holds an `asyncio.Event`, arms the gate mid-flight, and asserts
`arm_report["placements_in_flight"] == 1`. The placement completes (it was already
dispatched — unavoidable) but the operator is told, on the arm response and in the
log, that one order crossed the wire during the arm window. This is the honest
contract: the gate shrinks the window and *reports* the residual, it cannot
teleport an in-flight order back.

### 2.4 Atomic write, no residue

`test_kill_switch_arm_writes_atomically` (API level) and
`test_atomic_arm_leaves_no_temp_residue` (unit level) assert no
`.shetty_kill_switch.*` temp files remain after an arm and the marker file
contains `armed\n`. `tempfile.mkstemp` in the same directory guarantees
`os.replace` is same-volume (safe on Windows).

### 2.5 Restart survival preserved

`test_gate_honors_pre_existing_file_across_restart` + the existing wave5
`test_stale_kill_switch_file_armed_across_restart` confirm a file armed by a
previous process arms a fresh gate at construction. The file layer is untouched in
its role; the event merely mirrors it.

### 2.6 Verification

- Full pytest suite: **1182 passed / 0 failed / 0 skipped** (baseline 1116 +
  concurrent Lane A/C test additions + **25 new tests from this lane**).
- `grep "import openalgo|from openalgo" src/` → zero matches.
- God-module guard: no file > 1000 lines (largest touched: `execution_router.py`
  at ~407 lines).
- `graphify update .` run (graph: 7009 nodes, 14752 edges).

### 2.7 Operational note — concurrent Lane A edits

Lane A (F-CORE-001 model consolidation) landed mid-session and the working tree
was shared. Its rename `Order` → `OrderRequest` (canonical in `core.data_models`,
re-exported through `core.interfaces`) was 3-way-merged with this lane's edits to
the shared `tests/execution/test_mode_router.py` and `mode_router.py`. The merge
dropped the `KillSwitchGate` import from `mode_router.py` (it still imported — the
reference is a lazy annotation under `from __future__ import annotations`); it was
re-added explicitly and `_dispatch_live`'s `order: Order` annotation corrected to
`OrderRequest`. One stale `from ... import Order` remains in
`tests/wave5/test_proposal_flow.py:451` (function-body import) — it resolves under
full-suite import order (the `core.interfaces` package binds `Order` into the
package namespace before that test runs) but fails if the file is run in
isolation; it is Lane A's test file, left untouched.

## 3. Follow-ups (not done — out of scope)

- **Cross-process arm visibility**: `is_armed()` re-stats the file per call, so a
  switch armed by another process is honored on the next placement. A true
  cross-process signaling channel (named pipe / lock file with watcher) is beyond
  this lane — the file stat is the pragmatic contract and matches the pre-existing
  behavior.
- **In-flight count on disarm**: `disarm()` does not report how many placements
  completed during the armed interval. The data is available on the gate
  (`total_wire_entries` delta across arm/disarm); exposing it on the disarm
  response would be a 5-line follow-up if the operator wants an after-action count.
- **Cancel during arm window**: cancels keep their entry check only. If policy
  ever requires cancels to also double-check immediately before the wire, it's a
  one-line addition mirroring `_dispatch_live`.
