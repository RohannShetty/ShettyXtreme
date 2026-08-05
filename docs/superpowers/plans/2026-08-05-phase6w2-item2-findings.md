# Phase 6 · Wave 2 Item #2 — Chain Fields on the Tick Wire: Findings

**Date:** 2026-08-05
**Status:** Complete — 1187 backend tests + 17 frontend tests passing, svelte-check 0 errors, build OK
**Recon source:** `docs/superpowers/plans/2026-08-05-phase6-recon.md` §2 (roadmap #2)
**Scope:** Extend the `tick` WS payload with `strike`/`option_type`/`oi` so ChainGrid updates live without REST polling.

---

## 1. What changed

| Layer | Before | After |
|-------|--------|-------|
| **Tick model** (`core/data_models/market_data.py`) | `symbol, exchange, ltp, volume, timestamp, bid, ask, ohlc, oi` | + `strike: float \| None = None`, `option_type: str \| None = None` (defaulted — no call-site breakage) |
| **Adapter** (`integration/fyers/data_adapter.py` `_parse_tick`) | `from_fyers()` computed `strike`/`option_type` then discarded them | Kept on the Tick (`strike` int→float, `option_type` CE/PE) |
| **Projection** (`terminal/projections.py` `WatchlistProjection`) | Broadcast `{symbol, ltp, change_pct, volume}` only | Broadcast `{symbol, ltp, change_pct, volume, oi, strike, option_type}`; state store + `add()` defaults extended |
| **WS bridge** (`terminal/api/ws_bridge.py` → `ws_manager.py`) | — | **No change needed**: payload is a plain dict of native types (`float`/`str`/`None`); `json.dumps(..., default=str)` serializes it as-is |
| **Frontend** (`web/src/lib/ws.ts`) | Generic topic dispatch, no typed tick shape | Exported `TickPayload` type documenting the extended wire contract |
| **ChainGrid** (`web/src/components/ChainGrid.svelte`) | Regex-parsed the contract symbol (`parseTickKey`, Fyers-style `NIFTY24AUG24500CE`) | Uses live `strike`/`option_type`/`oi` from the payload; **regex parsing removed**; ticks without chain fields (indexes/equities, `strike`/`option_type` = null) are skipped |

## 2. Key findings

### 2.1 The regex parser was already dead for options
`from_fyers()` returns `internal_symbol` = the **underlying name** (e.g. `"NIFTY"`) for option tickers, so every option tick broadcast `symbol: "NIFTY"`. `parseTickKey("NIFTY")` returned `null` → ChainGrid's `applyTick` returned early → **no live updates ever matched for options**. The "future payload" branch (explicit `strike`/`option_type` fields) was already in place (recon §2.4 note) — this wave just switched it on. The grid's `matchIndex` is keyed on `strike|side`, so the tick `symbol` is irrelevant for matching; only `strike` + `option_type` matter.

### 2.2 `_to_bus_tick` needs no change
F-CORE-001 (Wave 1 Lane A) already made `core.interfaces.Tick` and `core.data_models.Tick` the **same class**, so adapter ticks pass through `_to_bus_tick` via the `isinstance` gate untouched — the new fields ride along automatically. The fallback constructor (foreign tick shapes) was left as-is (out of scope; only `oi` forwarded there). The real adapter path never hits it.

### 2.3 `iv` cannot go live — confirmed
The HSM symbol-update feed has no IV field. IV stays REST-polled via ChainGrid's 15s `refreshSilently` (`REFRESH_MS = 15000`). Per recon §2.4 the cadence can be relaxed later; not part of this item.

### 2.4 Expiry ambiguity (pre-existing, payload-level scoping)
ChainGrid matches ticks by `strike|side` only (one expiry per grid load). A tick for the same underlying+strike+side on a *different* expiry would update the visible row. This is the acknowledged limitation of recon §2.4 option (1) (payload-level, no client→server symbol-interest signal). Symbol-routed scoping (option 2) remains a follow-up.

## 3. Verification

- `pytest tests/ -q --tb=short` → **1187 passed, 0 failed** (was 1182; +5 new tests: 3 adapter, 2 projection)
- `vitest run` → **17 passed** (14 existing + 3 new `ChainGrid.test.ts`)
- `svelte-check` → **0 errors, 0 warnings**
- `vite build` → success; committed bundle regenerated (`terminal/static/`)
- Test gates: openalgo import gate ZERO matches; no touched file > 1000 lines

## 4. Files changed (ownership scope)

**Source**
- `src/shettyxtreme/core/data_models/market_data.py` — `Tick.strike`, `Tick.option_type`
- `src/shettyxtreme/integration/fyers/data_adapter.py` — `_parse_tick` extracts + stores strike/option_type (docstring updated)
- `src/shettyxtreme/terminal/projections.py` — `WatchlistProjection` stores + broadcasts chain fields; `add()` defaults
- `src/shettyxtreme/terminal/web/src/lib/ws.ts` — `TickPayload` type export
- `src/shettyxtreme/terminal/web/src/components/ChainGrid.svelte` — live strike/option_type/oi, `parseTickKey` removed
- `src/shettyxtreme/terminal/static/` — rebuilt committed bundle (from `npm run build`)

**Tests (regression)**
- `tests/integration/test_fyers_data_adapter.py` — option CE/PE ticks extract strike/option_type (+oi); index tick → honest `None`
- `tests/terminal/test_projections.py` — tick broadcast carries chain fields; index tick → nulls; two exact-payload assertions updated
- `src/shettyxtreme/terminal/web/src/components/ChainGrid.test.ts` (new) — live tick updates LTP + OI via strike/option_type; null-chain tick ignored (no regex fallback)

## 5. Notes / non-goals

- `terminal/api/ws_bridge.py` and `ws_manager.py` unchanged — serialization already correct.
- `terminal_init.py` fallback constructor not touched (out of ownership scope; real path passes ticks through).
- Pre-existing working-tree changes in `web/src/lib/components/ui/table/table-row.svelte` (+ its test files) are **not mine** (recon roadmap #6 rest-forwarding, presumably a parallel wave) — left untouched.
- Nothing committed (per task instruction).
