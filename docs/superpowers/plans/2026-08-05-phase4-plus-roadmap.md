# Phase 4+ Roadmap — Remaining Work After Phase 3

**Date:** 2026-08-05
**Status:** Compiled from audit findings + Phase 3 slice findings + codebase sweep
**Baseline:** 1012 passed / 0 failed / 0 skipped · v0.12.0 · Phase 3 cockpit redesign committed (`516b60d`)

---

## 0. How This Was Compiled

- `docs/superpowers/plans/2026-08-05-audit-findings.md` — 11 CRITICAL (Tier 1+2 **already fixed** in Phase 2, see `docs/superpowers/handoffs/2026-08-05-phase2-complete.md`) + 30+ MAJOR + 20+ MINOR + 6 Oracle gaps
- Phase 3 slice findings S1, S2, S4, S5, S6 (no S3 file exists — the positions/risk strip slice was folded into S1's `PositionsRiskStrip.svelte` styling; no dedicated S3 findings doc was produced)
- Live codebase sweep: `grep TODO|FIXME|XXX` over `src/` (.py/.svelte/.ts) → **zero matches** (codebase is marker-clean; all remaining work lives in the docs below)
- Current-state spot checks confirmed: `mode_router.cancel_order` mode-routing (F-CORE-005 fixed), `client._parse_retry_after` clamp (F-INT-002 fixed), `RegimeFilter.check` still always-allow (F-INTEL-004 open), `oi=None` hardcoded (F-INT-005 open), legacy postback unauthenticated (F-TERM-007 open), OAuth `state` never validated (F-AUTH-002 open), `ws.ts` fixed 2s reconnect (Oracle #6 open)

---

## 1. Categorization of Audit Findings

### 1.1 Money-path / security — MUST-FIX (5 remaining after Phase 2)

| ID | Issue | File:line | Effort |
|----|-------|-----------|--------|
| F-TERM-007 | Legacy `/api/postback/dhan` unauthenticated — arbitrary payloads mint `ORDER_UPDATED` events | `terminal/api/postback_router.py:106` | 1 h |
| F-AUTH-002 | OAuth callback never validates `state` — login CSRF | `terminal/api/auth_router.py:141` (`fyers_callback`) | 1–2 h |
| F-EXEC-004 | Paper MARKET orders fill at `order.price` (0.0) — poisons paper P&L + learning data | `execution/paper_trading.py:151` (`_fill_order`) | 2 h |
| F-INT-011 | All `FyersError`s degrade to `[]` on account endpoints — masks token expiry & -373 entitlement | `integration/fyers/trading_adapter.py:301` | 2 h |
| F-INT-009 | Session-validity gate no-op for unknown expiry — LIVE not truly gated | `integration/fyers/session.py:64` | 2–3 h |
| Oracle #4 | File-based kill switch race — order could land after kill | audit (kill switch + `mode_router.py`) | 1–2 days |

### 1.2 Correctness / reliability — SHOULD-FIX (21 open)

| ID | Issue | File:line | Effort |
|----|-------|-----------|--------|
| F-INT-003 | `_fatal_error` never cleared on reconnect | `integration/fyers/data_socket.py:148` | 4 h |
| F-INT-004 | Socket fatal errors invisible to app (no `on_error`/`on_close` wiring) | `terminal/api/terminal_init.py:215` | 4 h |
| F-INT-005 | Live tick OI hardcoded `None` | `integration/fyers/data_adapter.py:185` | 4–8 h |
| F-INT-006 | Bar volume = per-tick sum of cumulative `vol_traded` (inflated) | `integration/fyers/_util.py:171` | 3 h |
| F-INT-007 | `subscribe_bars` keyed by unresolved symbol | `integration/fyers/data_adapter.py:266` | 3 h |
| F-INT-008 | Instrument master refreshed only when DB empty | `integration/fyers/instrument_master.py:23` | 4 h |
| F-INT-010 | `connected` reports True during restart backoff | `integration/fyers/data_socket.py:232` | 3 h |
| F-INT-012 | Monthly↔weekly symbol round-trip asymmetry | `integration/fyers/symbols.py:320` | 1 day |
| F-CORE-002 | EventBus `start()` loop dies if a subscriber is sync or raises | `core/event_bus/event_bus.py:75` | 4 h |
| F-CORE-003 | `get_pnl()` raises AttributeError on first fill | `execution/paper_trading.py:98` | 30 min |
| F-CORE-004 | No config validation despite docstring claim | `core/config/config_manager.py:3` | 4 h |
| F-INTEL-004 | `RegimeFilter` always allows (stub) — verified still open | `intelligence/risk/risk_engine.py:127` | 3 h |
| F-INTEL-005 | Network failure becomes "empty chain" | `integration/fyers/data_adapter.py:382` | 4 h |
| F-INTEL-006 | Stale data treated as fresh at SignalEngine boundary | `intelligence/feature_engine.py:49` | 4 h |
| F-INTEL-007 | NaN/None LTP falls through with no guard | `intelligence/indicators/ema.py:20` | 30 min |
| F-INTEL-008 | Two IV-rank implementations with different units | `intelligence/options/options_intel.py:22` | 4 h |
| F-KNOW-003 | EOD compares UTC hours vs IST config (5 h late) | `execution/position_manager.py:212` | 2 h |
| F-KNOW-004 | OI tracker subscribed to wrong event shape (latent) | `options/oi_tracker.py:78` | 2 h |
| F-KNOW-005 | `pair_fills` drops partial-fill remainders (not re-queued) | `execution/ledger.py:31` | 3 h |
| F-TERM-002 | ws_manager double-disconnect race → ValueError | `terminal/api/ws_manager.py:32` | 2 h |
| F-TERM-005 | Adapter transport failures → raw 500 | `terminal/api/market_router.py:104` | 2 h |
| F-TERM-006 | Weekday before 9:15 reports "opens tomorrow" (verified) | `terminal/api/health_router.py:53` | 30 min |
| F-AUTH-001 | Pre-market probe always uses credential-less client | `auth/health_monitor.py:108` | 3 h |
| Oracle #3 | EventBus ordering guarantees unverified under concurrent publishes | `core/event_bus/` | 1 day |
| Oracle #5 | Credential encryption key derivation (HWID vs static) unverified | `auth/credential_store.py` | 2 h |

### 1.3 Performance / UX — NICE-TO-HAVE (4)

| ID | Issue | File:line | Effort |
|----|-------|-----------|--------|
| F-TERM-003 | Watchlist REST hydration hammering (2N sequential Fyers calls) | `terminal/api/watchlist_router.py:36` | 1–2 days |
| F-TERM-004 | "risk" WS broadcasts never refresh risk UI | `terminal/projections.py:154` | 1 day |
| Oracle #6 | WS reconnect fixed 2s, no exponential backoff (verified `RECONNECT_MS = 2000`) | `terminal/web/src/lib/ws.ts:18` | 2 h |
| — | `api.ts` fetch has no timeout / AbortController | `terminal/web/src/lib/api.ts:28,61` | 2 h |

### 1.4 Architecture / maintainability — TECH DEBT

| ID | Issue | File:line | Effort |
|----|-------|-----------|--------|
| F-CORE-001 | Divergent model pairs (interfaces vs data_models) — deferred from Phase 2 | `core/interfaces/*` vs `core/data_models/*` | 2–3 days |
| — | `core/` imports `yaml` (known layering violation, slated) | `core/config/config_manager.py:3` | 3 h |
| — | Version drift — `__init__.py` stale at 0.6.0 vs 0.12.0 elsewhere | `src/shettyxtreme/__init__.py` + 4 others | 30 min |
| — | HSM index tick timestamp uses `datetime.now(UTC)` (SDK feed lacks `last_traded_time`) | `integration/fyers/data_adapter.py` | documented |
| — | `~/.shettyxtreme_mode` LIVE persistence can break tests | `tests/**/conftest.py` | 30 min |

---

## 2. Phase 3 (S1–S6) Follow-ups Extracted

### 2.1 Backend follow-ups
1. **Tick payload lacks option identifiers** (S2 §2.1, the single biggest lever): `WatchlistProjection.on_market_data` broadcasts only `{symbol, ltp, change_pct, volume}` (`terminal/projections.py:55` — verified). Extending to `strike`/`option_type`/`iv`/`oi` lets ChainGrid update fully on the wire and kills the 15s IV/OI poll. Blocked on `Tick`→dict serialization + per-contract subscription scope. **→ Phase 6**
2. **Scorecard should carry `current_regime`** (S5 §3.3): AnalyticsPanel makes a second REST call to `/api/intelligence/regime` just to accent a bar. Add to `ScorecardResponse` (`terminal/api/analytics_router.py` + `analytics_models.py`). **→ Phase 5/6 (2 h)**
3. **`chain_snapshot` / `options_posture` render `[UNSOURCED]`** (v0.10 known) — `options_summary` intentionally None; no runtime options-posture source. **→ Phase 7**

### 2.2 Frontend follow-ups
1. **`selectedSymbol` needs an exchange** (S1 §3.1 + S2 §3.2 confirmed): `lib/selection.ts` is a bare string (verified, 3 lines). Extend to `{symbol, exchange}` — removes the Header REST-derived map + ChainGrid `NSE_FNO` misroute risk. **→ Phase 6**
2. **App.svelte `:global(.drawer)` override is now vestigial** (S6 §4.1): S6 deleted LogDrawer's media query, so S1's `!important` block matches but does nothing. Delete. **→ Phase 4 (30 min)**
3. **`KnowledgeHitList.svelte` is unused** (S6 §4.2, verified on disk at `components/knowledge/KnowledgeHitList.svelte`) — rendered inline in KnowledgePanel since S6. Delete + consolidate row styles. **→ Phase 4**
4. **LIVE banner overlaps workspace top ~28px** (S4 §4.1): needs a 4th grid row in `App.svelte` (`grid-template-rows` currently 3 rows); `--header-bottom` CSS var for the measurement coupling (S4 §4.2). **→ Phase 6**
5. **Tab remount churn** (S5 §4.5 / current-ui-analysis #2): scanner/hints/analytics remount + re-fetch on every tab switch. Keep-alive in App.svelte. **→ Phase 6**
6. **ChainGrid `min-width: 720px`** hard limit (S1 §3.4): container-query or internal scroll to remove the last hard min-width. **→ Phase 6**
7. **`TableRow` doesn't forward rest attributes** (S2 §3.3): `data-state`/`onkeydown`/`aria-*` silently dropped; `{...rest}` on `<tr>` is a small high-leverage primitive fix. **→ Phase 5/6**
8. **Native `<select>`s remain in ResearchPanel filters** (S6 §4.6): custom dropdown is part of the component-migration backlog. **→ Phase 7**
9. **a11y warnings**: `ChainGrid .table-wrap` / `Watchlist .list` `div onkeydown` without role (S6 §4.9). **→ Phase 7**
10. **Header <1000px clips** (S1 §3.5): two-row header or chip-density pass if sub-1024 support matters. **→ Phase 7**
11. **`Ctrl+R`/`Ctrl+M`/`Ctrl+F` suppress browser defaults** (S1 §3.3, S6 §2.4): deliberate workstation shortcuts — document for the operator. **→ Phase 7 (docs)**

---

## 3. Phase 4 — Quick Wins (1–2 days, high impact, low risk)

All are single-file, self-contained, low-blast-radius fixes. **Fully parallelizable across 4 lanes (disjoint files).**

| # | Item | File | Lane | Effort |
|---|------|------|------|--------|
| 1 | F-TERM-007: auth-gate legacy postback | `postback_router.py` | A-exec | 1 h |
| 2 | F-AUTH-002: validate OAuth `state` (persist + compare) | `auth_router.py` | A-exec | 1–2 h |
| 3 | F-EXEC-004: paper MARKET fill at last LTP, not 0.0 | `paper_trading.py` | A-exec | 2 h |
| 4 | F-CORE-003: guard `get_pnl()` first-fill AttributeError | `paper_trading.py` | A-exec | 30 min |
| 5 | F-INT-011: classify FyersErrors on account endpoints | `trading_adapter.py` | B-int | 2 h |
| 6 | F-INT-009: honest session-validity gate for unknown expiry | `session.py` (+`mode_router.py` touch) | B-int | 2–3 h |
| 7 | F-TERM-006: pre-9:15 weekday → "opens at 09:15 today" | `health_router.py` | A-exec | 30 min |
| 8 | F-INTEL-007: EMA NaN/None guard | `intelligence/indicators/ema.py` | C-intel | 30 min |
| 9 | F-INTEL-004: real `RegimeFilter` (or honest neutral) | `intelligence/risk/risk_engine.py` | C-intel | 3 h |
| 10 | F-KNOW-005: re-queue partial-fill remainders in `pair_fills` | `execution/ledger.py` | A-exec | 3 h |
| 11 | Oracle #6: WS exponential backoff + jitter | `web/src/lib/ws.ts` | D-front | 2 h |
| 12 | Fetch timeout / AbortController in `api.ts` | `web/src/lib/api.ts` | D-front | 2 h |
| 13 | Delete `KnowledgeHitList.svelte` + App.svelte vestigial override | `web/src/components/` | D-front | 30 min |
| 14 | Version drift alignment (5 files → 0.13.0) | root + app.py + pyproject + package.json + CHANGELOG | A-exec | 30 min |
| 15 | conftest: reset `~/.shettyxtreme_mode` to OBSERVER | `tests/` | E-test | 30 min |

**Verification gate:** full suite green + `npm run check` 0 errors + `npm run build` + `graphify update .`

---

## 4. Phase 5 — Medium Effort (3–5 days, correctness / reliability)

**Parallel lanes (disjoint ownership):**

| Lane | Files | Work |
|------|-------|------|
| **A — Data socket lifecycle** | `integration/fyers/data_socket.py`, `terminal/api/terminal_init.py` | F-INT-003 (clear `_fatal_error` on reconnect), F-INT-004 (wire `on_error`/`on_close` to app health), F-INT-010 (honest `connected` during backoff). 1–1.5 days |
| **B — Tick/bar correctness** | `integration/fyers/data_adapter.py`, `_util.py` | F-INT-005 (live OI from SDK field), F-INT-006 (delta volume), F-INT-007 (resolve symbol before subscribe). 1 day |
| **C — Symbols + master** | `integration/fyers/symbols.py`, `instrument_master.py` | F-INT-012 (round-trip), F-INT-008 (staleness refresh). 1 day |
| **D — EventBus + config** | `core/event_bus/event_bus.py`, `core/config/config_manager.py` | F-CORE-002 (sync-subscriber safety via `inspect.iscoroutinefunction`), F-CORE-004 (schema validation), Oracle #3 (ordering test). 1 day |
| **E — Intelligence** | `intelligence/feature_engine.py`, `options/oi_tracker.py`, `intelligence/options/options_intel.py`, `execution/position_manager.py` | F-INTEL-006 (staleness gate), F-KNOW-004 (event shape), F-INTEL-008 (unify IV-rank), F-KNOW-003 (IST EOD). 1 day |
| **F — Terminal/execution** | `terminal/api/ws_manager.py`, `market_router.py`, `auth/health_monitor.py`, `intelligence/risk/risk_engine.py` (if not in P4) | F-TERM-002 (double-disconnect), F-TERM-005 (structured 5xx), F-AUTH-001 (credentialed probe), Oracle #5 (key derivation audit). 1 day |

**Sequencing note:** Lane A first — socket health is a prerequisite for trusting any live-data fix (Phase-1.0 "honesty first" principle). Lanes B–F can run in parallel after A's design is set.

**Verification gate:** full suite green + per-fix regression tests (Phase-2 convention: every executed fix gets one) + `graphify update .`

---

## 5. Phase 6 — Deep Work (1–2 weeks, architecture / perf)

| # | Item | Files | Effort | Depends on |
|---|------|-------|--------|------------|
| 1 | **F-CORE-001: consolidate divergent model pairs** (one canonical Order/Tick/Position) | `core/interfaces/*`, `core/data_models/*` + all importers | 2–3 days | — (run first; everything touches it) |
| 2 | **Live chain on the wire**: extend tick broadcast with `strike`/`option_type`/`iv`/`oi`; per-contract subscription scope | `terminal/projections.py`, `integration/fyers/data_adapter.py`, `web/.../ChainGrid.svelte` | 1.5 days | Phase 5 Lane B (OI fix) |
| 3 | **F-TERM-003: watchlist hydration batching** (parallel / `_quotes` ≤50-symbol grouping) | `terminal/api/watchlist_router.py`, `data_adapter.py` | 1–2 days | — |
| 4 | **Tab keep-alive** (remount churn) | `web/src/App.svelte` | 1 day | — |
| 5 | **ChainGrid container-query** (kill 720px min-width) | `web/.../ChainGrid.svelte` | 1 day | — |
| 6 | **`TableRow` rest-forwarding** + related primitive fixes | `web/src/lib/components/ui/table/table-row.svelte` | 4 h | — |
| 7 | **`selection.ts` → `{symbol, exchange}`** + Header/ChainGrid consumers | `web/src/lib/selection.ts`, `Header.svelte`, `ChainGrid.svelte` | 1 day | — |
| 8 | **LIVE banner 4th grid row** + `--header-bottom` CSS var | `web/src/App.svelte`, `ModeSwitcher.svelte` | 4 h | Phase 6 #4 (same file — do together) |
| 9 | **Oracle #4: kill switch race audit + fix** | `execution/`, kill-switch plumbing | 1–2 days | — |
| 10 | **Component migration wave 1** (DESIGN.md-skinned): `scroll-area`, `separator`, `select`/`dropdown-menu`, `skeleton`, `sonner`, `kbd` | `web/src/lib/components/ui/` | 3–5 days | — |
| 11 | **Scorecard carries `current_regime`** | `analytics_router.py`, `analytics_models.py`, `AnalyticsPanel.svelte` | 2 h | — |

**Parallelization:** items 1, 9 (backend/architecture) ∥ 2–3 (integration) ∥ 4–8 (frontend, but 4+8 share App.svelte — same writer) ∥ 10 (component lib, touches only `ui/`) ∥ 11 (tiny, anywhere).

---

## 6. Phase 7 — Nice-to-have (UX polish, missing features)

| # | Item | Notes |
|---|------|-------|
| 1 | SettingsView real settings form (risk limits, theme, scheduler config) | S6 §4.4 — backend has zero `/api/settings/*` endpoints; build form + endpoints together |
| 2 | Command palette (⌘K symbol search) — `command` port | design-research §4 tier 2 |
| 3 | Split-pane resizable + persistence | ARCHITECTURE_V2 §15; `resizable` port |
| 4 | Custom scrollbars | `scroll-area` port |
| 5 | Custom dropdown for ResearchPanel native selects | S6 §4.6 |
| 6 | Badge `conviction-*` variants + resolve micro-vs-mono face tension | S5 §4.3/§4.4 — align DESIGN.md §4 or mission doc |
| 7 | Header <1000px two-row fallback | S1 §3.5 |
| 8 | Ticker strip / regime-IV-PCR at-a-glance chrome | current-ui-analysis "Missing" list |
| 9 | Knowledge STALE semantics → panel-level "last sync" | S6 §4.5 |
| 10 | a11y `onkeydown` role warnings | S6 §4.9 |
| 11 | Document Ctrl+R/Ctrl+M/Ctrl+F workstation shortcuts | S1 §3.3 |
| 12 | `options_posture` live source (currently honest `[UNSOURCED]`) | v0.10 known |
| 13 | Re-evaluate DECIDED-DEFER: multi-broker, backtest depth, critic pass (waits for order intents), live `/optionchain` fixture (needs live creds) | roadmap §17 / wayfinder map |
| 14 | `uipro update` + design-system generator cross-check vs DESIGN.md | design-research §1.4 |

---

## 7. Parallelization Summary + File-Ownership Matrix

| Phase | Parallel lanes | Conflict risk | Gate |
|-------|---------------|---------------|------|
| 4 | A-exec / B-int / C-intel / D-front / E-test | none — all disjoint | suite + svelte-check |
| 5 | A socket / B tick / C symbols / D bus+config / E intel / F terminal | none — disjoint | suite + per-fix tests |
| 6 | backend (1,9) ∥ integration (2,3) ∥ frontend (4–8: 4+8 same writer) ∥ ui-lib (10) ∥ tiny (11) | App.svelte serialized (4→8) | suite + svelte-check + build |
| 7 | per-item | none | svelte-check per change |

**Dependencies graph:**
```
Phase 4 (all)  →  Phase 5 Lane A (socket honesty)  →  Phase 6 #2 (live chain)
Phase 5 Lane B  ──────────────────────────────────┘
Phase 6 #1 (model consolidation)  ←  must precede any broad refactor touching interfaces
Phase 6 #4 → #8 (App.svelte serialized)
```

## 8. Verification Gates (every phase exit)

```powershell
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase4plus -p no:cacheprovider
```
Plus:
- `grep -r "import openalgo\|from openalgo" src/` = zero
- No new file > 1000 lines (gate raised 2026-08-05, `389a286`)
- `npm run check` 0 errors before `npm run build` (frontend phases)
- Layering greps (`core/` no external imports; `knowledge/` imports core only)
- `graphify update .` after every code-touching phase

## 9. Effort Totals

| Phase | Effort | Nature |
|-------|--------|--------|
| 4 | 1–2 days | security + quick correctness (5 money-path items front-loaded) |
| 5 | 3–5 days | reliability across all 6 layers |
| 6 | 1–2 weeks | architecture (model consolidation) + live-chain + perf |
| 7 | ongoing | UX polish + deferred-feature re-evaluation |
