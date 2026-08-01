# Phase 3A — Advanced Intelligence: Design Spec

**Date:** 2026-08-01 · **Status:** APPROVED (user) · **Repo:** D:\ShettyXtreme · **Branch:** to be created from master

## 1. Purpose

Graduate the intelligence layer from display to validated edge: session-aware shadow-voter graduation (≥20 sessions), calibration consumed by sizing, correlation block caps wired into the signal path, conviction (D/P/G) live-wired, and walkforward depth — on the machinery that already exists (`ShadowManager`, `VoterCorrelation`, `OutcomeTracker`, `CalibrationCurve`, 4 shadow voters, `walkforward.py`). Phase 2's review follow-ups ride along. This is sub-project 3A of Phase 3; 3B (research workspace + AI research layer, D3) is a separate spec pending the LLM-provider decision.

## 2. Binding constraints (from decisions pack + repo conventions)

- **D3:** agents never gate/place orders — this spec adds NO LLM surface. Everything is deterministic/statistical.
- **No-import rule (D1):** zero `import openalgo` / `from openalgo` in `src/`.
- **≤500 lines per file; zero new runtime dependencies** (stdlib + existing packages only; test helpers may use pytest).
- **Suite gate:** 527 passed / 0 failed → never shrinks.
- **Test runner (Windows):** `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=... -p no:cacheprovider` (never bare `pytest`).
- **Dirty file:** `docs/superpowers/plans/2026-07-31-graphify-upgrade.md` is pre-existing unstaged — never stage or commit it.
- **Learning-loop honesty (§14/§17):** "the backtest path is the live path" — synthetic validation is test-only and never presented as real data.

## 3. Design

### 3.1 Session-aware shadow gate + graduation

**Existing:** `ShadowManager` (src/shettyxtreme/intelligence/signals/shadow_manager.py): `shadow_sessions` table (shadow_name, signal_id, vote_direction, vote_confidence, outcome, was_correct); `should_promote(name)` = rows>20 AND hit rate>0.55; `_is_correct(vote_dir, outcome)` treats ANY WIN as correct for ANY direction.

**Changes:**
1. `shadow_sessions` gains `session_date TEXT` column (migration: `CREATE TABLE IF NOT EXISTS` with the new column; existing DBs get `ALTER TABLE ... ADD COLUMN` guarded by a pragma table_info check — no data loss).
2. `log_shadow_results(signal_id, shadow_votes, session_date)` — new required param; the DB insert includes it.
3. `should_promote(name)` — gate = **distinct session_date count ≥ 20** AND hit rate > 0.55 over evaluated (was_correct not null) rows. Constant `MIN_SESSIONS = 20`, `PROMOTION_HIT_RATE = 0.55` at module level.
4. **Direction-aware correctness:** `compare_shadow_vs_live(signal_id, live_outcome, live_direction)` — new param; a vote is correct iff `sign(vote_direction) == sign(live_direction)` and outcome is WIN. Neutral votes (0.0) are never correct. (Backward-compatible default `live_direction=1.0` keeps old call sites working; update the existing call sites to pass it.)
5. **Graduation:** `graduate(name) -> ShadowFn | None` — registers the shadow's callable into the module-level default `VoterRegistry` via the existing `voter(name, weight)` decorator mechanics (registry.register), records graduation in a new `shadow_graduates` table (shadow_name PRIMARY KEY, graduated_at), returns the registered fn or None if the gate is not met. Idempotent: already-graduated name re-registers with current weight, does not duplicate rows.
6. `graduation_status() -> list[dict]` — per shadow: sessions (distinct count), evaluated count, hit rate, graduated bool, registered bool — for the terminal endpoint.

### 3.2 Synthetic session simulator (test-only)

`tests/wave6/session_simulator.py` — deterministic helper (seeded, no randomness): `SimulatedSession(date, signals)` where each signal = (features dict, regime, options_context, votes {name: Vote}, live_direction, outcome). Builders:
- `make_shadow_manager(db_path)` — real ShadowManager on a tmp sqlite.
- `run_sessions(manager, sessions)` — for each session: for each signal: run_shadow → log_shadow_results(session_date=...) → compare_shadow_vs_live(outcome, direction).
- `good_voter_session(...)` / `poor_voter_session(...)` — scripted vote/outcome patterns: a shadow that agrees with the live direction ≥ 60% of the time across ≥ 21 sessions (so `should_promote` true), and one that agrees < 45% (gate false at 20+ sessions).
- Demo test: `test_end_to_end_graduation` — 21+ sessions → `should_promote` true → `graduate` registers into the default registry → `get_registry().get(name)` returns the callable; second `graduate` is idempotent. Negative test at 19 sessions → gate false.

### 3.3 Calibration → sizing

**Existing:** `CalibrationCurve` (src/shettyxtreme/learning/calibration.py): fit/predict/is_reliable/get_curve, 10 bins, `RELIABLE_THRESHOLD = 30`. No consumer. Quantity flows: strategy hint → `ExecutionEngine._build_order` reads `strategy_hint["quantity"]`.

**Changes:** new `src/shettyxtreme/learning/sizing.py`:
- `class CalibratedSizing:` with `__init__(self, curve: CalibrationCurve, base_rate: float = 0.5, min_multiplier: float = 0.25, max_multiplier: float = 2.0)`.
- `adjust(base_quantity: int, conviction: float) -> int` — if `not curve.is_reliable(decisions)` (curve carries no decision list; is_reliable takes decisions — so sizing holds its own `reliable` flag set via `set_reliable(bool)` or takes `curve.predict` output + explicit reliability) — **design decision:** `adjust` computes `p = curve.predict(conviction)`; multiplier = `p / base_rate`, clamped to [min_multiplier, max_multiplier]; returns `max(1, round(base_quantity * multiplier))`. Reliability: `CalibratedSizing.is_active` property set from `curve.is_reliable(decisions)` by the caller (sizing never touches the DB).
- Consumed in `intelligence/hints/strategy_hints.py::generate()` — optional constructor param `sizing: CalibratedSizing | None = None`; when set AND active, the hint gains `quantity` (computed from a `base_quantity` param on the hint generator, default 75 — one NIFTY lot) — the strategy hint's quantity is then picked up by the execution path. When None or inactive, no quantity on the hint (current behavior).

### 3.4 Correlation block caps in the signal path

**Existing:** `VoterCorrelation` (voter_correlation.py): compute_correlation_matrix/get_correlation_groups/get_block_cap/apply_block_caps — library only.

**Changes:** `SignalEngine.__init__` gains `correlation: VoterCorrelation | None = None` and `history_window: int = 50`. In `compute_signal`:
1. Collect raw votes.
2. If correlation is set: append current votes to an internal rolling history (cap `history_window`); if ≥ 5 signals seen, compute the matrix from history, derive groups (threshold 0.7), build caps map (name → block_cap for grouped names), and `apply_block_caps(votes, caps)` before weighting.
3. Everything else unchanged (weights still applied after caps).

### 3.5 ConvictionEngine wired (Phase-2 follow-up)

**Existing:** `ConvictionEngine.compute(votes, eligible)` (intelligence/conviction/conviction_engine.py) — library + tests only. `Signal` (signal_engine.py) has no D/P/G. Projection's `SIGNAL_V2` handler already reads D/P/G keys.

**Changes:** `Signal` dataclass gains `D: float = 0.0`, `P: float = 1.0`, `G: str = "contested"` (defaults — `asdict` serialization in outcome_tracker/analytics unaffected; tests that construct Signal positionally keep working since defaults are appended last). `SignalEngine.compute_signal` computes `ConvictionResult` from the (capped) votes with `eligible=len(self.voters)` and attaches D/P/G to the returned Signal. `compute_signal_from_votes` alias unchanged.

### 3.6 Walkforward depth

**Existing:** `learning/walkforward.py` (purged-CV protocol, tested). Changes (read the file first — extend, don't restructure):
- Report gains per-voter breakdown: for each voter name, count of signals where it voted, directional hit rate (against realized outcomes).
- Report gains per-regime breakdown: group evaluations by regime label with win rate and sample count.
- PnL uses the existing cost model (`compute_cost` / `learning/cost_model`) so premium/slippage/brokerage are netted in the walkforward evaluation (option-premium-aware), and the PositionManager exit policy (TP/TSL/EOD) is applied to simulated fills where the harness has entry/exit prices.

### 3.7 Learning status endpoints (+ minimal terminal surface)

New `src/shettyxtreme/terminal/api/learning_router.py` (prefix `/api/learning`):
- `GET /api/learning/calibration` — `{reliable: bool, points: [{conviction_bin: [lo, hi], actual_win_rate, sample_size, confidence_interval: [lo, hi]}]}` (from a `CalibrationCurve` fitted from the OutcomeTracker DB at request time — DB path from a module-level config, empty when no DB/unreliable).
- `GET /api/learning/shadows` — `{shadows: [{name, sessions, evaluated, hit_rate, graduated, registered}]}` from `ShadowManager.graduation_status()` (same DB config).
- Registered in `app.py`; response models added to `terminal/api/models.py`.
- Tests: with tmp DBs (outcome tracker + shadow manager) populated by the simulator, endpoints return the expected shapes.
- Svelte panel: only if cheap — a small "Learning" section in the hints panel area or header dropdown; otherwise endpoints-only for this phase (explicitly noted in the plan).

### 3.8 Phase-2 deferred minors

- `strategy_hints.py::_select_strike`: normalize `strike_price`/`drv_option_type` aliases (same normalization as `intelligence_router._enrich_chain` — extract a shared helper if clean, else duplicate the 4-line normalization).
- Endpoint-level test: `DataEntitlementError → HTTP 503` conversion in `intelligence_router` (the raising path `_fetch_chain_with_spot`).
- Remove dead `_fetch_chain` wrapper in `intelligence_router.py` (both endpoints use `_fetch_chain_with_spot`).
- `on_regime_changed` dataclass-path test in `tests/terminal/test_projections.py` (symmetric with the `on_signal_v2` guard).

## 4. Data flow (3A)

```
live pipeline / simulator
  → ShadowManager.run_shadow → log_shadow_results(session_date)
  → compare_shadow_vs_live(outcome, live_direction)   [direction-aware]
  → should_promote (≥20 sessions + hit rate) → graduate → VoterRegistry
SignalEngine.compute_signal
  → [correlation caps] → [ConvictionEngine D/P/G] → Signal(D,P,G)
  → SIGNAL_V2 → projection → terminal
StrategyHints.generate [sizing hook] → quantity → ExecutionEngine._build_order
Walkforward: purged-CV → per-voter/per-regime breakdowns + cost/PnL
Terminal: /api/learning/{calibration,shadows} ← OutcomeTracker/ShadowManager DBs
```

## 5. Error handling

- Shadow DB migration: guarded ALTER TABLE (missing column → add; never crash on legacy DBs).
- `graduate`: gate not met → returns None (no exception); DB write failure → logged, returns None.
- Sizing: conviction outside [0,1] clamped; non-positive base_quantity → ValueError (explicit).
- Learning endpoints: DB missing/unreadable → 200 with empty/neutral payload (reliable: false, points: [], shadows: []) — never 500.
- Correlation: history shorter than 5 signals → caps skipped (documented behavior).

## 6. Testing

- Simulator-driven: session gate positive (21 sessions) + negative (19 sessions); hit-rate gate negative (45% agreement); graduation idempotency; direction-aware correctness (bearish vote + long WIN → not correct).
- Sizing: multiplier math, clamps, inactive when unreliable, hint-quantity end-to-end.
- Correlation: block cap scales group weights in compute_signal; history window cap.
- Conviction wiring: Signal carries D/P/G; projection updates on SIGNAL_V2 with D/P/G; existing wave2 signal-engine tests unchanged.
- Walkforward: breakdown sections present; cost netted.
- Endpoints: shapes with tmp DBs; empty-DB fallback.
- Full suite: 527 → ~560+ passing, 0 failures; grep gate zero; ≤500 lines.

## 7. Excluded / deferred

- **3B research workspace + AI research layer** — separate spec; needs the LLM-provider decision.
- **Live `/optionchain` fixture** — blocked on live Dhan credentials (OPEN QUESTION stays).
- Live shadow-voter activation with real data — happens automatically once ≥20 real OBSERVER sessions accumulate; no fake claims of graduation.

## 8. Delivery

- New branch `phase3a-advanced-intelligence` from master; SDD task-by-task (briefs → implementer → task review → fix waves); final whole-branch review; ledger + handoff; merge decision presented to the user.
- Docs to update at completion: roadmap §17 Phase 3 row (partial), section 14 learning-loop wording if behavior changes, CHANGELOG entry, README feature list.
