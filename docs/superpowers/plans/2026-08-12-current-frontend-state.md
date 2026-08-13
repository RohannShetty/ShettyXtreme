# Current Frontend State — Findings for the v0.16.0 Refactor

**Date:** 2026-08-12
**Purpose:** Ground-truth inventory of the existing frontend before Phase 1 of the shadcn-svelte refactor. Feeds `2026-08-12-v0.16.0-refactor-plan.md`.

---

## ⚠️ Executive finding — the plan's premise is stale

The v0.16.0 refactor plan says the current state is "v0.15.0, UI broken, shadcn-svelte not set up". **The repo does not match that.** As of today:

- **shadcn-svelte is already initialized** (`components.json`, "new-york" style, `$lib/components/ui` with **18 component families**).
- **Tailwind v4 is already wired** (`@tailwindcss/vite`, `@import "tailwindcss"` in `app.css`, `@theme inline` block).
- **A full design-token system already exists** (`design.css`: dark/light × international/indian, ~50 CSS custom properties).
- **A typed API client already exists** (`api.ts`: ~20 endpoint functions + ~40 types), plus a topic-based **WebSocket client** (`ws.ts`).
- **104 Svelte files (~372 KB)** of working feature code behind a hash-routed SPA shell.

Phase 1 of the refactor ("set up shadcn, design tokens, base components, API contract") is **largely already done**. Phase 1 should be re-scoped to *consolidate/extend* what exists, not build from scratch. The real gaps: no real router, no alert/popover/switch primitives, no API-versioning strategy, mixed state model (runes vs. legacy stores), and heavy bespoke CSS in feature components.

---

## 1. Current directory structure

```
src/shettyxtreme/terminal/web/
├── components.json          # shadcn-svelte config (new-york, neutral, css vars)
├── index.html               # SPA entry (no router; #/hash routing)
├── package.json             # v0.13.0
├── svelte.config.js         # vitePreprocess only
├── tsconfig.json            # strict, moduleResolution: bundler, $lib paths
├── vite.config.ts           # tailwindcss + svelte plugins; build → ../static; dev proxy :3000→:8000
├── vitest.config.ts         # happy-dom, src/**/*.test.ts
├── src/
│   ├── main.ts              # mounts App; imports app.css + design.css; initTheme + initColorConvention
│   ├── App.svelte           # 612-line SPA shell: hash routing, resizable panes, WS boot, toasts
│   ├── components/          # ← feature components (flat, no per-feature folders)
│   │   ├── AnalyticsPanel.svelte        ChainGrid.svelte           CandleChart.svelte
│   │   ├── CommandPalette.svelte        GreeksPanel.svelte         Header.svelte
│   │   ├── HintsPanel.svelte            KillSwitch.svelte          LogDrawer.svelte
│   │   ├── ModeSwitcher.svelte          OrderHistory.svelte        PositionsRiskStrip.svelte
│   │   ├── ProposalQueue.svelte         ResearchBriefDetail.svelte ResearchPanel.svelte
│   │   ├── RightDockTabs.svelte         RiskHeatmap.svelte         ScannerPanel.svelte
│   │   ├── SettingsView.svelte          SetupWizard.svelte         ShortcutsDialog.svelte
│   │   ├── SymbolSearch.svelte          TickerStrip.svelte         Watchlist.svelte
│   │   ├── knowledge/                   # KnowledgeDetail.svelte + knowledge-shared.ts
│   │   ├── state/                       # EmptyState.svelte / ErrorState.svelte / LoadingState.svelte
│   │   └── *.test.ts                    # ChainGrid, CandleChart, SettingsView, SetupWizard
│   └── lib/
│       ├── api.ts             # typed fetch helpers (get/post/postBody/putBody/del) + all API types
│       ├── ws.ts              # WebSocket client: topics, subscribe frames, exponential backoff, pings
│       ├── connection.svelte.ts  # Svelte-5 $state connection store (rune file — must keep .svelte.ts)
│       ├── activeTab.ts       # legacy writable store (center tab id)
│       ├── selection.ts       # legacy writable store (selected symbol + exchange)
│       ├── theme.ts           # dark/light, localStorage "sx-theme"
│       ├── color-convention.ts# international/indian, localStorage "sx-convention" (+ test)
│       ├── utils.ts           # cn() = twMerge(clsx())
│       ├── app.css            # Tailwind v4 entry + shadcn layer→token alias mapping + @theme inline
│       ├── design.css         # ← ALL design tokens (dark/light × intl/indian), fonts, base styles
│       └── components/ui/     # ← shadcn-svelte registry components (18 families, see §3)
```

Committed build output lives in `src/shettyxtreme/terminal/static/` (vite `outDir: "../static"`, `base: "/static/"`), served by FastAPI.

## 2. Existing components (grouped by feature)

### App shell / layout
| Component | Lines | Role |
|---|---|---|
| `App.svelte` | 612 | Hash router, 3-col resizable workspace (rail/gutter/center/gutter/right), tabs, drawer <1440px, Ctrl+R, Esc, WS connect, alert→toast mapping |
| `Header.svelte` | 704 | Brand, LTP hero, ModeSwitcher, connection pip, entitlement chip, session clock, cred chip, kill switch, theme toggle, shortcuts, logs drawer; two-row <1024px |
| `CommandPalette.svelte` | 421 | Ctrl+K/⌘K palette with Dialog; Research/Knowledge items open right dock |
| `RightDockTabs.svelte` | 124 | Hand-rolled tab bar: Proposals / Orders / Research+Knowledge / Logs |
| `ShortcutsDialog.svelte` | 171 | Keyboard-shortcut reference |
| `ModeSwitcher.svelte` | 350 | OBSERVER/PAPER/LIVE w/ typed confirmation + CSRF, LIVE banner |
| `KillSwitch.svelte` | 154 | Armed kill switch with pulse + confirm Dialog |
| `state/` | 3 files | EmptyState / ErrorState / LoadingState primitives |

### Center tabs (DESIGN §4 keep-alive hidden panels)
| Component | Lines | Feature |
|---|---|---|
| `ChainGrid.svelte` | 677 | Option chain: expiry select, strike table, live WS OI/LTP, column layout, skeletona |
| `ScannerPanel.svelte` | 521 | 11 scanner types, thresholds, findings |
| `HintsPanel.svelte` | 294 | Strategy hints w/ rationale + one-click proposals |
| `AnalyticsPanel.svelte` | 393 | Regime/calibration/scorecard dashboards |
| `GreeksPanel.svelte` | 262 | Portfolio + per-position greeks |
| `CandleChart.svelte` | 212 | Intraday candle chart (+ test) |

### Rail / strips
| Component | Lines | Feature |
|---|---|---|
| `Watchlist.svelte` | 411 | Watchlist + live ticks, SymbolSearch, select exchange |
| `SymbolSearch.svelte` | 230 | SERP autocomplete (NSE/BSE) |
| `TickerStrip.svelte` | 474 | Regime/IV/PCR/max-pain chrome, 30s polling |
| `PositionsRiskStrip.svelte` | 319 | Positions + risk summary strip |
| `RiskHeatmap.svelte` | 533 | Sector/expiry risk heatmap |

### Right dock
| Component | Lines | Feature |
|---|---|---|
| `ProposalQueue.svelte` | 676 | OBSERVER propose→approve/reject flow + confirm Dialog |
| `OrderHistory.svelte` | 310 | Order list w/ status badges |
| `ResearchPanel.svelte` | 598 | Research lens runs, briefs, decision workflow |
| `ResearchBriefDetail.svelte` | 142 | Brief detail view |
| `KnowledgePanel.svelte` | 585 | Knowledge docs search/sync/tags |
| `knowledge/KnowledgeDetail.svelte` | — | Knowledge doc detail |
| `LogDrawer.svelte` | 223 | Server log stream |

### Routes (hash-based, no router library)
- `#/` → terminal cockpit
- `#/settings` → `SettingsView.svelte` (810 lines: risk limits, theme, color convention, scheduler)
- `#/setup` → `SetupWizard.svelte` (178 lines: credential onboarding)
- else → inline 404

### Tests
8 test files: `ui/textarea`, `ui/table/table-row`, `ui/input`, `lib/color-convention`, `components/{SetupWizard, SettingsView, ChainGrid, CandleChart}`. Each UI test has a `*.test-harness.svelte`. **No E2E (Playwright is mentioned in the plan but not installed).**

## 3. UI library state (shadcn-svelte, already installed)

`src/lib/components/ui/` — **18 families**, standard shadcn-svelte shape (each has `index.ts` + parts):

`badge, button, card, checkbox, dialog, dropdown-menu, input, kbd, label, scroll-area, select, separator, skeleton, sonner, table, tabs, textarea, tooltip`

**Actually used in feature code** (grep of `$lib/components/ui` imports): `button, badge, card, dialog, input, kbd, scroll-area, select, separator, skeleton, sonner (Toaster), table, tabs, textarea, tooltip` — 15 of 18.

**Scaffolded but not referenced by any feature component:** `checkbox, dropdown-menu, label`. (Likely added for future work or leftover scaffolding.)

**Customized beyond stock:** `badge` — extended variants (`success/warning/danger/info`, 4-level `conviction-*` scale, DESIGN §4). `button` variants used w/ `text-muted-foreground hover:text-accent-active` classes. Components use shadcn's "new-york" CVA style; UI primitives are lean (Button = 31 lines).

**Dependencies** (`package.json` v0.13.0):
- Runtime: `bits-ui ^2.18`, `class-variance-authority ^0.7`, `clsx ^2.1`, `svelte-sonner ^1.1`, `tailwind-merge ^3.6`, `tw-animate-css ^1.4`, `@lucide/svelte ^1.28`
- Dev: `svelte ^5`, `@sveltejs/vite-plugin-svelte ^5`, `vite ^6`, `tailwindcss ^4.3` + `@tailwindcss/vite`, `typescript ^5.6`, `svelte-check ^4`, `vitest ^4`, `happy-dom ^20`, `@testing-library/{dom,svelte}`

**Not installed (gaps vs. the refactor plan):** no `alert`, `popover`, `switch`, `slider`, `sheet`, `avatar`, `progress`, `radio-group`, `collapsible`, `drawer`, `command` (palette is hand-rolled). No router lib. No charts lib (CandleChart is hand-rolled SVG/canvas). No Playwright/E2E.

## 4. Styling approach

**Three layers, deliberately split:**

1. **`design.css` — the single source of truth for tokens** (~50 CSS custom properties under `:root[data-theme]` × `[data-convention]`): canvas/surface/hairline greys, ink/body/muted/faint text, amber accent + focus-ring, price up/down (+strong/+soft/flash) with **international default (green up `#2ebd85` / red down `#f6525c`)** and **Indian opt-in swap**, semantic status (success/warning/danger/info), row hover/selected, candle/option/side/SL/target colors, scrim, fonts. Also global base: `box-sizing`, body font 13px Inter, `.num/.ticker/.mono` → JetBrains Mono tabular, `.price-up/.price-down/.flash-*` utilities + keyframes.
2. **`app.css` — Tailwind v4 entry + shadcn alias bridge**: `@import "tailwindcss"`, `@import "tw-animate-css"`, `@custom-variant dark (&:is([data-theme="dark"] *))`, and an `@theme inline` block mapping every shadcn layer alias (`--color-primary`, `--color-card`, `--color-border`, … `--color-danger`) **to the design.css tokens** — "Never hard-code hex here (P5a)". Also `--radius: 6px` and the kill-pulse animation.
3. **Per-component scoped `<style>` blocks** with heavy use of `var(--token)` — feature components (Header 704 / SettingsView 810 lines) carry large bespoke CSS: CSS-grid layouts, media-query breakpoints (1440/1360/1240/1080/1024), `:has()` LIVE-banner row tricks, `color-mix` chips, custom animations, `prefers-reduced-motion` guards.

**Mixed utility usage:** Tailwind utilities in markup (flex/size-4/text-muted-foreground) coexist with scoped-style classes. Tab keep-alive relies on unlayered `.tab-panel.hidden` beating the Tailwind `hidden` utility (documented cascade note in App.svelte). **No Tailwind config file** — Tailwind v4 is config-less (CSS-first `@theme`).

**Fonts:** Inter (sans) + JetBrains Mono (tabular numerals) — declared as CSS vars only; **not bundled**, rely on system/fallback (`system-ui`, `ui-monospace`).

## 5. API client setup

**REST — `lib/api.ts`** (no codegen; hand-written typed wrapper):
- Generic `get/post/postBody/putBody/del` over `fetch` with 10s AbortController timeout, `credentials: "same-origin"`, JSON error extraction (`detail`/`message`), abort→"Request timeout".
- ~20 typed endpoint functions + ~40 exported types, grouped: auth (`/auth/*`), execution (`/api/execution/proposals|orders|mode|risk` w/ CSRF header support), market bars, settings (`/api/settings*`), research (`/api/research/*` types), knowledge, symbol search, analytics/sessions.
- **No base-URL abstraction** — paths are relative, resolved by the Vite dev proxy (`/api`, `/auth` → `:8000`) and, in prod, served same-origin under `/static` with API at `/` (FastAPI mounts).
- **No `v2` namespace yet** — the refactor plan proposes `/api/v2/*`; nothing in `api.ts` uses it today.

**WebSocket — `lib/ws.ts`**:
- Topic-based registry (`onMessage(topic, handler)`), server frames `{topic, data}`, subscribe frames sent on connect/registry-change, 30s pings, exponential backoff reconnect (2s→30s cap, ±20% jitter), `stop()` teardown.
- Consumed topics seen: `tick`, `alert`, `connection` (via `connection.svelte.ts` store feeding Header pip).

**State layer** — mixed:
- **Legacy Svelte 4 stores:** `activeTab.ts`, `selection.ts` (writable).
- **Svelte 5 runes:** `connection.svelte.ts` ($state store — file renamed with `.svelte.ts` infix after the blank-screen bug; **rule: runes only compile in `.svelte`/`.svelte.js`/`.svelte.ts`**). Components use `$state`/`$derived`/`$props`/`$bindable` throughout.

## 6. Design tokens / theme system (exists — reusable as-is)

| System | Mechanism |
|---|---|
| Theme | `data-theme="dark\|light"` on `<html>`, localStorage `sx-theme`, `theme.ts` init in `main.ts` |
| Color convention | `data-convention="international\|indian"`, localStorage `sx-convention`, `color-convention.ts` |
| Tokens | `design.css` = source of truth; `app.css` bridges shadcn aliases → tokens; Tailwind v4 `@theme inline` makes them `text-price-up` etc. usable as utilities |
| Radius | `--radius: 6px` base → sm/md/lg/xl derived |
| Typography | `--font-sans` Inter, `--font-mono` JetBrains Mono; hierarchy in DESIGN.md §3 |
| Motion | `tw-animate-css`, custom keyframes (flash, pip-pulse, kill-pulse) with reduced-motion guards |

DESIGN.md (binding UI contract) covers §1 atmosphere, §2 palette/tokens, §3 typography, §4 component stylings, §5 layout, §6 depth, §7 do/don'ts, §8 responsive, §9 agent prompt guide. **Tokens and DESIGN.md align 1:1** — this is the strongest reusable asset.

## 7. Build setup

| Concern | Current |
|---|---|
| Bundler | Vite 6, plugins `tailwindcss()` + `svelte()` (vite-plugin-svelte 5) |
| Output | `outDir: ../static`, `emptyOutDir: true`, `base: "/static/"` — **committed** bundle served by FastAPI (`terminal/static`) |
| Dev server | `:3000`, proxies `/api` + `/auth` → `http://127.0.0.1:8000`, `/ws` → ws proxy |
| Alias | `$lib` → `src/lib` (both vite + tsconfig paths) |
| TS | strict, ES2022, `moduleResolution: bundler`, `verbatimModuleSyntax`, `noEmit`, types `vite/client`, include `src/**/*.ts` + `*.svelte` |
| Checks | `npm run check` (svelte-check, 0-error gate), `npm run build`, `npm run test` (vitest, happy-dom, `src/**/*.test.ts`) |
| Preprocess | `vitePreprocess()` only |
| Version | `package.json` 0.13.0 — **drifted** (CHANGELOG head v0.15.0, `__init__.py` 0.6.0, api/app.py 0.7.0, plan targets v0.16.0) |

## 8. Reuse vs. rebuild

### ✅ Reuse as-is (do not rebuild)
- **Design token system** (`design.css` + `app.css` bridge + `theme.ts` + `color-convention.ts`) — exactly what Phase 1.2 of the plan asks to create; it exists and matches DESIGN.md.
- **shadcn-svelte primitives** (15/18 in use) — Button, Badge (incl. custom conviction variants), Card, Dialog, Input, Kbd, ScrollArea, Select, Separator, Skeleton, Sonner, Table, Tabs, Textarea, Tooltip.
- **API client** (`api.ts` types + fetch wrappers) and **WS client** (`ws.ts` topic registry) — both solid, typed, tested in use. Extend with v2 endpoints rather than rewrite.
- **`connection.svelte.ts`** unified connection store + Header pip feed.
- **State primitives** (`state/EmptyState|ErrorState|LoadingState`), `cn()` util, `$lib` alias conventions, vitest harness pattern.
- **Keep-alive tab pattern** in App.svelte (DESIGN §4) and the resizable-pane gutter system.

### 🔧 Refactor/consolidate (keep behavior, change shape)
- **App.svelte (612 lines)** — hand-rolled hash router + all layout/state in one file. Extract a router (or adopt one) and split the shell.
- **Bespoke component CSS** — Header (704), SettingsView (810), ChainGrid (677), ProposalQueue (676) carry hundreds of lines of scoped CSS + media queries. Move reusable pieces into tokens/primitives (e.g., status chips → Badge variants, panel chrome → Card).
- **Legacy writable stores** (`activeTab.ts`, `selection.ts`) vs. runes — pick one model. Runes (`$state` in `.svelte.ts`) are the Svelte 5-idiomatic direction already used by `connection.svelte.ts`.
- **Hand-rolled equivalents of standard primitives** — CommandPalette (no `command` component), RightDockTabs tab bar (hand-rolled instead of shadcn Tabs), CandleChart (hand-rolled; no chart lib).
- **Version drift** — align `package.json`/`__init__.py`/api/app.py/CHANGELOG on one version during the refactor.

### 🆕 Rebuild / add (genuine gaps)
- **Alert, Popover, Switch, Slider, Sheet/Drawer, Progress, RadioGroup, Collapsible** primitives (missing from `ui/`; plan Phase 1.3 lists Alert).
- **Real router** or a deliberate decision to keep hash routing (fine for a local workstation tool, but document it).
- **`/api/v2` namespace** + OpenAPI spec (plan Phase 1.4) — nothing versioned today.
- **E2E layer** (Playwright) — plan mentions it; only vitest unit tests exist.
- **Font bundling** — Inter/JetBrains Mono are not bundled; `npm run build` has no local font strategy (offline/private workstation).
- **`checkbox`, `dropdown-menu`, `label`** are scaffolded but unused — either wire them in or note them dead.

## 9. Recommendations for the refactor (Phase 1 re-scope)

1. **Rewrite the Phase-1 premise.** Phase 1 of `2026-08-12-v0.16.0-refactor-plan.md` (shadcn setup, token system, base components, API types) is ~80% complete on disk. Re-scope Phase 1 to: (a) inventory reconciliation (this doc), (b) add the missing primitives (Alert/Popover/Switch/etc.), (c) introduce the `/api/v2` contract + versioned types alongside the existing v1 client, (d) decide the state-model (runes everywhere) and router question, (e) version alignment.
2. **Keep `design.css` as the single token source; never fork hex values into components** (already enforced — P5a).
3. **Extract before rebuilding:** the workspace shell (App.svelte) and the 4 biggest components (Header, SettingsView, ChainGrid, ProposalQueue) are where refactor effort pays; every other feature component is already thin enough to touch incrementally.
4. **Incremental migration, not big-bang:** the risk-mitigation section of the plan (parallel build, feature-by-feature cutover, rollback per stage) is sound and matches the current codebase's modularity — the static bundle is committed, so every build is already a deployable unit.
5. **Guardrail:** any new reactive module must use the `.svelte.ts` infix (see `2026-08-12-svelte-build-issue.md`) — the blank-screen `$state` bug is the #1 regression risk during a refactor that touches many files.
6. **Tests:** keep the vitest harness pattern; add component tests for the refactored primitives; the 0-error `npm run check` gate is the refactor's safety net.

## Files referenced
- `src/shettyxtreme/terminal/web/package.json`, `vite.config.ts`, `tsconfig.json`, `svelte.config.js`, `vitest.config.ts`, `components.json`, `index.html`
- `src/shettyxtreme/terminal/web/src/main.ts`, `App.svelte`
- `src/shettyxtreme/terminal/web/src/lib/{api,ws,theme,color-convention,utils,activeTab,selection,connection.svelte}.ts`, `app.css`, `design.css`
- `src/shettyxtreme/terminal/web/src/components/*` (31 entries incl. `knowledge/`, `state/`)
- `src/shettyxtreme/terminal/web/src/lib/components/ui/*` (18 families)
- `docs/superpowers/plans/2026-08-12-v0.16.0-refactor-plan.md`, `2026-08-12-svelte-build-issue.md`
- `DESIGN.md`, `AGENTS.md`, `CHANGELOG.md`
