# Phase 6 Lane E — Component Migration Wave 1: Findings

**Date:** 2026-08-05
**Lane:** E — ui-lib (#10 component migration wave 1)
**Status:** Complete · both verification gates pass
**Baseline:** 1116 tests passing, v0.13.0 (recon `docs/superpowers/plans/2026-08-05-phase6-recon.md` §6)

---

## 1. Delivered components (7/7 ported, none deferred)

All ports live under `terminal/web/src/lib/components/ui/` and follow the
repo's established classic shadcn-svelte pattern (bits-ui subcomponent style,
`cn()` from `$lib/utils.js`, DESIGN.md token classes only — no hardcoded hex).

| Component | Files | Primitive | Notes |
|-----------|-------|-----------|-------|
| **scroll-area** | `scroll-area.svelte`, `scroll-area-scrollbar.svelte`, `index.ts` | bits-ui `ScrollArea` | Self-contained Root (viewport + scrollbar + corner). `orientation` prop: vertical/horizontal/both. Thumb = `bg-hairline-strong` radius 5px, hover `bg-muted` — matches DESIGN §4 scrollbar spec. |
| **select** | 11 subcomponents + `index.ts` | bits-ui `Select` | Full API: Root/Trigger/Content/Item/Group/GroupHeading/Label/Separator/ScrollUpButton/ScrollDownButton/Portal. Trigger styled like Input per DESIGN §4 (canvas-raised + hairline, accent focus ring). Content on `surface-elevated`, items `row-hover`, 8×10px padding. |
| **dropdown-menu** | 17 subcomponents + `index.ts` | bits-ui `DropdownMenu` | Full API incl. Sub/SubTrigger/SubContent/CheckboxItem/RadioGroup/RadioItem/CheckboxGroup/Shortcut/Label/GroupHeading. Menu surface = `surface-elevated`, highlight = `row-hover`, `data-highlighted` styling. |
| **skeleton** | `skeleton.svelte`, `index.ts` | plain div | `animate-pulse bg-surface-elevated rounded-[4px]`. |
| **separator** | `separator.svelte`, `index.ts` | bits-ui `Separator` | `bg-hairline-strong`, horizontal h-px / vertical w-px. |
| **sonner** | `sonner.svelte`, `index.ts` | **svelte-sonner 1.1.1** (new dep) | Theme follows `<html data-theme>` via MutationObserver (no mode-watcher in repo). Toasts pinned to DESIGN tokens: `surface-overlay` bg, `hairline-strong` border, 6px radius, status-token left edge/text via richColors vars. |
| **kbd** | `kbd.svelte`, `index.ts` | plain `<kbd>` | Mono face, 2px radius, hairline border, `surface-elevated` bg. |

**Dependency added:** `svelte-sonner@^1.1.1` (peer svelte ^5 — satisfied). All
other primitives ride on the already-installed `bits-ui@2.18.1`; no new bits-ui
version bump was required. `@lucide/svelte` used for chevron/check/alert icons
(already a dependency).

## 2. Adopting consumers (updated, per recon §6.2)

| Consumer | Adoption | Diff |
|----------|----------|------|
| **ChainGrid** | Native `<select>` expiry → `Select` (mono, commit on change); `.table-wrap` hand-rolled `overflow:auto` → `<ScrollArea orientation="both">`; loading state → 8 Skeleton rows in the table body | ~40 lines |
| **Watchlist** | Exchange `<select>` → `Select`; `.list` native scroll → `<ScrollArea>` wrapping the rows | ~25 lines |
| **ResearchPanel** | Status + lens filter `<select>`s → two `Select` primitives; removed now-dead `.filters select` CSS | ~30 lines |
| **ScannerPanel** | Added a `loading` flag; three card lists render 4 Skeleton rows each while loading (replaces raw empty flashes) | ~35 lines |
| **App.svelte** | `<Toaster />` mounted at app root; WS `alert` topic → toasts (HIGH/CRITICAL → error, MEDIUM → warning, else info) with `description: alert_type`; `Separator` under the drawer head (shown in overlay mode); `Kbd` `Ctrl+R` hint in drawer head | ~40 lines |

WS alert wiring detail: `AlertProjection` broadcasts `{alert_type, severity,
message}` on the `alert` topic (`projections.py:160,204`). `onMessage("alert",
…)` in App.svelte maps severity → DESIGN status token. Subscribes on mount,
unsubscribes on destroy — the existing `ws.ts` topic registry handles the
unsubscribe frame automatically.

## 3. Verification gates (MUST-pass checklist)

| Gate | Result |
|------|--------|
| `npm run check` (svelte-check) | ✅ **0 errors, 0 warnings** |
| `npm run build` (vite) | ✅ Success, exit 0 |
| Full pytest suite | ✅ **1182 passed / 0 failed** (baseline 1116 + other lanes) |
| No file > 1000 lines | ✅ Largest touched: ChainGrid 560, ResearchPanel 594; ui/ max = sonner 51 |
| DESIGN.md tokens | ✅ No hardcoded hex, no `price-up`/`price-down` in chrome components, no shadows/gradients in ui/ ports; red=up/green=down untouched |
| Frontend vitest suite | ✅ 13 passed (5 files) |
| `graphify update .` | ✅ 7218 nodes rebuilt |

### Bundle-size check (mandatory per recon §6.3)

| Asset | Before (HEAD) | After | Delta |
|-------|---------------|-------|-------|
| JS raw | 322.9 KB | 429.1 KB | **+106.2 KB** |
| JS gzip | — | **128.9 KB** | +~20 KB est. |
| CSS raw | 69.7 KB | 85.4 KB | +15.7 KB |

The JS delta is almost entirely the new **svelte-sonner** dependency (78 KB
installed) plus the bits-ui menu/select/scroll machinery now actually being
bundled. Net gzip impact ≈ +20 KB — acceptable for a toast surface + two
menu-class primitives; no action required. (Sonner is lazy in spirit — its
Toast surface mounts once and the tree-shaken payload is small.)

## 4. Design decisions worth recording

1. **Classic port, not registry-v2.** The current shadcn-svelte registry (v2)
   relies on `WithoutChild`/`WithElementRef` type helpers, global `cn-*`
   utility classes, and an `IconPlaceholder` indirection — none of which exist
   in this repo. All ports were adapted to the repo's established classic
   pattern (seen in `dialog`, `tooltip`, `tabs`): plain `Props & { class?,
   children? }`, explicit `cn()`, DESIGN token classes inline. This keeps the
   codebase internally consistent and the diff reviewable.
2. **Sonner theme follows the terminal, not the OS.** No mode-watcher in the
   repo; theme lives on `<html data-theme>` (`lib/theme.ts`). The Toaster
   observes that attribute (MutationObserver) so toasts match the operator's
   active theme, and all toast surfaces are pinned to DESIGN tokens so the
   richColors pastels never leak in.
3. **Scrollbar spec honored.** DESIGN §4 calls for a 10px transparent track
   with a `hairline-strong` thumb (radius 5px) that warms to `muted` on hover —
   encoded directly in the port, so ChainGrid's previously OS-native scrollbars
   now match the DESIGN scrollbar contract (pre-pays Phase 7 #4).
4. **Price-token boundary.** None of the ported chrome components use
   `price-up`/`price-down` — those stay reserved for data columns (DESIGN §2.4).
   Status severity in toasts uses `success`/`warning`/`danger`/`info`, never
   price colors.

## 5. Residual / future work

- **`kbd` currently used once** (drawer-head Ctrl+R). Full shortcut-hint UI
  (Ctrl+M/Ctrl+F, Phase 7 #11) can adopt it when the command palette lands.
- **Sonner adoption is surface-only today** (WS alerts). Research run-complete,
  order accept/reject, and risk events are candidate call sites for follow-up
  toasts.
- **`dropdown-menu` is in but has no consumer yet** — it exists as the
  documented prerequisite for select (now true) and the Phase 7 command
  palette. A "panel overflow menu" consumer can adopt it later.
- Native scroll containers remain in panels outside this wave's scope
  (e.g. LogDrawer, AnalyticsPanel, ProposalQueue) — a second ScrollArea
  adoption pass is a cheap follow-up.
- Svelte-sonner adds ~20 KB gzip; if bundle budget tightens later, a
  hand-rolled toaster (bits-ui has none) could replace it, but the sonner
  semantics (promise toasts, dismiss, position) justify the cost today.

## 6. Files touched (scope audit)

All changes confined to `terminal/web/src/` (ui/ + consumers) and the committed
`terminal/static/` bundle; nothing outside Lane E's ownership was modified.

- **New:** `ui/{scroll-area,select,dropdown-menu,skeleton,separator,sonner,kbd}/` (7 families, 39 files)
- **Modified:** `components/{ChainGrid,Watchlist,ResearchPanel,ScannerPanel}.svelte`, `App.svelte`
- **Dependency:** `web/package.json` + `package-lock.json` (`svelte-sonner@^1.1.1`)
- **Bundle:** `terminal/static/` regenerated via `npm run build` (committed per repo convention)

*No commit made (per lane instruction).*
