# Task 4: Migrate Legacy Stores to Svelte 5 Runes

**Date**: 2026-08-13  
**Status**: ✅ Complete  

## Summary

Migrated `activeTab.ts` and `selection.ts` from Svelte 4 `writable()` stores to Svelte 5 `$state` runes, following the existing `connection.svelte.ts` pattern.

## Store Migrations

### activeTab.ts → activeTab.svelte.ts

- **Before**: `writable<CenterTabId>("chain")` — used via `$activeTab` (subscribe) and `activeTab.set(tab)`
- **After**: `$state({ value: "chain" })` — used via `activeTab.value` (read) and `activeTab.value = tab` (write)
- Wrapped primitive in object to enable property-level mutation (matching `connectionStore` pattern)

### selection.ts → selection.svelte.ts

- **Before**: `writable<SelectedSymbol>({...})` — used via `$selectedSymbol` (subscribe) and `selectedSymbol.set({...})`
- **After**: `$state({ symbol: "", exchange: "" })` — used via `selectedSymbol.symbol` / `selectedSymbol.exchange` (read + write)
- Object type allows direct property mutation without wrapper

## Updated Components

| Component | Changes |
|-----------|---------|
| **CommandPalette.svelte** | Import path → `.svelte.ts`, `activeTab.set(tab)` → `activeTab.value = tab` |
| **ChainGrid.svelte** | Import path → `.svelte.ts`, replaced `selectedSymbol.subscribe()` in `onMount` with top-level `$effect()`, `selectedSymbol.set(...)` → direct property mutation |
| **Watchlist.svelte** | Import path → `.svelte.ts`, `selectedSymbol.set({...})` → direct property mutation |
| **Header.svelte** | Import path → `.svelte.ts`, `$selectedSymbol` → `selectedSymbol` (no store prefix needed) |

## Files NOT touched (Task 5 ownership)

- `App.svelte` — still imports from `./lib/activeTab` (old path); Task 5 will update it

## Verification

- ✅ `npm run check` — 0 errors (2 pre-existing warnings in unrelated files)
- ✅ `npm run build` — success (22s)
- ✅ Python test suite — 1626 passed, 1 skipped, 0 failed
