# Phase 6 · Wave 3 Item #7 — selection.ts → {symbol, exchange}: Findings

**Date:** 2026-08-05
**Status:** Complete — svelte-check 0 errors/0 warnings, build OK, 17/17 frontend tests passing
**Recon source:** `docs/superpowers/plans/2026-08-05-phase6-recon.md` §7/§10 (roadmap #7) + §2.3 (exchange derived in Header from REST)
**Scope:** `selection.ts`, `Header.svelte`, `ChainGrid.svelte`, `Watchlist.svelte` (+ committed static bundle from the build gate)

---

## 1. What changed

| Location | Before | After |
|----------|--------|-------|
| `lib/selection.ts` | `export const selectedSymbol = writable<string>("")` | `writable<SelectedSymbol>({ symbol: "", exchange: "" })` with exported `type SelectedSymbol = { symbol: string; exchange: string }` |
| `Header.svelte` | Hero derived `exchange` from `exchangeBySymbol` map built via `GET /api/watchlist` (`loadExchanges()`, called on mount + every 30s) | `exchange = selection.exchange \|\| "NSE"` — read straight from the selection store; `loadExchanges()`, `exchangeBySymbol`, and the `WatchlistItem` type **deleted**; the 30s interval now only re-polls health + creds |
| `ChainGrid.svelte` | `exchange = $state("NSE_FNO")` — hardcoded, fed CandleChart regardless of selection | Selection subscription now applies `sel.exchange` to the `exchange` state; `"NSE_FNO"` remains the default only for the manual symbol input path (no selection yet) |
| `Watchlist.svelte` | `selectedSymbol.set(symbol)` — string only | `selectRow(item)` sets `{ symbol: item.symbol, exchange: item.exchange \|\| "NSE" }`; 3 call sites updated to pass the `WatchItem` |
| `ChainGrid.test.ts` | — | **No change needed** — its `selectedSymbol` mock (`subscribe: vi.fn(...)`) never invokes the handler, so the new object shape is invisible to the tests |

## 2. Key findings

### 2.1 The chain REST endpoint never needed exchange — exchange was a chart-only concern
`GET /api/intelligence/options` (`intelligence_router.py:303-323`) takes **only `symbol` + `expiry`**; exchange is not a query param. ChainGrid's `exchange` state feeds exclusively `CandleChart` via `getMarketBars(symbol, exchange, tf)`. So the correct exchange on the chain was purely about the chart's bar request (`NSE_FNO` was the right *domain* default for options — it is the options segment). The real defect was Header: it made a **full watchlist REST round-trip every 30s** just to print the exchange next to the hero symbol.

### 2.2 Backward-compatibility strategy
The store's value shape changed, so every consumer re-derives its own domain default when `exchange` is empty (never throws, never breaks a legacy string setter):
- **Header → `"NSE"`** (its pre-existing fallback; equities/indices default segment).
- **ChainGrid → `"NSE_FNO"`** (its pre-existing default; options segment).

This satisfies "if exchange is missing, default to NSE" while keeping each panel's semantically correct fallback. Empty `symbol` remains falsy, so the header's `class:empty` / `"—"` empty-state logic is unchanged.

### 2.3 Why Watchlist passes the row, not a string
`WatchItem` already carries `exchange` (from `/api/watchlist`), so `selectRow` now takes the item and defaults to `"NSE"` only if the backend omitted exchange. Keyboard (Enter/Space, ArrowUp/Down) and click paths all route through the same `selectRow`, so both get the exchange for free.

### 2.4 Removed a 30s × 1 REST call, not the header's other polls
`load()` (`/api/health` + `/api/health/session`) and `loadCreds()` (`authStatus`) are untouched — the hero's connection pip, session clock, and credential chip still poll. Only the watchlist exchange-mapping round-trip is gone; the `get` import stays (still used by `load`).

## 3. Verification

| Gate | Result |
|------|--------|
| `npm run check` (svelte-check) | **0 errors, 0 warnings** |
| `npm run build` (vite) | **Success** — 4628 modules, committed bundle refreshed |
| `npm run test` (vitest) | **17/17 passed** (ChainGrid live-tick + CandleChart tests exercise the touched components) |
| Header REST exchange map | Removed — `loadExchanges`/`exchangeBySymbol`/`WatchlistItem` grep = zero matches |
| Git scope | Only the 4 owned source files + static bundle (build gate) modified |

## 4. Follow-ups (out of scope)
- `Watchlist.remove()` clears the local `selected` but not the store (pre-existing; store is only ever set, never cleared). With the store now an object, consider clearing `{ symbol: "", exchange: "" }` on removal in a later item.
- Phase-6 recon §2.4/§2.3: once strike/option_type ride the wire, ChainGrid's 15s poll narrows to IV-only — unrelated to this item.
