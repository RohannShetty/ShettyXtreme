# Phase 7 Reconnaissance — Current State & Execution Lanes

**Date:** 2026-08-05
**Status:** Compiled from live codebase inspection (read-only) + `npm run check` + grep sweeps
**Baseline:** Phase 6 complete — 1187 passed / 0 failed / 0 skipped · v0.13.0
**Input roadmap:** `docs/superpowers/plans/2026-08-05-phase4-plus-roadmap.md` §6 (items 1–14)

---

## 0. Headline findings (read this first)

1. **Two Phase-7 roadmap items are ALREADY DONE and need only a verify gate:**
   - **#5 Custom dropdown for ResearchPanel** — ResearchPanel already uses the shadcn `Select` port (`ResearchPanel.svelte:289-309`, status + lens filters). `grep "<select"` across `web/src` = **zero matches** (also `Watchlist.svelte:203`, `ChainGrid.svelte:322` use the custom Select). The S6 §4.6 note is stale.
   - **#10 a11y `onkeydown` role warnings** — `npm run check` reports **0 errors AND 0 warnings** (svelte.config.js has no `onwarn` suppression, so a11y warnings would surface). S6 §4.9 items already fixed: `Watchlist.svelte:231-239` rows carry `role="button" tabindex="0"`, `ChainGrid.svelte:401-409` strike cells carry `role="gridcell" tabindex="0"`, `HintsPanel.svelte:84-97` card carries `role="button"`, Research/Knowledge listboxes carry `role="listbox"`, remaining `onkeydown`s (ModeSwitcher:177, KillSwitch:116, Watchlist:201, KnowledgePanel:280) are on **native inputs** (no role needed).
2. **`command` palette is feasible with ZERO new dependencies** — bits-ui 2.18.1 already exports `Command` + `computeCommandScore` (verified in `node_modules/bits-ui/dist/index.d.ts`). No `command/` dir in `ui/` yet — pure port work.
3. **`resizable` needs a dependency decision** — shadcn-svelte's resizable imports from `svelte-panels`, which is **NOT installed** (`Test-Path` = False). Either add the dep or hand-roll with pointer events. This is the only Phase-7 item with a dependency question.
4. **`settings_router.py` is a 12-line empty stub** (prefix only, zero endpoints). Every "settings" the form should expose (loss_limit, theme, scheduler) is currently hardcoded or env-gated — this item is greenfield backend + frontend.
5. **`options_posture` is NOT a stub anymore** — it's live-backed by the chain cache + IVRank/OITracker (`research_source.py:134-196`), but shows `[UNSOURCED]` until a chain has been fetched once. The gap is "chain cache is write-only on `/api/intelligence/options`".
6. **All four DECIDED-DEFER items remain correctly deferred** — no trigger has fired (order intents don't exist; no second-broker need; no comparison surface).

---

## 1. Per-item findings

### 1.1 Settings form (roadmap #1) — **GREENFIELD, biggest item**
**Frontend state** — `src/shettyxtreme/terminal/web/src/components/SettingsView.svelte` (184 lines): auth/credentials-only. Cards show broker / client / token VALID-EXPIRED-NOT SET / token expiry + Re-auth + Logout buttons (lines 92-116); Enter-on-surface triggers reauth (22-32). No risk, theme, or scheduler sections.
**Backend** — `src/shettyxtreme/terminal/api/settings_router.py` (12 lines): `router = APIRouter(prefix="/api/settings", tags=["settings"])` — **zero endpoints**; docstring says "retained so the composition root keeps a stable include". Included in `app.py:515`; `/settings` page redirect at `app.py:503-505`.
**What exists to expose:**
| Setting | Current state | Where |
|---|---|---|
| `loss_limit` (risk) | Hardcoded `-5000.0` in 4 places | `intelligence/risk/risk_engine.py:75`, `intelligence/risk/bus_bridge.py:10` (`_DEFAULT_LOSS_LIMIT`), `terminal/projections.py:157`, default in `terminal/api/execution_router.py:198` |
| `max_positions` | Hardcoded `5` | `bus_bridge.py:11`, `projections.py:159` |
| Theme | Frontend-only, `localStorage["sx-theme"]` | `web/src/lib/theme.ts` (whole file); `initTheme()` in `main.ts:7`; toggle button `Header.svelte:293-310` |
| Scheduler (research) | Env-gated at startup; no runtime mutation | `app.py:231-260` (`RESEARCH_SCHEDULE_ENABLED=1`, `RESEARCH_SCHEDULE_INTERVAL_MINUTES`, `_LENSES`, `_TOOLS`, requires `DEEPSEEK_API_KEY`); `research/scheduler.py` (whole file); status GET-only at `research_router.py:137-150` |
| Config file | Minimal 7 lines | `configs/default.yaml` |

**Build plan shape:** new `GET/PUT /api/settings/*` (risk + scheduler + theme) + a tiny persistence layer (config write vs sqlite KV — decide in spec; `core/config/config_manager.py` exists and already loads yaml, but note the known `core/`→yaml layering violation at `config_manager.py:3`). `GET /api/research/scheduler` already returns everything the UI needs to render scheduler state (`research_router.py:142-150`).

### 1.2 Command palette ⌘K (roadmap #2) — feasible now, no new dep
- **No existing palette code** anywhere in `web/src`.
- **Component gap:** `ui/` has NO `command/` dir (glob of `ui/**/*.svelte` confirms). But bits-ui 2.18.1 exports `Command` + `computeCommandScore` → port shadcn-svelte `command` set (root, input, list, empty, group, item, separator, dialog) with DESIGN tokens.
- **Searchable symbols/actions:**
  - Center tabs: `activeTab` store — `web/src/lib/activeTab.ts:3` (`"chain"|"scanner"|"hints"|"analytics"`)
  - Routes: `#/settings`, `#/setup` (App.svelte:154-157 hash router)
  - Commands: toggle right dock (Ctrl+R, App.svelte:47-59), toggle theme (theme.ts), cycle mode (Ctrl+M, ModeSwitcher.svelte:50), kill-switch view (Ctrl+Shift+K, KillSwitch.svelte:34)
  - Symbols: watchlist items (`GET /api/watchlist` → `watchlist_router.py:144`) and — for full instrument search — the Fyers `instrument_master.search()` (`instrument_master.py:434-444`) already exists **but has no REST endpoint**; palette v1 can scope to watchlist + actions, v2 adds an `/api/instruments/search` endpoint.
- **Integration points:** App.svelte window `keydown` (add `Ctrl+K`, keep the existing input-guard pattern from KnowledgePanel.svelte:86-95), Header search affordance button, selection store `web/src/lib/selection.ts` (already `{symbol, exchange}` from Phase 6).

### 1.3 Split-pane resizable (roadmap #3) — needs a dependency decision
- **Current layout is grid-based, not resizable:** `App.svelte:190-196` — `.workspace { display:grid; grid-template-columns: 260px minmax(0,1fr) 320px }`. `.rail` `min-width:260px` (197-204), `.right-col` `min-width:320px` (235-242). Below 1440px the right-col becomes a fixed overlay drawer (`App.svelte:315-350`).
- **Split boundaries:** rail↔center (260px) and center↔right-col (320px). Only the two inner boundaries are resizable candidates; the drawer breakpoint (1440px) is a hard constraint.
- **Component gap:** NO `resizable/` in `ui/`, and `svelte-panels` **not installed** (neither is `cmdk`). shadcn-svelte resizable = `Panel/PanelGroup/PanelResizeHandle` from svelte-panels → **either add `svelte-panels` or hand-roll** (pointer-events handle, ~150 lines). ARCHITECTURE_V2 §15 mandates "min panel widths, resizable split panes" (`15-design-system-terminal-ux.md:15,57`) and DESIGN.md §8 density rules apply. Persistence: `localStorage` widths.

### 1.4 Custom scrollbars (roadmap #4) — component exists, rollout only
- **`scroll-area` port EXISTS** (`ui/scroll-area/scroll-area.svelte` + `scroll-area-scrollbar.svelte` + `index.ts`), DESIGN-skinned (thumb `bg-hairline-strong` radius 5px). Already consumed by **ChainGrid** (`orientation="both"`, `ChainGrid.svelte:362`) and **Watchlist** (`Watchlist.svelte:228`) — pattern proven.
- **Native-scrollbar survivors (9 spots):**
  - `App.svelte:218` `.tab-panel overflow-x:auto`
  - `App.svelte:334` right-col drawer overlay `overflow-y:auto`
  - `AnalyticsPanel.svelte:210`, `KnowledgePanel.svelte:427`, `LogDrawer.svelte:158`, `ProposalQueue.svelte:442`, `PositionsRiskStrip.svelte:197`, `ResearchPanel.svelte:488`, `ScannerPanel.svelte:333` (all `overflow-y:auto`)
- **Migration effort:** LOW per spot — wrap scrollable region in `<ScrollArea>`; the two existing consumers are the template. Note ChainGrid pre-paid this in Phase 6 (`phase6-lane-e-findings.md:89-90`).

### 1.5 ResearchPanel dropdown (roadmap #5) — **DONE, verify only** (see §0.1)

### 1.6 Badge conviction variants (roadmap #6) — small, tidy-up
- **Current variants** — `ui/badge/index.ts:14-23`: `default, outline, secondary, success, warning, danger, info`. Base = `font-mono text-[10px] uppercase tracking-wide` (mono face, DESIGN §4 chip).
- **Conviction levels** — `ProposalQueue.svelte:84-89`: EXTREME ≥0.75, HIGH ≥0.5, MEDIUM ≥0.25, else LOW. But the rendering does **not** use named variants: `convictionClass()` (`ProposalQueue.svelte:91-102`) slaps raw Tailwind utilities on the Badge (`border-hairline-strong bg-row-selected text-ink` / `border-accent-disabled text-accent` / `border-warning text-warning` / `border-hairline-strong text-muted-foreground`). `ScannerPanel.svelte:273` has its own parallel `.badge-conv` class (styled at :397).
- **Micro-vs-mono tension** (S5 §4.3/§4.4): badge base forces mono+uppercase, but several sites render status/labels inside `micro` (Inter 10px) contexts (e.g., `KnowledgePanel.svelte:321-322` chip + `.micro` src — though that one uses a custom `.chip` class, not Badge). Resolution: add `conviction-{low,medium,high,extreme}` variants to `badgeVariants` (or a `face` prop) and consolidate ProposalQueue/ScannerPanel onto them.

### 1.7 Header <1000px two-row fallback (roadmap #7) — coupled to App.svelte var
- **Current behavior** — `Header.svelte:332-342`: `.head` is fixed `height:44px; overflow:hidden`. Progressive compaction cascade: `.ltp-chg` hidden ≤1360px (`:579-583`), `.title` hidden ≤1240px (`:584-588`), `.session-time` hidden ≤1080px (`:589-597`). **Below ~1000px the row clips** — brand, ltp-hero (28px number), ModeSwitcher, KillSwitch, pip, cred-chip, theme + drawer buttons all fight for one 44px row.
- **Two-row strategy:** `@media (max-width:1000px)` → `.head { height:auto; flex-wrap:wrap }`; row 1 = brand + mode + kill + pip + toggles; row 2 = ltp-hero + session + cred-chip. `ltp-value` (28px, `Header.svelte:401-407`) can drop to ~18px on row 2.
- **⚠ Coupling:** App.svelte hardcodes `--header-bottom: 52px` (`App.svelte:174-178`, comment documents the measurement coupling) and the LIVE banner slot (`App.svelte:185-187`, ModeSwitcher `.live-banner` reads the var). **A taller two-row header REQUIRES bumping that var in the same change** — do Header + App.svelte together (serialized with §1.3/§1.8 which also touch App.svelte layout).

### 1.8 Ticker strip / regime-IV-PCR chrome (roadmap #8) — data exists, UI missing
- **No at-a-glance regime/IV/PCR strip exists.** Regime appears only in AnalyticsPanel by-regime table + ScannerPanel `.badge-regime` (which is gap/cluster *type*, not market regime). ChainGrid shows per-row IV only.
- **Data sources (all live, backend-side):**
  - Regime: `IntelligenceProjection.get_regime()` (`projections.py:299-303`) → `GET /api/intelligence/regime` (`intelligence_router.py:248`) **and WS topic `regime` already broadcast** (`projections.py:267`).
  - Signal: `GET /api/intelligence/signal` (`:262`) + WS `signal` broadcast (`:281-285`).
  - IV/PCR/OI posture: `render_options_posture()` (`terminal/api/research_source.py:13-74`) computes PCR, CE/PE max-OI pins, IV level (HIGH≥30 / LOW<20 / NORMAL) from the chain cache `app.state.options_chain`, populated by `GET /api/intelligence/options` (`intelligence_router.py:319-322`). IVRankCalculator + OITracker feed `options_summary()` (`research_source.py:145-183`).
- **Placement options:** (a) second header row when ≥1000px (ties into §1.7 work), or (b) a thin strip in its own grid row — the 4th-row mechanism already exists for the LIVE banner (`App.svelte:185-187`). Regime can be pushed over WS (zero polling); IV/PCR needs either a WS projection or a 15s poll mirroring ChainGrid's cadence.

### 1.9 Knowledge STALE semantics (roadmap #9) — add "last sync"
- **Current staleness** — `KnowledgePanel.svelte:46-57,326-328`: per-hit STALE chip when `created_at` > 60 min old (per-doc age, not sync age). Header counts `{docs} docs · {prop} prop · {act} act` (`:263`).
- **"Last sync" does not exist.** `/api/knowledge/status` returns only counts from `KnowledgeStore.counts()` (`knowledge_router.py:123-130` → `knowledge/store.py:246-255`). `KnowledgeSyncResponse` (`knowledge_router.py:153-157`) carries ingested/skipped counts but **no timestamp**. The sync handler (`:133-157`) is where a `synced_at` would be recorded. Docs table has `created_at/activated_at` only — no sync meta.
- **Fix:** add `last_sync_at`/`last_sync_result` (meta table or `MAX(created_at)` is WRONG — created_at is doc birth, not sync time) → surface in `KnowledgeStatusResponse` (`api.ts` model) → panel header "Last sync: HH:MM". ~0.5 day.

### 1.10 a11y onkeydown warnings (roadmap #10) — **DONE, verify only** (see §0.1). Keep `npm run check` as the gate.

### 1.11 Document shortcuts (roadmap #11) — help modal + manual
- **Defined shortcuts:** Ctrl+R = right dock (`App.svelte:47-59`), Ctrl+M = cycle mode (`ModeSwitcher.svelte:50`), Ctrl+F = focus knowledge search (`KnowledgePanel.svelte:86-95`), Ctrl+Shift+K = kill switch (`KillSwitch.svelte:34`). All window-level, all `preventDefault()` (suppress browser defaults while cockpit mounted).
- **Documented today:** `docs/OPERATOR_MANUAL.md:65,89` mentions only Ctrl+Shift+K. **No help modal exists.**
- **Where docs go:** (a) a "Shortcuts" dialog built on the existing `Dialog` port (`ui/dialog/`, used by ModeSwitcher), triggered from the Header; (b) `OPERATOR_MANUAL.md` section; (c) the `Kbd` component (`ui/kbd`, used once at `App.svelte:133`) reused for palette footer hints when §1.2 lands.

### 1.12 `options_posture` live source (roadmap #12) — live-backed, one gap
- **Not a stub.** `research/tools.py:115` defines the tool; `ProjectionDataSource.options_summary()` (`research_source.py:134-196`) is the live source: (1) `app.state.iv_rank_calculator` (real rank), (2) `app.state.oi_tracker` (PCR + buildup alerts), (3) `app.state.options_chain` cache via `render_options_posture` (`:13-74`).
- **The gap:** the chain cache is **write-only** — populated only as a side-effect of `GET /api/intelligence/options` (`intelligence_router.py:319-322`). Until that's called once, `[UNSOURCED]` is honest-by-construction (`research_source.py:140-142`).
- **Fix options:** (a) prime the chain cache at startup / on data-adapter connect; (b) new `OptionsProjection` subscribing to chain snapshots + WS broadcast (feeds §1.8 too); (c) wire IVRankCalculator/OITracker onto app.state (currently only referenced via `getattr` in research_source — `app.py` does not construct them). Related: F-INTEL-008 (two IV-rank implementations, `options_intel.py:22`) is a Phase-5 item that would unify the rank path.

### 1.13 DECIDED-DEFER re-evaluation (roadmap #13) — **NO CHANGE, triggers un-fired**
| Deferred item | Trigger (recorded) | Status today | Verdict |
|---|---|---|---|
| Multi-broker | concrete broker need / missing Fyers capability (`issues/07-multibroker-decision.md:16`) | Fyers migration complete; no second-broker need | **Keep deferred** |
| Backtest depth | comparison-surface need (`issues/08-backtest-depth-scope.md:16`) | Walkforward stays; no comparison surface | **Keep deferred** |
| Critic pass | waits for **order intents** to gate (`map.md:51`, roadmap §17) | `grep order_intent\|intent` in `src/` = **nothing** — order intents don't exist | **Keep deferred** |
| Live `/optionchain` fixture | needs live credentials (`map.md:52`) | Cannot verify live Data-API creds from code; env-gated | **Keep deferred** |

---

## 2. Dependency graph (what must come first)

```
§1.5 verify + §1.10 verify (gates only)         → runs FIRST, unblocks lane budget
§1.6 badge variants          ─┐
§1.4 scroll-area rollout     ─┤  Wave 1, disjoint files
§1.11 shortcut docs          ─┘
                                 │
§1.2 command palette  ← needs Header.svelte button (serialize Header with §1.7/§1.8)
§1.7 header two-row   ← MUST update App.svelte `--header-bottom` (174-178) in same change
§1.8 ticker strip     ← placement decision depends on §1.7 row layout; data via existing WS/REST
§1.3 resizable        ← App.svelte grid + media query; serialize with §1.7/§1.8 (same file)
                                 │
§1.1 settings form    ← backend-first (risk plumbing touches risk_engine/bus_bridge/projections/execution_router defaults)
§1.9 knowledge sync   ← backend-only (store + router + panel header)
§1.12 options_posture ← backend-only (chain-cache priming / projection); feeds §1.8 later
                                 │
§1.13 re-eval         ← decision doc only; fully parallel, zero code
```

**Hard ordering:** nothing blocks nothing except (a) all three App.svelte-layout items (§1.3/§1.7/§1.8) must be **one writer, sequential**; (b) §1.2/§1.7/§1.8 all touch `Header.svelte` → serialize Header edits; (c) §1.8's IV/PCR panel benefits from §1.12's projection but is not blocked by it.

## 3. Parallelization opportunities

| Lane | Items | Conflict surface | Notes |
|---|---|---|---|
| **A — verify/gates** | §1.5, §1.10 | none | Zero code; just run check + grep; frees the roadmap |
| **B — ui-lib tidy** | §1.6 badge, §1.4 scroll-area, §1.11 docs | `ui/badge/` only; docs touch `OPERATOR_MANUAL.md` | Fully parallel (disjoint files) |
| **C — frontend chrome** | §1.2 palette, §1.7 header, §1.8 strip, §1.3 resizable | **App.svelte + Header.svelte are shared by all four** | Run as ONE serialized sub-lane (one writer) — palette can start first (ui/ + stores), then header+strip+resizable in order |
| **D — backend** | §1.1 settings, §1.9 sync, §1.12 posture | disjoint files; §1.1 touches risk defaults (4 files) + tests | Fully parallel with each other AND with Lane C |
| **E — decision** | §1.13 | none | Any time, any agent |

## 4. Risk assessment

| Item | Risk | Mitigation |
|---|---|---|
| §1.7 header two-row | **HIGH coupling:** `--header-bottom:52px` (App.svelte:174-178) + LIVE banner slot (185-187) + ModeSwitcher `.live-banner` — a taller head with a stale var = banner overlap | Bump the var in the same commit; keep `:has(:global(.live-banner))` 4th-row intact; regression-check LIVE banner manually |
| §1.3 resizable | **MEDIUM:** 1440px drawer breakpoint (App.svelte:315-350) vs persisted widths; restoring a right-col wider than `min(380px,88vw)` breaks the overlay; grid `minmax(0,1fr)` interplay | Clamp persisted widths to [min, 0.5×vw]; reset persistence at breakpoint; svelte-panels choice is a spec decision (new dep vs hand-roll) |
| §1.2 palette | **LOW:** Ctrl+K global handler must not fight Ctrl+M/R/F/Shift+K; hijack-while-typing guard needed | Reuse KnowledgePanel guard pattern (86-95); keep all shortcuts in one documented registry |
| §1.8 strip | **MEDIUM:** a persistent strip changes default 3-row → 4-row layout (only LIVE banner does this today, conditionally) | Conditionally render strip slot (like `:has(.live-banner)`); WS push for regime, 15s poll or WS for posture |
| §1.1 settings | **MEDIUM:** risk defaults live in 4 spots + tests assert `-5000.0`; persistence decision (config write vs sqlite) | Centralize into one settings store; update assertions; regression tests per endpoint |
| §1.12 posture | **MEDIUM-LOW:** startup chain fetch could hit entitlement (403/-373) on boot | Reuse `DataEntitlementError` → 503 pattern (`intelligence_router.py:115-123,312-315`); degrade to `[UNSOURCED]` |
| §1.9 sync | **LOW:** additive schema change (meta) | No migration needed if keyed on store path; additive columns safe |
| §1.4 scroll-area | **LOW:** 9 wrap sites; the two existing consumers are the pattern; careful with `orientation="both"` (ChainGrid) | Wrap list/panel regions only; keep `overflow:hidden` containers |

## 5. Estimated effort per item

| # | Item | Effort | Nature |
|---|---|---|---|
| 1 | Settings form | **1–2 days** | Full-stack greenfield (endpoints + store + UI + tests) |
| 2 | Command palette | **1–1.5 days** | Frontend: `command` port (~8 files) + palette + Ctrl+K + symbol/action registry |
| 3 | Split-pane resizable | **1 day** (+dep decision) | Frontend: port or hand-roll + grid refactor + persistence |
| 4 | Custom scrollbars | **0.5–1 day** | 9 wrap sites, template exists |
| 5 | ResearchPanel dropdown | **0** (done) | Verify gate |
| 6 | Badge conviction variants | **0.5 day** | Variants + 2 consumers consolidated |
| 7 | Header two-row | **0.5 day** | Header + App.svelte var (must ship together) |
| 8 | Ticker strip | **1–1.5 days** | Strip UI + regime WS + posture data plumbing |
| 9 | Knowledge last sync | **0.5 day** | Store meta + endpoint + panel header |
| 10 | a11y warnings | **0** (done) | Verify gate |
| 11 | Shortcut docs | **0.5 day** | Help dialog + OPERATOR_MANUAL.md |
| 12 | options_posture live | **1 day** | Chain-cache priming / OptionsProjection |
| 13 | DECIDED-DEFER re-eval | **0.5 day** | Decision doc only |
| | **Total** | **~7–9 days** | | 

## 6. Recommended execution order (waves)

- **Wave 0 (30 min, gates):** run §1.5 verify (grep `<select` = 0) + §1.10 verify (`npm run check` 0/0). Mark both roadmap items done.
- **Wave 1 (parallel, 2 lanes):** Lane B — §1.6 badge variants, §1.4 scroll-area rollout, §1.11 shortcut help dialog + manual. Lane D — §1.9 knowledge last-sync, §1.12 options_posture priming. (§1.13 decision doc in parallel.)
- **Wave 2 (serialized frontend chrome, one writer):** §1.2 command palette → §1.7 header two-row (with `--header-bottom` bump) → §1.8 ticker strip (placement resolved by §1.7) → §1.3 resizable (layout settles last so persisted widths are final). Alternative: land §1.3 before §1.7 if resizable is more important than the two-row header — but never interleave.
- **Wave 3 (settings):** §1.1 last — it's the only item needing new backend surface + risk-default consolidation; run after the frontend waves so the form can expose their state (theme via theme.ts is frontend-only, so §1.1's theme section is a UI-pass-through).

**Verification gates every wave:** `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase7 -p no:cacheprovider` + `npm run check` (0/0) + `npm run build` (frontend waves) + `graphify update .` + no file >1000 lines.

## 7. Key files index

| Concern | File:line |
|---|---|
| Settings UI | `web/src/components/SettingsView.svelte` (184 lines) |
| Settings router (empty) | `terminal/api/settings_router.py` (12 lines) |
| Risk default #1 | `intelligence/risk/risk_engine.py:75` |
| Risk default #2 | `intelligence/risk/bus_bridge.py:10-11` |
| Risk default #3 | `terminal/projections.py:157-159` |
| Risk default #4 | `terminal/api/execution_router.py:198` |
| Theme | `web/src/lib/theme.ts` (31 lines) |
| Scheduler (env-gated) | `research/scheduler.py`; wiring `app.py:231-260`; status `research_router.py:137-150` |
| Command primitive | bits-ui 2.18.1 (`dist/index.d.ts` — `Command`, `computeCommandScore`) |
| Center tabs | `web/src/lib/activeTab.ts:3` |
| Selection store | `web/src/lib/selection.ts` (20 lines) |
| Workspace grid | `App.svelte:190-196`; drawer breakpoint `:315-350`; LIVE slot `:185-187`; `--header-bottom` `:174-178` |
| Native scrollbars | `App.svelte:218,334`; `AnalyticsPanel.svelte:210`; `KnowledgePanel.svelte:427`; `LogDrawer.svelte:158`; `ProposalQueue.svelte:442`; `PositionsRiskStrip.svelte:197`; `ResearchPanel.svelte:488`; `ScannerPanel.svelte:333` |
| scroll-area consumers | `ChainGrid.svelte:362`; `Watchlist.svelte:228` |
| Badge variants | `ui/badge/index.ts:14-23` |
| Conviction levels | `ProposalQueue.svelte:84-102`; ScannerPanel `:144,273,397` |
| Header compaction | `Header.svelte:332-342,579-597` |
| Regime projection | `terminal/projections.py:234-308`; WS `:267`; REST `intelligence_router.py:248` |
| Options posture render | `terminal/api/research_source.py:13-74,134-196`; chain cache `intelligence_router.py:319-322` |
| Knowledge status | `knowledge_router.py:123-130`; `knowledge/store.py:246-255` |
| Shortcuts | `App.svelte:47-59`; `ModeSwitcher.svelte:50`; `KnowledgePanel.svelte:86-95`; `KillSwitch.svelte:34`; docs `OPERATOR_MANUAL.md:65,89` |
| Instrument search (palette v2) | `integration/fyers/instrument_master.py:434-444` (no REST endpoint yet) |
| DECIDED-DEFER records | `.scratch/phase4-knowledge-dashboards/issues/07,08`; `map.md:34-35,51-52`; `sections/17-delivery-roadmap.md:11` |
