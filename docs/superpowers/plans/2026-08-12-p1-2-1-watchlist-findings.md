# P1-2.1 Findings — Watchlist Cannot Add Symbols (No Search)

**Date:** 2026-08-12
**Scope:** Full watchlist flow trace — frontend UI, backend API, symbol search, storage, WebSocket/tick subscription, indices-vs-stocks differentiation.
**Version under investigation:** v0.14.0 (CHANGELOG head, 2026-08-06; suite 1244 passed). Bundle `terminal/static/assets/index-D-Nssls5.js` committed in `d92243f`.

---

## Executive summary

The bug report says *"No Add Symbol UI. No typeahead."* — **the first half is stale, the second half is true.**

- An **Add-row UI already exists** in `Watchlist.svelte` (input + exchange select + Plus button) **and is present in the committed static bundle** (verified byte-level in `index-D-Nssls5.js` — the `add-row` template, `POST /api/watchlist/{symbol}?exchange=...` call, and `aria-label="Add symbol"` button are all compiled in).
- **No symbol search / typeahead exists anywhere** — there is no `/api/symbols/search` endpoint (13 routers enumerated; the only `/search` endpoint is `/api/knowledge/search`).
- The **add flow is functionally broken** for real user input:
  1. **No dynamic feed subscription** — the Fyers HSM tick subscription is created exactly once at terminal init with the startup symbols. `WatchlistProjection.add()` only mutates an in-memory dict. A symbol added at runtime **never ticks** → permanent STALE chip (or REST-hydrated LTP that still shows STALE, because the STALE chip keys on live ticks).
  2. **Add silently accepts unresolvable symbols** — `POST /api/watchlist/RELIANCE-EQ` returns 200 with `security_id=None` instead of 4xx. `-EQ`/`-FO` suffixes are not normalized; "RELIANCE-EQ" is passed to `to_fyers` verbatim → `NSE:RELIANCE-EQ-EQ` → master gate fails → dead row.
  3. **No persistence** — the watchlist is in-memory only; runtime adds vanish on restart (YAML seeds only the 3 indices at startup).

---

## 1. Current watchlist architecture

### 1.1 Storage — in-memory only

`WatchlistProjection` (`src/shettyxtreme/terminal/projections.py:23`) holds `self._data: dict[str, dict[str, Any]]`. Methods: `add(symbol, exchange, security_id)` (insert-only into the dict), `remove`, `get`, `get_item`, `subscribe(bus)` (listens `Topic.MARKET_DATA_TICK`). No DB, no file writes.

**Seed** (`src/shettyxtreme/terminal/api/app.py:422-440`): at lifespan, reads `configs/default_watchlist.yaml`, loads **only the `indices:` block** (NIFTY / BANKNIFTY / FINNIFTY, exchange `NSE_FNO`, internal symbol = `security_id`) into the projection. The `options:` block (`auto_discover: true` ATM CE/PE) is **never loaded** by app.py — vestigial.

`configs/default_watchlist.yaml` comment: `security_id` holds the *internal* symbol; the Fyers resolver converts at runtime (`NIFTY → NSE:NIFTY50-INDEX`, etc.).

**Consequence:** adds/removes are session-only. Restart reverts to the 3 seeded indices.

### 1.2 API — `/api/watchlist` (`watchlist_router.py`)

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/watchlist` | `list[WatchlistItem]`; REST hydration backfills ltp/change_pct when the live feed is idle (10s TTL cache, `_hydrate_from_rest` line 79) |
| POST | `/api/watchlist/{symbol}?exchange=` | `add_to_watchlist` (line 187) — resolves symbol, **always returns 200**, stores in projection |
| DELETE | `/api/watchlist/{symbol}` | 204, projection remove |

`WatchlistItem` (`terminal/api/models.py:14`): `symbol, exchange, ltp, change_pct, volume, timestamp, security_id`.

**`_resolve_security_id` (line 164) — the add-path core:**
- If symbol contains `:` → pass-through (already a Fyers ticker).
- Else `instrument_type = "INDEX" if s.upper() in _INDEX_SYMBOLS else "EQUITY"` — `_INDEX_SYMBOLS = {NIFTY, BANKNIFTY, FINNIFTY}` (line 27). **Only exact big-3 names are INDEX; everything else is EQUITY.**
- Calls `resolver.to_fyers(s, exchange, instrument_type)` purely as a *validation gate* (return value discarded). `ValueError` (e.g. `SymbolNotFoundError` from the master round-trip gate) → caught → returns `None`.
- On `None`: logs a warning and **still adds** with `security_id=None` (line 197). No 4xx. No dedup concern (dict-keyed, idempotent).

### 1.3 Frontend — `Watchlist.svelte`

- Add-row (lines 196-216): `Input` (placeholder `SYMBOL`, Enter triggers add) + `Select` exchange (`NSE` / `NSE_FNO` labeled NFO / `BSE`, default `NSE`) + icon `Button` (`aria-label="Add symbol"`).
- `add()` (lines 127-138): `POST /api/watchlist/${symbol.toUpperCase()}?exchange=${newExchange}`, clears input, reloads. Errors render via `ErrorState`.
- Row rendering: symbol/exchange, LTP colored by `change_pct` (red up / green down — Indian convention intact), `% chg`, remove `X` button, STALE chip when no tick seen in 60s (`lastSeenMs` seeded from REST `timestamp`).
- **No typeahead, no suggestions, no validation before POST.** The exchange default is `NSE` — but the seeded indices live on `NSE_FNO`, and `_resolve_symbol` in the data adapter resolves everything against `"NSE_FNO"` (`data_adapter.py:272`), so the frontend exchange selection mostly does not match what the backend uses for resolution.

### 1.4 The committed bundle is NOT stale

Verified in `src/shettyxtreme/terminal/static/assets/index-D-Nssls5.js`:
- `<div class="add-row ...">` template with SYMBOL input, NSE/NSE_FNO/BSE select items, Plus button, `aria-label:"Add symbol"`.
- `B()` function: `tn(\`/api/watchlist/${encodeURIComponent(L)}?exchange=${encodeURIComponent(s(c))}\`)` then reload.
- Remove + STALE chip + EmptyState "Add one above" all present.

So a fresh user does see an add UI. The functional failures (below) are why "cannot add symbols" reads true.

---

## 2. What is missing / broken

### 2.1 ❌ No symbol search endpoint (the "No typeahead" claim — confirmed)

All 13 routers enumerated: `analytics, auth, execution, health, intelligence, learning, market, knowledge, postback, research, watchlist, settings, scanner`. **There is no `/api/symbols*` or `/api/instruments*` router.** The only search endpoint is `GET /api/knowledge/search` (FTS5 over knowledge docs — unrelated).

**Reusable backing already exists:** `FyersInstrumentMaster.search()` (`instrument_master.py:434`) — SQLite query on `internal_symbol` with filters for `exchange`, `instrument_type`, `expiry`, `strike`, `option_type`, ordered by `fyers_symbol`. Also `lookup()` (line 408), `get_lot_size()` (line 486, prefers INDEX row), `count_instruments()` (line 401). The master is a **public-download local SQLite mirror**, refreshed automatically by `init_instrument_master()` (`terminal/api/instrument_init.py`) — available with only an access token, so search can work pre-feed.

### 2.2 ❌ Add endpoint is naive (silent 200 on unresolvable input)

Walk-through of the three inputs the task names:

| User types | `_resolve_security_id` behavior | Result |
|---|---|---|
| `RELIANCE` (plain) | EQUITY → `to_fyers("RELIANCE","NSE","EQUITY")` → `NSE:RELIANCE-EQ` → master hit | ✅ works; hydration resolves too (`master.search("RELIANCE")` → EQUITY row) |
| `RELIANCE-EQ` | EQUITY → `to_fyers("RELIANCE-EQ","NSE","EQUITY")` → `NSE:RELIANCE-EQ-EQ` → **master miss** → `SymbolNotFoundError` → `None` | ⚠️ **200 with `security_id=None`** — dead row, ltp 0, STALE forever (hydration: `master.search("RELIANCE-EQ")` misses too; internal_symbol column is `RELIANCE`) |
| `NIFTY-FO` | NOT in `_INDEX_SYMBOLS` → EQUITY → `NSE:NIFTY-FO-EQ` → **miss** → `None` | ⚠️ Same silent dead row — futures never handled on the add path |
| `NIFTY` | INDEX → `NSE:NIFTY50-INDEX` | ✅ adds; REST hydration works, but **no live ticks** (see 2.3) → STALE chip anyway |
| `NSE:NIFTY50-INDEX` | contains `:` → pass-through | ✅ best case, but no user types that |

Root cause: `_resolve_security_id` never (a) strips/normalizes `-EQ`/`-FO`/`-INDEX` suffixes, (b) infers instrument type from the input (the `_INST_RE` ticker-suffix logic at `instrument_master.py:105` — `-INDEX`/`FUT`/`CE|PE`/`-[A-Z]{1,2}` — exists but is only used by `_derive_instrument_type`, not by the add path), nor (c) returns 4xx when the resolver rejects the symbol. Same `_INDEX_SYMBOLS`-or-else-EQUITY shortcut is duplicated in `market_router.py:122` and `_util.py:24` — three copies of the same incomplete heuristic.

### 2.3 ❌ No dynamic feed subscription (the biggest functional gap)

The live tick pipeline:
1. `init_terminal_adapters` (`terminal/api/terminal_init.py:194-213`) registers `_publish_market_tick` (EventBus `MARKET_DATA_TICK` publisher) and calls `data_adapter.subscribe_ticks(list(watchlist_data.keys()), cb)` **once** — with whatever is in the projection at that moment (the 3 YAML indices).
2. `FyersDataAdapter.subscribe_ticks` (`data_adapter.py:269`) resolves each symbol via `_resolve_symbol` (prefers INDEX row, then EQUITY, from `master.search`) and delegates to `FyersDataSocketWrapper.subscribe(resolved, "SymbolUpdate")`.
3. `FyersDataSocketWrapper` (`data_socket.py:205`) appends to `self._subscriptions[dt]` (idempotent per symbol) and pushes to the live SDK socket; the supervisor re-applies `_subscriptions` on every reconnect (`_apply_subscriptions`, line 330) — **the registry is already reconnect-safe and designed for incremental mutation.**

But nothing mutates it after init:
- The **only** caller of `subscribe_ticks` is `terminal_init.py:202`.
- `FyersDataAdapter.unsubscribe` (line 293) has **zero callers**.
- `WatchlistProjection.add()`/`remove()` never touch the adapter/socket.
- `app.state.terminal_initialized` (terminal_init.py:266) pins after first success → re-running init wouldn't help either.

**Net effect:** any symbol added at runtime is invisible to the Fyers HSM feed. `WatchlistProjection.on_market_data` only updates rows that tick, so the new row shows `—` LTP, and the 60s `lastSeenMs` check paints the STALE chip. REST hydration (`_hydrate_from_rest`, watchlist_router.py:79) can backfill LTP for resolvable symbols (plain names like `NIFTY`/`RELIANCE`), but only on GET, cached 10s, and the STALE chip still shows because it keys on live ticks (`lastSeenMs` seeded from REST `timestamp` — which is `None` for a freshly added row).

### 2.4 ❌ No persistence

Adds/removes never leave `WatchlistProjection._data`. `configs/default_watchlist.yaml` is read-only at startup. A user's custom watchlist is lost on every restart.

### 2.5 Indices vs Stocks (task question 6)

**Current differentiation:**
- Input side: `_INDEX_SYMBOLS` exact match → `INDEX`; everything else `EQUITY` (`watchlist_router.py:179`, `market_router.py:122`, `_util.py:24`).
- Resolution side: `FyersSymbolResolver.to_fyers` maps internal→ticker: `NIFTY → NSE:NIFTY50-INDEX`, `RELIANCE → NSE:RELIANCE-EQ` (`symbols.py:56-60`, `256-259`); validated by exact master lookup (raises `SymbolNotFoundError`).
- `data_adapter._resolve_symbol` (`data_adapter.py:128`) prefers the INDEX row, then EQUITY, from `master.search(name)`.

**What's missing for F&O (NIFTY-FO):**
- No `FUTURES` path on the add flow. To subscribe index futures you need the **nearest monthly expiry contract** (e.g. `NSE:NIFTY26AUGFUT`) plus **lot size**.
- The master has `get_lot_size()` (prefers INDEX row; for a concrete contract use `lookup(ticker)["lot_size"]`) and `search(instrument_type="FUTURES")` — but **no "nearest expiry" helper**: you'd compute `min(expiry)` over `search(symbol, instrument_type="FUTURES")` rows (master `expiry` is ISO date) and build the monthly ticker via `to_fyers(..., "FUTURES", expiry=nearest, is_monthly=True)` (monthly detection `is_monthly_expiry`, symbols.py:195).
- The options chain already achieves "nearest by default" by passing `expiry=""` to Fyers (`data_adapter.get_option_chain` omits the `timestamp` param → Fyers returns the nearest expiry; this was the v0.14.0 500-fix, CHANGELOG line 13). Futures have no such REST default — a concrete ticker must be derived from the master.
- The watchlist row itself shows only symbol/exchange/LTP/change — no expiry/lot-size display. Expiry + lot-size live in the chain/strategy-hint path (`execution_router.py:151` uses `lot_size` hints for lot math). So "equity LTP only vs index nearest-monthly + lot size" is really about **which ticker gets subscribed and which metadata rides alongside** — currently neither is implemented for futures.

---

## 3. Reusable existing code (do not reinvent)

| Asset | Location | Why it helps |
|---|---|---|
| `FyersInstrumentMaster.search()` | `instrument_master.py:434` | SQLite-backed symbol search w/ filters — direct backing for `GET /api/symbols/search` |
| `FyersInstrumentMaster.lookup()` | `instrument_master.py:408` | Exact-ticker validation / row metadata (lot_size, expiry, type) |
| `FyersInstrumentMaster.get_lot_size()` | `instrument_master.py:486` | Lot size for sizing metadata |
| `init_instrument_master()` | `terminal/api/instrument_init.py` | Auto-refreshing public master — search works without a valid token |
| `FyersSymbolResolver.to_fyers/from_fyers` | `symbols.py:109/132` | Canonical internal↔ticker conversion with master round-trip gate (`SymbolNotFoundError`) |
| `_INST_RE` suffix patterns | `instrument_master.py:105` | `-INDEX`/`FUT`/`CE\|PE`/`-[A-Z]{1,2}` — the input-normalization logic that should replace the `_INDEX_SYMBOLS`-or-else-EQUITY shortcut |
| `is_monthly_expiry` + monthly FUT encoding | `symbols.py:195`, `symbols.py:260-269` | Building `NSE:NIFTY26AUGFUT` from the nearest expiry |
| `FyersDataSocketWrapper.subscribe()/unsubscribe()` | `data_socket.py:205/223` | Incremental, idempotent, supervisor re-applies on reconnect — exactly what dynamic add/remove needs |
| `FyersDataAdapter.subscribe_ticks()/unsubscribe()` | `data_adapter.py:269/293` | Adapter-level entry point (unsubscribe currently unused) |
| `_hydrate_from_rest` + `_hydration_cache` | `watchlist_router.py:79/39` | Immediate first-paint LTP after add (call `get_quotes([security_id])` on POST) |
| YAML seeding pattern | `app.py:422-440` | First-run seed; extend to persist adds |
| `core/knowledge/lexicons.py` | curated NSE symbols | Offline suggestion fallback before/without a fresh master |

---

## 4. Proposed fix approach (algorithm, not code)

### Step 1 — Symbol search endpoint (unblocks typeahead)
`GET /api/symbols/search?q=&instrument_type=&exchange=&limit=` on a new `symbols_router` (or `market_router`):
- Back with `instrument_master.search(q, exchange=..., instrument_type=...)`; add a prefix/substring `LIKE` fallback (`internal_symbol LIKE 'q%'`) when exact filter returns nothing.
- Dedupe per `(internal_symbol, instrument_type)` (a plain name has INDEX + FUTURES + many OPTION rows — return one row per type, or the INDEX/EQUITY preferred row like `data_adapter._resolve_symbol` does).
- Response row: `{symbol (internal), exchange, instrument_type, fyers_symbol, expiry, strike, lot_size}`.
- `503` with a clear message when `app.state.instrument_master` is None (no login yet) — mirroring the market-router `503` contract; fall back to `lexicons.py` curated list when the master mirror is empty.

### Step 2 — Harden the add endpoint (kill silent dead rows)
- Normalize input before resolution: Fyers ticker (`NSE:...` → `from_fyers`); `-EQ`/`-BE`/`-INDEX`/`-FO`/`-FUT`/`CE`/`PE` suffix (strip/infer via `_INST_RE`-style logic); plain name → `master.search` first to pick the preferred row.
- Infer `instrument_type` from the normalized name + master, not from the `_INDEX_SYMBOLS`-or-else-EQUITY shortcut (consolidate the three duplicate copies).
- Return `404` (unknown) / `422` (unparseable) instead of the current silent `security_id=None` 200. Keep the `:` pass-through for expert ticker input.
- Preserve the resolver round-trip gate — never add a row whose `to_fyers` fails.

### Step 3 — Dynamic feed subscription on add/remove (the core fix)
- After `proj.add(...)` succeeds, resolve the security → Fyers ticker and call `data_adapter.subscribe_ticks([internal_symbol], _publish_market_tick)` — reuse the **same single EventBus callback** from terminal_init (capture it, or make the bridge subscribable per-symbol).
- On `proj.remove(...)`, call `data_adapter.unsubscribe(symbol)`.
- `FyersDataSocketWrapper` already handles incremental, reconnect-safe subscription — no socket-layer changes needed.
- Optionally clear/re-seed the `_hydration_cache` entry and fire one `get_quotes` for instant first paint.

### Step 4 — Index futures (NIFTY-FO) support
- On add of an F&O request (`-FO` suffix, `NSE_FNO` exchange, or a search-selected FUTURES row): derive nearest monthly expiry = `min(expiry)` over `master.search(symbol, instrument_type="FUTURES")`; build the monthly FUT ticker via `to_fyers(symbol, exchange, "FUTURES", expiry=nearest, is_monthly=True)`; subscribe that; store `expiry` + `lot_size` (from the row) on the projection entry so the chain/execution path can reuse them (the `WatchlistItem` model gains optional `expiry`/`lot_size` fields).
- Equity stays as-is (spot equity ticker, no expiry).

### Step 5 — Persistence
- Persist adds/removes to a small JSON/SQLite file (e.g. `data/watchlist.json`) written on every mutation; at startup merge `default_watchlist.yaml` seed + persisted overrides. The settings-store pattern (`data/settings.db`) is the in-repo precedent.

### Step 6 — Frontend
- Keep the existing add-row; replace free-text-only input with a **typeahead dropdown** fed by Step 1 (debounced ≥200ms, keyboard navigable — reuse the existing `Input`/`Select` primitives and DESIGN.md tokens).
- Show the resolved `fyers_symbol` + `instrument_type` as confirmation before commit; disable Add until a valid match.
- Surface 4xx errors from Step 2 (currently the input is only error-surfaced via `ErrorState` on load failure).
- Default the exchange select to match the symbol type picked (indices/F&O → `NSE_FNO`, equity → `NSE`).

---

## 5. Verification / test notes

- Existing coverage is happy-path only and **never exercises the resolver or feed**: `tests/wave3/test_api.py:109-142` POST plain internal names with no `symbol_resolver` on `app.state` (so `_resolve_security_id` returns the symbol unchanged); `tests/wave7/test_watchlist_hydration.py` covers REST backfill only; `tests/terminal/test_projections.py` covers tick→row updates for pre-existing rows; `tests/wave7/test_terminal_init.py` covers the one-shot bridge but asserts the empty-watchlist case deliberately skips the bridge.
- New tests to add with the fix: search endpoint (master-backed + no-master 503), add with `-EQ`/`-FO`/plain/ticker inputs, unresolvable → 4xx, dynamic subscribe/unsubscribe invoked on add/remove (fake socket asserting registry mutation), nearest-monthly FUT selection for `NIFTY-FO`, persistence round-trip.
- Manual gate after change: full suite command from AGENTS.md; `npm run check` + `npm run build` (bundle must be committed per repo convention).

## Files touched in this trace (read-only)

- `src/shettyxtreme/terminal/web/src/components/Watchlist.svelte`
- `src/shettyxtreme/terminal/api/watchlist_router.py`
- `src/shettyxtreme/terminal/api/app.py` (lifespan seed, state wiring)
- `src/shettyxtreme/terminal/api/terminal_init.py` (one-shot bridge)
- `src/shettyxtreme/terminal/api/market_router.py`, `instrument_init.py`, `models.py`
- `src/shettyxtreme/terminal/projections.py`
- `src/shettyxtreme/integration/fyers/{data_adapter,data_socket,symbols,instrument_master,_util}.py`
- `configs/default_watchlist.yaml`
- `src/shettyxtreme/terminal/static/assets/index-D-Nssls5.js` (bundle — add-row verified present)
- Tests: `tests/wave3/test_api.py`, `tests/wave7/test_watchlist_hydration.py`, `tests/wave7/test_terminal_init.py`, `tests/terminal/test_projections.py`, `tests/integration/test_fyers_symbols.py`
