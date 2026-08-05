# Handoff: Phase 1 Complete — Fyers Migration

**Date:** 2026-08-04  
**Session:** Phase 1.0 (honesty hardening) + Phase 1 (Fyers migration)  
**Status:** ✅ Complete, ready for Phase 2

---

## What Was Accomplished

### Phase 1.0: Honesty Hardening (874 tests)
Fixed the health system lies that would have made Fyers verification untrustworthy:
- **HealthProjection honesty**: Data health checks `is_stale()` (60s threshold), trading health checks token validity, components renamed to broker-neutral `data_adapter`/`trading_adapter`
- **Real margin**: `margin_available: None` until poller gets real data from broker (no more hardcoded 500000.0 lie)
- **UTC/IST convention**: `market_router.py` uses IST market-day via `ZoneInfo`, `voter_quality.py` uses UTC timestamps
- **TokenHealthMonitor**: 60s cadence (configurable), bounds token-expired state latency
- **Cockpit S0**: Connection pip with 4 states (LIVE/STALE/DISCONNECTED/EXPIRED), watchlist stale-fade (60s), honest empty/loading/error primitives, margin displays "—" when null

### Phase 1: Fyers Migration (959 tests)
Complete broker migration from Dhan to Fyers:
- **F1**: Fyers symbol resolver + instrument master (SQLite mirror of Fyers masters, weekly/monthly encoding, round-trip validation)
- **F2**: HTTP client (rate-limited 8 req/s, token-bucket, error taxonomy) + session management (token lifecycle, liveness probe)
- **F3**: WebSocket client (order socket JSON + data socket HSM via SDK, reconnect supervisor, token expiry detection)
- **F4**: Trading adapter (OrderExecutor + AccountInfo) + data adapter (MarketDataStream + DataProvider + history methods)
- **F5**: Auth layer (OAuth2 authorization-code flow, credential store, setup wizard, health monitor)
- **F6**: Terminal wiring (all routers de-Dhaned, Fyers adapters injected, postback → order socket, config updated)
- **F7**: Test porting (959 tests, all Fyers), Dhan residue sweep (integration/dhan/ deleted), docs (ADR-008, ARCHITECTURE_V2 §11 rewritten, frozen rules amended)

### Key Improvements
- `app.py` reduced from 565 → 504 lines (61 lines removed)
- All Dhan-specific code removed from `src/`
- Token expiry detection wired into LIVE mode gate (D10 safety intact)
- Rate limiting (8 req/s) prevents Fyers day-block
- Honest health states (stale/disconnected/token_expired) from Phase 1.0 preserved
- Version aligned at 0.12.0 across all files

---

## Current State

### Test Suite
- **959 passed / 0 failed / 0 skipped** (40.74s)
- Baseline: 861 (pre-Phase 1.0) → 959 (post-Phase 1)
- Net gain: +98 tests

### Architecture
- **Broker**: Fyers (OAuth2 authorization-code, daily-expiring tokens)
- **Auth**: `auth/credential_store.py` stores `app_id`, `secret_id`, `access_token`, `token_expiry` (Fernet-encrypted)
- **Adapters**: `integration/fyers/` implements core/interfaces Protocols
- **WebSocket**: Order socket (JSON, raw websockets) + data socket (HSM binary, SDK in supervised thread)
- **Rate limiting**: Token-bucket 8 req/s in `FyersHTTPClient`
- **Token lifecycle**: `FyersSession.is_valid()` checks expiry, `probe_liveness()` calls `/profile`
- **Health**: `HealthProjection` checks `is_stale()` + token validity, 4 distinct states
- **Margin**: Polled from broker via `get_margin()`, `None` until real data arrives

### File Ownership (for next session)
- `integration/fyers/`: Complete, all files <500 lines
- `terminal/api/`: All routers de-Dhaned, using Fyers adapters
- `auth/`: Fyers OAuth flow, credential store, health monitor
- `execution/`: `mode_router.py` gates LIVE on `is_session_valid()`
- `core/interfaces/`: `BrokerGateway` has `is_session_valid()` method

### Known Issues
- `app.py` at 504 lines (pre-existing known violation, improved from 565)
- `fyers-apiv3` SDK installed with `--no-deps` (HSM data socket guarded, runtime deps not installed)
- No Fyers sandbox available — testing uses real account in OBSERVER mode

---

## Phase 2: Deep Audit (Next)

### Scope
Audit EVERY layer for correctness, not just style. Hunt specifically:

**Logic bugs:**
- Wrong comparisons (>= vs >, off-by-one in bars/lookback)
- UTC vs IST timestamp mixing (Phase 1.0 fixed some, but check all layers)
- NaN/None LTP falling through
- Division by zero, percent change on zero/None close
- Wrong units (₹ vs paise, lots vs shares, decimals)
- Stale-data-is-fresh problems (health "healthy" when data is old)
- Event-bus race conditions
- asyncio + threading mixups (run_in_executor + blocking calls in the loop)
- Unclosed WS/threads on shutdown
- Reconnect storms
- Silent `except: pass` swallowing real errors

**Missing things:**
- Missing error paths (what happens when every API call fails?)
- Missing tests for critical modules
- Config drift (version numbers, legacy keys)
- Missing auth/token lifecycle handling
- Missing rate-limit handling
- Missing state recovery on restart
- Dead code
- Wrong assumptions documented as fact

### Workflow
1. Background Explorers per layer in parallel → each returns a CATEGORIZED findings report (severity: critical/major/minor; file:line; why it's wrong; suggested fix)
2. Oracle independently reviews the findings (catching misses)
3. Reconcile into ONE audit report
4. Present the report via a written doc (`docs/superpowers/plans/YYYY-MM-DD-audit-findings.md`)
5. Summarize the top 10 in chat with options
6. DO NOT auto-fix everything: propose a fix plan, ask which tiers to execute
7. Critical fixes (data corruption, money-path, crash) may be fixed immediately AFTER asking
8. Every fixed finding must be demonstrably covered by the test suite

### Known Suspicions (from Phase 1 recon)
- Stub voters (`orb_breakout` never computed → constant votes dominating signals)
- `tte=0.25` hardcoded greeks (expiry ignored)
- Bar-boundary double-count (first tick of every new bar)
- `shadow_manager` sessions-vs-rows unit mix
- `oi_tracker` subscribed to wrong event shape
- `mode_router` KeyError on unknown status
- Ledger NULL-symbol fills → realized PnL silently zero
- Missing proposal persistence (`db_path=None` in production)
- `position_manager` EOD compares UTC hours against IST config

---

## Phase 3: Cockpit Redesign (After Phase 2)

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
- **Suite**: 959 passed / 0 failed / 0 skipped (current baseline)
- **No file >500 lines** (known violation: `app.py` 504 lines)
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
# SHELTERED MISSION CONTINUATION — Phase 2 + Phase 3 (ShettyXtreme)

You are the Orchestrator of ShettyXtreme (FastAPI + Svelte 5, India-first options intelligence workstation). Phase 1 (Fyers migration) is complete. Read the handoff at `docs/superpowers/handoffs/2026-08-04-phase1-complete.md` for full context.

## Current State
- **Phase 1.0 + Phase 1 complete**: 959 tests passing, Fyers migration done, Dhan removed
- **Version**: 0.12.0
- **Branch**: `fix/terminal-data-pipeline` (or create new branch for Phase 2)

## Next Phases

### Phase 2: Deep Audit
Audit EVERY layer for correctness (logic bugs, missing error paths, stale-data-as-fresh, UTC/IST mixing, event-bus races, silent except:pass, missing tests, dead code). Workflow:
1. Background Explorers per layer → categorized findings report
2. Oracle independently reviews findings
3. Reconcile into ONE audit report (`docs/superpowers/plans/YYYY-MM-DD-audit-findings.md`)
4. Present top 10 findings with options
5. DO NOT auto-fix everything — propose fix plan, ask which tiers to execute
6. Critical fixes (money-path/crash) fixable immediately AFTER asking
7. Every fix gets regression test, suite green at end

Known suspicions to investigate:
- Stub voters dominating signals
- `tte=0.25` hardcoded greeks
- Bar-boundary double-count
- `shadow_manager` sessions-vs-rows unit mix
- `oi_tracker` subscribed to wrong event shape
- `mode_router` KeyError on unknown status
- Ledger NULL-symbol fills → realized PnL silently zero
- Missing proposal persistence
- `position_manager` EOD UTC vs IST

### Phase 3: Cockpit Redesign
FULL cockpit UI redesign (not polish). DESIGN.md binding. Slices S1-S6, approval-gated. Brainstorm IA first (2-3 density options), then Designer-led implementation.

## Working Method (Binding)
1. Phase Zero — Recon + Plan + Questions (dispatch Explorers, produce plan, QUESTION tool to confirm)
2. Cheap specialists do work, heavy models verify (Explorer/Librarian/Fixer → Oracle review)
3. Background parallel tasks with explicit file ownership
4. @council for big judgment calls
5. Ask questions for irreversible/expensive decisions

## Project Rules (Non-Negotiable)
- Test command: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
- Suite: 959 passed / 0 failed / 0 skipped
- No file >500 lines
- No openalgo imports from src/
- Layered architecture law
- OBSERVER-first execution (D10)
- DESIGN.md binding for UI
- Never commit without being asked
- Never paper over a real error

## First Action
Read the handoff doc, then dispatch Phase 2 recon Explorers (one per layer: integration, core, intelligence+research+data+options+learning, knowledge, execution+auth, terminal). Produce audit findings report. Present to me for tier selection.
```

---

## Session End Summary

**Phase 1.0 + Phase 1 delivered:**
- 959 tests passing (baseline 861 → 959, +98 tests)
- Complete Fyers migration (F1-F7)
- Honesty hardening (health, margin, UTC/IST, token lifecycle)
- Zero Dhan residue in `src/`
- Version 0.12.0 aligned
- ADR-008 written, frozen rules amended

**Ready for Phase 2 (deep audit) in next session.**
