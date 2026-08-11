# Handoff: Phase 2 Complete — Deep Audit

**Date:** 2026-08-05
**Session:** Phase 2 (deep audit)
**Status:** ✅ Complete, ready for Phase 3

---

## What Was Accomplished

### Audit Methodology
1. **6 parallel Explorers** audited every layer (integration, core, intelligence+research+data+options+learning, knowledge, execution+auth, terminal)
2. **Oracle independently reviewed** all findings — confirmed all CRITICAL, reclassified 1 (F-CORE-001 from CRITICAL to MAJOR)
3. **Consolidated audit report** at `docs/superpowers/plans/2026-08-05-audit-findings.md`
4. **Operator selected all 3 tiers** for execution in this session

### Tier 1 — Money-path + Security (4 fixes, 959→991 tests)

| ID | Issue | Fix | Files |
|----|-------|-----|-------|
| F-INT-001 | SL orders transmitted as SL-M (limit price dropped) | `ORDER_TYPE_MAP[SL] = 4` (SL-L), not 3 | `mappings.py`, `test_fyers_mappings.py`, `test_fyers_trading_adapter.py` |
| F-EXEC-001 | CSRF/D10 bypass — LIVE mode activatable via query param | Typed `confirm="LIVE"` in body, per-session CSRF token for approve, WS Origin validation, kill-switch disarm requires typed "DISARM" | `execution_router.py`, `app.py`, `ws_manager.py`, `models.py`, frontend components, 3 test files |
| F-CORE-005 | cancel_order routes to paper engine in LIVE | Route by mode: LIVE→live adapter (with session validity + kill switch gates), PAPER/OBSERVER→paper | `mode_router.py` |
| F-KNOW-001 | NULL-symbol fills → phantom cross-symbol pairing | Resolve symbol from order-id before recording; removed "?" catch-all in `pair_fills` | `ledger.py`, `ledger_recorder.py`, `test_trade_ledger.py` |

### Tier 2 — Correctness + Reliability (5 fixes, 991→1011 tests)

| ID | Issue | Fix | Files |
|----|-------|-----|-------|
| F-INTEL-003 | `tte=0.25` hardcoded greeks (theta understated 15-500×) | Compute tte from actual expiry date; parse ISO, Fyers symbol-style, epoch; floor at 1/365 | `intelligence_router.py`, new `test_intelligence_router.py` (10 tests) |
| F-INTEL-002 | Volume double-count at bar boundary + cumulative volume inflation | Remove `apply_tick` from `_create_state`; BarAggregator tracks `volume_at_bar_open`, computes delta; also fixed latent `oi` AttributeError crash | `bar_builder.py`, `_util.py`, `test_bar_builder.py`, new `test_fyers_util.py`, `test_fyers_data_adapter.py` |
| F-INTEL-001 | Stub voters dominate signals (42% weight, constant noise) | Deleted `orb_voter.py` (both stubs); removed from pipeline registry; added neutral-abstain regression guard | `voters/orb_voter.py` (deleted), `voters/__init__.py`, `pipeline.py`, `test_intelligence_pipeline.py`, `test_signal_engine.py`, `test_lifespan_wiring.py` |
| F-INT-002 | retry-after=0 → immediate retry storm on 429 | Clamp to [1.0, 10.0] seconds; handle HTTP-date format | `client.py`, `test_fyers_client.py` (3 new tests) |
| F-KNOW-002 | Proposal persistence no-op (`db_path=None`) | Pass `db_path="data/proposals.db"`; serialize full payload as JSON; load PENDING/APPROVED on init; DB failure degrades to in-memory | `app.py`, `execution_engine.py`, new `test_execution_engine.py` (2 tests) |

### Tier 3 — Critical Gaps (2 audits + 1 fix, 1011→1012 tests)

| ID | Issue | Result |
|----|-------|--------|
| HSM data adapter audit | 5 critical bugs found: wrong field mapping (5/10 tick fields corrupt), wrong SDK kwargs, wrong token format, wrong disconnect method, missing `aws-lambda-powertools` dependency | **All fixed** — `_parse_tick` uses real SDK field names (`vol_traded_today`, `last_traded_time`, `bid_price`, `ask_price`, `prev_close_price`); `_build_socket` uses correct kwargs; raw JWT passed; `close_connection()` called; `aws-lambda-powertools` installed and declared in `pyproject.toml` |
| DeepSeek API key audit | Verified secure: env-only, read at call time, never logged, no key committed | **No changes needed** — 2 low-risk theoretical leaks documented with recommendations |
| F-CORE-001 model consolidation | Divergent model pairs (interfaces vs data_models) — maintenance hazard, not active bug | **Deferred** to next session |

---

## Current State

### Test Suite
- **1012 passed / 0 failed / 0 skipped** (~47s)
- Baseline: 959 (pre-Phase 2) → 1012 (post-Phase 2)
- Net gain: +53 tests

### Architecture
- **Broker**: Fyers (unchanged from Phase 1)
- **Data adapter**: Now correctly wired to real Fyers SDK contract (HSM field names, JWT token, SDK kwargs)
- **Execution**: D10 safety hardened (typed confirmation, CSRF token, WS Origin validation)
- **Signals**: Stub voters removed; only real voters (options_flow, micro, breadth) remain
- **Greeks**: tte computed from actual expiry date
- **Proposals**: Persisted to `data/proposals.db` with full payload, recovered on restart
- **Ledger**: NULL-symbol fills resolved before recording; no cross-symbol phantom pairing

### Dependencies
- `aws-lambda-powertools>=2.0.0` added to `pyproject.toml` (required by Fyers SDK's `fyers_logger.py`)
- `fyers-apiv3` still installed with `--no-deps` (to avoid `asyncio==3.4.3` stdlib shadow)

### File Ownership (for next session)
- `integration/fyers/data_adapter.py` — 384 lines, HSM field mapping fixed
- `integration/fyers/data_socket.py` — 358 lines, SDK contract fixed
- `terminal/api/execution_router.py` — 355 lines, CSRF/typed-confirm added
- `execution/execution_engine.py` — 382 lines, proposal persistence added
- `execution/mode_router.py` — 198 lines, cancel/modify routing fixed
- `execution/ledger.py` — 169 lines, NULL-symbol handling fixed
- `intelligence/voters/` — `orb_voter.py` deleted; only 3 real voters remain
- `terminal/api/intelligence_router.py` — 354 lines, tte computation added

### Known Issues (Carried Forward)
- `app.py` at ~569 lines (pre-existing known violation)
- F-CORE-001: divergent model pairs (interfaces vs data_models) — deferred
- Index ticks still use `datetime.now(UTC)` for timestamp (SDK `index_val` feed has no `last_traded_time`, only `exch_feed_time`)
- `~/.shettyxtreme_mode` file can persist "LIVE" from a prior run, causing test failures — tests should reset to OBSERVER in conftest
- 30+ MAJOR findings from audit remain unfixed (see audit report for full list)

---

## Phase 3: Cockpit Redesign (Next)

### Scope
FULL cockpit UI redesign (not polish). DESIGN.md is binding:
- Near-black canvas (`#0d0c0a`), one accent (`#f5b942` warm amber)
- Indian price convention: **red=up `#f6525c`, green=down `#2ebd85`** (NEVER invert)
- JetBrains Mono tabular numerals, Inter labels
- Glanceability <1s, honest data states, no dead ends, keyboard-first density

### Slices (approval-gated)
- **S1**: Shell + clock + connection status (DESIGN.md token review gate)
- **S2**: Watchlist + live ticks (gate: tick-to-pixel, Indian red=up)
- **S3**: Positions/PnL/real margin (gate: matches broker console)
- **S4**: Orders + execution (gate: OBSERVER proposals-only, LIVE typed-confirm)
- **S5**: Chain/scanner/intelligence (gate: honesty guarantees hold)
- **S6**: Depth (research/analytics/settings)

### Workflow
1. Brainstorm IA with operator first (2-3 density options via question tool)
2. Designer-led implementation in gated slices
3. Each slice DESIGN.md-reviewed before merge
4. `npm run check` + build per slice

---

## Remaining Audit Findings (Not Fixed)

### MAJOR (30+ items, see full report)
Key items worth addressing in future sessions:
- **F-INT-003**: `_fatal_error` never cleared on data socket reconnect
- **F-INT-004**: Socket fatal errors invisible to app (no `on_error`/`on_close` wired)
- **F-INT-005**: Live tick OI hardcoded to None
- **F-INT-008**: Instrument master refreshed only when DB empty (stale after a few days)
- **F-INT-009**: Session-validity gate no-op for unknown expiry (token_expiry usually None)
- **F-INT-011**: Account/quotes errors degrade to `[]`/`{}` for all FyersErrors (masks token expiry and -373 entitlement)
- **F-AUTH-001**: Pre-market liveness probe always uses credential-less client (false alarm daily)
- **F-AUTH-002**: OAuth callback never validates `state` (login CSRF)
- **F-EXEC-004**: Paper MARKET orders fill at 0.0 (poisons paper P&L and learning)
- **F-KNOW-003**: EOD compares UTC hours vs IST config (5h late)
- **F-KNOW-004**: OI tracker subscribed to wrong event shape (latent)
- **F-KNOW-005**: `pair_fills` drops partial-fill remainders
- **F-TERM-003**: REST hydration hammering (2N sequential Fyers calls per watchlist refresh)
- **F-TERM-007**: Unauthenticated legacy `/api/postback/dhan` accepts arbitrary payloads

### MINOR (20+ items)
See `docs/superpowers/plans/2026-08-05-audit-findings.md` for full list.

---

## Verification Gates (Every Phase Exit)

```powershell
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider
```

Plus:
- `grep -r "import openalgo\|from openalgo" src/` = zero
- No new file >500 lines
- `npm run check` 0 errors before `npm run build`
- Layering greps
- `graphify update .` after code changes

---

## Working Method (Binding)

1. **Phase Zero** — Recon + Plan + Questions: Dispatch background Explorers, produce documented mission plan, use QUESTION tool to confirm scope/priority/ordering
2. **Cheap specialists do the work, heavy models verify**: Explorer/Librarian/Fixer do recon/research/edits; Oracle reviews EVERY substantive change before finalizing
3. **Dispatch background tasks in parallel** with explicit file ownership (no two writers on one file). Track task IDs. Never finalize until every terminal result is reconciled AND the project test suite passes.
4. **Use @council for big judgment calls**: broker API choice/design, data-model changes, cockpit IA
5. **Ask questions whenever a decision is irreversible or expensive** (schema changes, contract changes, UI direction). Give options with trade-offs.

---

## Project Rules (Non-Negotiable)

- **Test command**: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
- **Suite**: 1012 passed / 0 failed / 0 skipped (current baseline)
- **No file >500 lines** (known violation: `app.py` ~569 lines)
- **No openalgo imports from src/** (`grep -r "import openalgo\|from openalgo" src/` = zero)
- **Layered architecture**: `core/` → nothing external; `intelligence/` → core only; `integration/` → core/interfaces + external APIs; `knowledge/` → core only; `research/` = only LLM layer
- **OBSERVER-first execution** (D10): platform proposes, human approves; LIVE needs typed confirmation
- **DESIGN.md binding for UI**: near-black canvas, one accent, red=up `#f6525c` / green=down `#2ebd85`, JetBrains Mono tabular, Inter labels
- **Never commit without being asked**
- **Never paper over a real error** — surface it, recommend options, ask, then act

---

## Next Session Prompt

Paste this into the new session:

```
# SHELTERED MISSION CONTINUATION — Phase 3 (ShettyXtreme Cockpit Redesign)

You are the Orchestrator of ShettyXtreme (FastAPI + Svelte 5, India-first options intelligence workstation). Phase 2 (deep audit) is complete. Read the handoff at `docs/superpowers/handoffs/2026-08-05-phase2-complete.md` for full context.

## Current State
- **Phase 1.0 + Phase 1 + Phase 2 complete**: 1012 tests passing
- **Version**: 0.12.0
- **Branch**: create new branch for Phase 3

## Phase 3: Cockpit Redesign
FULL cockpit UI redesign (not polish). DESIGN.md binding. Slices S1-S6, approval-gated. Brainstorm IA first (2-3 density options), then Designer-led implementation.

## Remaining Audit Items (Deferred)
- F-CORE-001: divergent model pairs (interfaces vs data_models)
- 30+ MAJOR findings (see `docs/superpowers/plans/2026-08-05-audit-findings.md`)
- HSM index tick timestamp (SDK limitation, not a bug)

## Working Method (Binding)
1. Phase Zero — Recon + Plan + Questions
2. Cheap specialists do work, heavy models verify
3. Background parallel tasks with explicit file ownership
4. @council for big judgment calls
5. Ask questions for irreversible/expensive decisions

## Project Rules (Non-Negotiable)
- Test command: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
- Suite: 1012 passed / 0 failed / 0 skipped
- No file >500 lines
- No openalgo imports from src/
- Layered architecture law
- OBSERVER-first execution (D10)
- DESIGN.md binding for UI
- Never commit without being asked
- Never paper over a real error

## First Action
Read the handoff doc, then brainstorm cockpit IA with 2-3 density options via question tool.
```

---

## Session End Summary

**Phase 2 delivered:**
- 1012 tests passing (baseline 959 → 1012, +53 tests)
- 4 Tier 1 fixes (money-path + security)
- 5 Tier 2 fixes (correctness + reliability)
- 1 Tier 3 fix (HSM data adapter — was completely broken)
- 2 Tier 3 audits (DeepSeek key verified secure, HSM binary parsing audited)
- 124 files changed, +8189/-5969 lines
- Full audit report at `docs/superpowers/plans/2026-08-05-audit-findings.md`

**Ready for Phase 3 (cockpit redesign) in next session.**
