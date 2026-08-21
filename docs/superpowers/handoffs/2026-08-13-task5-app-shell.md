# Task 5: Extract App.svelte Shell

**Date**: 2026-08-13

## Summary

Extracted router logic, workspace layout, and center tabs from `App.svelte` into dedicated modules. Reduced `App.svelte` from 612 lines to 215 lines (65% reduction).

## Extracted Files

| File | Lines | Purpose |
|------|-------|---------|
| `src/lib/router.svelte.ts` | 47 | Hash-based router state (`route`, `query`, `initRouter`, `teardownRouter`) |
| `src/lib/activeTab.svelte.ts` | 13 | Rune-based center-tab state (replaces writable store in `activeTab.ts`) |
| `src/components/layout/Workspace.svelte` | 243 | Resizable 3-col workspace (rail/gutter/center/gutter/right) with drag + keyboard resize, localStorage persistence |
| `src/components/layout/CenterTabs.svelte` | 80 | Tab bar (CHAIN/SCANNER/HINTS/ANALYTICS/GREEKS) + keep-alive hidden panels |

## App.svelte Line Count

| Metric | Before | After | Δ |
|--------|--------|-------|---|
| Lines | 612 | 215 | -397 (-65%) |

## What Remains in App.svelte

- Route switch (`/`, `/settings`, `/setup`, 404)
- `app-grid` CSS with LIVE banner slot logic
- WS connect + alert-to-toast mapping
- Keyboard shortcuts (Ctrl+R drawer toggle, Esc close)
- CommandPalette + Toaster mount
- Header, TickerStrip, PositionsRiskStrip, RiskHeatmap layout

## Rune Migration

- `App.svelte` now imports from `./lib/activeTab.svelte.ts` (rune-based) instead of `./lib/activeTab.ts` (writable store)
- Usage changed from `$activeTab` to `activeTab.value`
- `router.svelte.ts` uses `$state` runes for `route` and `query`
- **Scope note**: Only App.svelte's store imports migrated. Other components (Header, ChainGrid, etc.) still use the old writable stores (Task 4's scope).

## Verification

| Check | Result |
|-------|--------|
| `npm run check` (svelte-check) | 0 errors, 4 warnings (2 pre-existing, 2 about removed `.ts` files) |
| `npm run build` | ✅ Success (23s, 508 kB JS bundle) |
| Python tests | 1625 passed, 1 skipped, 1 pre-existing PermissionError (Windows SQLite teardown) |
