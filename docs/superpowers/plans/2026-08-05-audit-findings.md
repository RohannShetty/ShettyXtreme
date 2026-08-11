# Phase 2 Deep Audit — Consolidated Findings

**Date:** 2026-08-05
**Auditors:** 6 Explorers (parallel) + Oracle (independent review)
**Status:** Findings complete, awaiting tier selection

---

## Executive Summary

**6 layers audited, 11 CRITICAL confirmed, 30+ MAJOR, 20+ MINOR.**

Oracle independently verified all CRITICAL findings. No false positives. One reclassification: F-CORE-001 (divergent model pairs) downgraded from CRITICAL to MAJOR — maintenance hazard, not active bug.

**Top 3 money-path bugs:**
1. SL orders transmitted as SL-M (limit price dropped) — real slippage risk
2. LIVE mode activation bypasses D10 typed confirmation — security violation
3. cancel_order routes to paper engine in LIVE — orders cannot be cancelled

---

## Top 10 Findings (Ranked by Impact)

### 1. [F-INT-001] SL orders transmitted as SL-M — **MONEY-PATH CRITICAL**
**File:** `integration/fyers/mappings.py:34-39`, `trading_adapter.py:157-160`
**Impact:** SL orders (stop-loss limit) are sent to Fyers as type 3 (SL-M, stop-loss market). Fyers ignores `limitPrice` on type 3, so after the stop triggers, the order fills at market — potentially far from the intended limit. The test asserts the wrong value.
**Fix:** `ORDER_TYPE_MAP[OrderType.SL] = 4` (SL-L). Fix test.
**Tier:** 1 (immediate)

### 2. [F-EXEC-001 + F-TERM-001] CSRF/D10 bypass — **SECURITY CRITICAL**
**File:** `terminal/api/execution_router.py:142-153, 210-236`
**Impact:** `POST /api/execution/mode?mode=LIVE&confirm=true` activates LIVE mode with a query-param boolean — no typed confirmation, no CSRF token, no Origin check. Any webpage can fire a form post and arm LIVE. Same for `approve_proposal`. D10 safety violated.
**Fix:** Require typed `confirm="LIVE"` in request body; add per-session CSRF token; validate Origin on WS handshake.
**Tier:** 1 (immediate)

### 3. [F-CORE-005 + F-EXEC-002] cancel_order routes to paper in LIVE — **MONEY-PATH CRITICAL**
**File:** `execution/mode_router.py:92-98`
**Impact:** `cancel_order` checks `if self._paper is not None` first. Paper engine is always initialized → LIVE orders route to paper cancel (which doesn't hold them) → returns False. Live orders cannot be cancelled.
**Fix:** Route by mode: LIVE → live.cancel, PAPER → paper.cancel, else reject.
**Tier:** 1 (immediate)

### 4. [F-KNOW-001] Ledger NULL-symbol fills → phantom pairing — **MONEY-PATH CRITICAL**
**File:** `execution/ledger.py:127`, `execution/ledger_recorder.py:52`
**Impact:** Postback fills recorded with `symbol=None`. `pair_fills` buckets NULL under "?", pairing cross-symbol fills (NIFTY buy + BANKNIFTY sell). `per_session_summary` shows fills and notional but `realized_pnl = 0.0`. Analytics scorecard computes negative EV.
**Fix:** Resolve symbol on postbacks (order-id → symbol lookup) before recording; remove "?" catch-all in `pair_fills`.
**Tier:** 1 (immediate)

### 5. [F-INTEL-003] tte=0.25 hardcoded greeks — **MONEY-PATH CRITICAL**
**File:** `terminal/api/intelligence_router.py:134`
**Impact:** Every option contract gets `tte=0.25` years (~91 days). Weekly options (7 DTE) should use tte≈0.027; expiry-day should use tte≈0.001. Theta understated by 15-500×. Greeks are decorative.
**Fix:** Compute `tte = (expiry_datetime - now_IST) / 365.25` with floor.
**Tier:** 2 (this session)

### 6. [F-INTEL-002] Volume double-count at bar boundary — **CORRECTNESS CRITICAL**
**File:** `data/pipeline/bar_builder.py:145-151, 135`
**Impact:** `_create_state` calls `apply_tick(tick)`, then `_on_tick` calls `apply_tick(tick)` again. Volume and tick_count doubled on every new bar. Fyers ticks carry cumulative volume, so the aggregation is wrong in two ways.
**Fix:** Remove `apply_tick` from `_create_state`; fix volume to use delta or cumulative assignment.
**Tier:** 2 (this session)

### 7. [F-INTEL-001] Stub voters dominate signals (42% weight) — **CORRECTNESS CRITICAL**
**File:** `intelligence/voters/orb_voter.py:7-15`, `intelligence/pipeline.py:52-53`
**Impact:** `orb_voter` permanently votes DOWN (direction=-1.0), `iv_rank_voter` permanently votes UP (direction=1.0). Combined weight 2.0 of 4.8 total (41.7%) is constant noise with fixed -0.1 bias. Real signals diluted ~2×.
**Fix:** Delete stubs from pipeline or make them return neutral on missing features.
**Tier:** 2 (this session)

### 8. [F-INT-002] retry-after parses as 0.0 → retry storm — **RELIABILITY CRITICAL**
**File:** `integration/fyers/client.py:234-238`
**Impact:** `_parse_retry_after` defaults to 0.0 when header missing/unparseable. On 429, client sleeps 0 seconds → immediate retry → worsens rate limiting. Fyers bans for a full day when rate limit breached.
**Fix:** Add minimum retry-after floor (1.0s); cap max sleep; raise `FyersRateLimitError` promptly.
**Tier:** 2 (this session)

### 9. [F-KNOW-002] Proposal persistence no-op — **RELIABILITY MAJOR**
**File:** `terminal/api/app.py:358-362`, `execution/execution_engine.py:99-107`
**Impact:** `ExecutionEngine` created without `db_path` → proposals in-memory only. Restart wipes every PENDING/APPROVED proposal. Even when `db_path` is provided, the table stores only (id, status) — no signal/strategy_hint payload — and nothing reads it back.
**Fix:** Pass `db_path` from app.py; serialize full proposal; load on init.
**Tier:** 2 (this session)

### 10. [F-CORE-001] Divergent model pairs — **MAINTAINABILITY MAJOR**
**File:** `core/interfaces/*` vs `core/data_models/*`
**Impact:** Two `Order`, two `Tick`, two `Position` classes. Importing the wrong one compiles but may silently drop data. Currently used consistently (interfaces for adapter contracts, data_models internally), but a maintenance hazard.
**Fix:** Consolidate to one canonical model set.
**Tier:** 3 (next session)

---

## All CRITICAL Findings (11 total)

| ID | Layer | File | Issue | Tier |
|----|-------|------|-------|------|
| F-INT-001 | integration | mappings.py:34 | SL→SL-M transmission | 1 |
| F-INT-002 | integration | client.py:234 | retry-after=0 retry storm | 2 |
| F-CORE-001 | core | interfaces vs data_models | Divergent model pairs | 3 |
| F-CORE-005 | core | mode_router.py:92 | cancel_order→paper in LIVE | 1 |
| F-INTEL-001 | intelligence | orb_voter.py:7 | Stub voters dominate | 2 |
| F-INTEL-002 | intelligence | bar_builder.py:145 | Volume double-count | 2 |
| F-INTEL-003 | intelligence | intelligence_router.py:134 | tte=0.25 hardcoded | 2 |
| F-KNOW-001 | knowledge | ledger.py:127 | NULL-symbol phantom pairing | 1 |
| F-KNOW-002 | knowledge | app.py:358 | Proposal persistence no-op | 2 |
| F-EXEC-001 | execution | execution_router.py:142 | CSRF/D10 bypass | 1 |
| F-TERM-001 | terminal | execution_router.py:142 | CSRF/D10 bypass (dup) | 1 |

---

## All MAJOR Findings (30+)

### Integration (12)
- **F-INT-003** data_socket.py:148 — `_fatal_error` never cleared on reconnect
- **F-INT-004** terminal_init.py:215 — Socket fatal errors invisible to app
- **F-INT-005** data_adapter.py:185 — Live tick OI hardcoded to None
- **F-INT-006** _util.py:171 — Bar volume is per-tick sum of cumulative vol_traded (inflated)
- **F-INT-007** data_adapter.py:266 — subscribe_bars keyed by unresolved symbol
- **F-INT-008** instrument_init.py:23 — Instrument master refreshed only when DB empty
- **F-INT-009** session.py:64 — Session-validity gate no-op for unknown expiry
- **F-INT-010** data_socket.py:232 — `connected` reports True during restart backoff
- **F-INT-011** trading_adapter.py:301 — Account errors degrade to [] for all FyersErrors
- **F-INT-012** symbols.py:320 — Monthly↔weekly round-trip asymmetry

### Core (5)
- **F-CORE-002** event_bus.py:75 — start() loop dies if any subscriber is sync or raises
- **F-CORE-003** paper_trading.py:98 — get_pnl() raises AttributeError on first fill
- **F-CORE-004** config_manager.py:3 — No config validation despite docstring claim

### Intelligence (8)
- **F-INTEL-004** risk_engine.py:127 — RegimeFilter always allows (stub)
- **F-INTEL-005** data_adapter.py:382 — Network failure becomes "empty chain"
- **F-INTEL-006** feature_engine.py:49 — Stale-data-is-fresh at SignalEngine boundary
- **F-INTEL-007** ema.py:20 — NaN/None LTP falls through with no guard
- **F-INTEL-008** options_intel.py:22 — Two IV-rank implementations with different units

### Knowledge (5)
- **F-KNOW-003** position_manager.py:212 — EOD compares UTC hours vs IST config (5h late)
- **F-KNOW-004** oi_tracker.py:78 — Subscribed to wrong event shape (latent)
- **F-KNOW-005** ledger.py:31 — pair_fills drops partial-fill remainders

### Execution+Auth (6)
- **F-AUTH-001** health_monitor.py:108 — Pre-market probe always uses credential-less client
- **F-AUTH-002** auth_router.py:141 — OAuth callback never validates state (CSRF)
- **F-EXEC-003** execution_engine.py:122 — Proposal queue in-memory only (dup of F-KNOW-002)
- **F-EXEC-004** paper_trading.py:151 — Paper MARKET orders fill at 0.0

### Terminal (7)
- **F-TERM-002** ws_manager.py:32 — Double-disconnect race → ValueError
- **F-TERM-003** watchlist_router.py:36 — REST hydration hammering (2N sequential calls)
- **F-TERM-004** projections.py:154 — "risk" WS broadcasts never refresh risk UI
- **F-TERM-005** market_router.py:104 — Adapter transport failures → raw 500
- **F-TERM-006** health_router.py:53 — Weekday before 9:00 reports "opens tomorrow"
- **F-TERM-007** postback_router.py:106 — Unauthenticated legacy /api/postback/dhan

---

## Oracle-Identified Gaps

1. **Fyers WebSocket HSM binary protocol** — No explorer checked the byte-offset parsing. If wrong, all tick data corrupted upstream.
2. **DeepSeek API key handling** — AGENTS.md says "env-only, never logged" but unverified.
3. **EventBus ordering guarantees** — Multiple layers depend on event ordering; unverified under concurrent publishes.
4. **Kill switch race condition** — File-based kill switch could allow orders after kill.
5. **Credential encryption key derivation** — Unverified if machine-bound (HWID) vs static fallback.
6. **WebSocket reconnect state loss** — ws.ts uses fixed 2s delay, no exponential backoff.

---

## Proposed Fix Tiers

### Tier 1 — Immediate (money-path + security + crash)
**Fix now, even before asking:**
- F-INT-001: Fix ORDER_TYPE_MAP — SL→4 (SL-L), not 3
- F-EXEC-001: Add CSRF token or server-side typed confirmation for LIVE mode
- F-CORE-005: Fix cancel_order routing — check mode first, not paper-first
- F-KNOW-001: Reject NULL-symbol fills or require symbol in postback handler

**Estimated effort:** 4 fixes × ~30 min each = ~2 hours + tests

### Tier 2 — This Session (correctness + reliability)
**Fix after asking:**
- F-INTEL-003: Compute tte from actual expiry date
- F-INTEL-002: Fix volume aggregation (delta or cumulative)
- F-INTEL-001: Zero out stub voter weights or remove from registry
- F-INT-002: Add minimum retry-after floor (1.0s)
- F-KNOW-002: Pass db_path to ExecutionEngine in app.py

**Estimated effort:** 5 fixes × ~45 min each = ~4 hours + tests

### Tier 3 — Next Session (maintainability + dead code)
**Defer:**
- F-CORE-001: Consolidate divergent model pairs
- Add regression tests for Tier 1 fixes
- Audit Fyers WebSocket HSM binary parsing (Oracle gap #1)
- Verify DeepSeek API key never logged (Oracle gap #2)
- Fix remaining MAJOR findings (30+ items)

**Estimated effort:** 2-3 days

---

## Verification Gates

After each tier:
```powershell
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider
```

Plus:
- `grep -r "import openalgo\|from openalgo" src/` = zero
- No new file >500 lines
- `graphify update .` after code changes

---

## Next Steps

1. **Present top 10 findings to operator** (this document)
2. **Ask which tiers to execute** (question tool)
3. **Execute Tier 1 immediately** (money-path + security)
4. **Execute Tier 2 after confirmation** (correctness + reliability)
5. **Defer Tier 3 to next session** (maintainability)
6. **Run full test suite after each tier**
7. **Update graphify after code changes**
