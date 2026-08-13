# Handoff: Svelte Rune Compilation Fix

**Date:** 2026-08-12  
**Status:** Complete  
**Type:** Bug fix (Svelte 5 rune compilation)

## Problem

`src/shettyxtreme/terminal/web/src/lib/connection.ts` used Svelte 5's `$state()` rune (line 22), but Svelte's compiler only processes runes in `.svelte`, `.svelte.js`, or `.svelte.ts` files. The `.ts` extension meant `$state()` was passed through uncompiled to the production bundle, causing the connection pip to be non-reactive.

## Changes

| File | Change |
|------|--------|
| `src/shettyxtreme/terminal/web/src/lib/connection.ts` → `connection.svelte.ts` | Renamed to enable Svelte rune compilation |
| `src/shettyxtreme/terminal/web/src/components/Header.svelte` (line 12) | Updated import to `"../lib/connection.svelte.ts"` |
| `src/shettyxtreme/terminal/web/tsconfig.json` | Added `"allowImportingTsExtensions": true` (required for `.svelte.ts` import path) |

## Verification

### `npm run check` — 0 errors
```
svelte-check found 0 errors and 2 warnings in 2 files
```
Warnings are pre-existing and unrelated (SymbolSearch `$state` hint, ProposalQueue CSS prefix).

### `npm run build` — success
```
✓ built in 29.19s
index-BscedVmj.js  506.83 kB │ gzip: 150.13 kB
```

### Bundle rune check — no raw `$state()` calls
```
Select-String -Pattern '\$state\(' → (no output)
```
The `$state()` rune was properly compiled by the Svelte compiler into reactive getters/setters. No uncompiled rune calls remain in the production bundle.

## Notes

- The `.svelte.ts` extension requires `allowImportingTsExtensions: true` in tsconfig.json (already has `noEmit: true`, so this is safe).
- Vite's `vite-plugin-svelte` handles the `.svelte.ts` extension at build time; TypeScript's LSP needed the tsconfig flag to stop erroring on the import path.
