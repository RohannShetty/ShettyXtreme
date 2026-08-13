# P1-2.3 Findings — SERP / Symbol Search Endpoint Missing (v0.14.0)

**Date:** 2026-08-12
**Scope:** Trace symbol resolution end-to-end; identify what a symbol-search
endpoint (aliases + fuzzy + natural contract parse) needs.

## TL;DR

- **No `GET /api/symbols/search` exists anywhere.** `grep /api/symbols` → zero
  hits. No router, no response model, no frontend call.
- The instrument master `search()` is **exact-match only** (`internal_symbol = ?`).
  No `LIKE`, no FTS5 on the instrument DB (FTS5 exists only in `knowledge.db`).
- **All 5 requested aliases already exist** — `BANK`/`BNF`→`BANKNIFTY`,
  `FIN`→`FINNIFTY`, `MIDCAP`→`MIDCPNIFTY`, `NIFTYNEXT50`→`NIFTYNXT50` — in
  `src/shettyxtreme/core/knowledge/lexicons.py` (`SYMBOL_ALIASES`). **But they
  are only used by the knowledge tagger** (`knowledge/tagger.py`), never by the
  symbol-resolution/trading path. Typing `BNF` in Watchlist or ChainGrid fails
  resolution today.
- The "nifty 24k ce → NIFTY 24000 CE nearest weekly" fuzzy case has **no
  parser and no nearest-weekly selector** anywhere.

---

## 1. Current symbol resolution

### 1.1 Instrument master — `src/shettyxtreme/integration/fyers/instrument_master.py`

Local SQLite mirror of the 7 public Fyers daily masters (`DEFAULT_MASTERS`),
refreshed on a 24h staleness gate (F-INT-008).

- Table `fyers_instruments`:
  `fyers_symbol` (PK, raw ticker `NSE:SBIN-EQ`), `internal_symbol`, `exchange`,
  `instrument_type` (EQUITY/INDEX/FUTURES/OPTION/UNKNOWN), `expiry` (ISO),
  `strike` (REAL), `option_type` (CE/PE/XX), `lot_size`, `tick_size`, `isin`,
  `raw_json`.
- Index: `idx_fi_internal ON fyers_instruments(internal_symbol, exchange)`
  (line 204-207). **No FTS5, no other index.**
- `lookup(ticker)` — exact PK lookup (handles URL-encoded input).
- `search(internal_symbol, exchange, instrument_type, expiry, strike, option_type)`
  (line 434) — **exact match** `internal_symbol = ?` plus optional filter
  clauses; rows ordered by `fyers_symbol`. Used by `get_lot_size` (line 486)
  and by the data adapter's `_resolve_symbol` (master-first resolve).
- `_row_to_dict` / `_COLUMNS` (line 510 / 64) — the row-shaping helpers a
  search endpoint would reuse.

### 1.2 Symbol resolver — `src/shettyxtreme/integration/fyers/symbols.py`

- `to_fyers(internal, exchange, type, expiry, strike, option_type, series)` —
  constructs the Fyers ticker; validates against the master when bound
  (`SymbolNotFoundError` on unknown, the weekly-vs-monthly gate).
- `_INDEX_INTERNAL_TO_TICKER` (line 56): `NIFTY→NIFTY50-INDEX`,
  `BANKNIFTY→NIFTYBANK-INDEX`, `FINNIFTY→FINNIFTY-INDEX`. MIDCPNIFTY/NIFTYNXT50
  fall through to `<NAME>-INDEX` (correct, just not enumerated).
- `from_fyers(ticker)` — regex parse back to `{internal_symbol, exchange,
  instrument_type, expiry, strike, option_type, is_monthly}`.
- **No alias table here.** `BNF` → `_index_ticker("BNF")` → `BNF-INDEX` → not
  in master → `SymbolNotFoundError`.
- `_infer_instrument_type` (`trading_adapter.py:62`): only NIFTY/BANKNIFTY/
  FINNIFTY classify as INDEX; everything else EQUITY.

### 1.3 Aliases — `src/shettyxtreme/core/knowledge/lexicons.py`

```python
SYMBOL_ALIASES: dict[str, str] = {
    "BANK": "BANKNIFTY", "BNF": "BANKNIFTY", "FIN": "FINNIFTY",
    "MIDCAP": "MIDCPNIFTY", "NIFTYNEXT50": "NIFTYNXT50",
}
NSE_SYMBOLS: set[str] = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}
normalize_symbol(token)  # strip NSE:/NSE_FNO:/BSE: → upper → alias-map → stopword/NSE_SYMBOLS gate
```

- **Exactly the 5 aliases requested.** Covered by
  `tests/wave9/test_knowledge_lexicons.py` (`test_normalize_symbol_alias_maps_to_canonical`).
- **Reach is limited to knowledge tagging** (`knowledge/tagger.py:47`). The
  trading path (`watchlist_router`, `market_router`, `data_adapter`,
  `trading_adapter`) never consults it. D12 note: `core/` is import-safe
  everywhere, so promoting/reusing this is fine.

### 1.4 Wiring & endpoint consumers

- `terminal_init.py:136-159` — `FyersSymbolResolver(init_instrument_master())`
  → `app.state.symbol_resolver` / `app.state.instrument_master` (wired on
  lifespan AND post-OAuth login; `app.py` seeds the same state at line 233-234).
- `watchlist_router._resolve_security_id` (line 164) — resolver round-trip;
  failure logs a warning and **still adds the row with `security_id=None`**
  (no ticks until resolver knows it).
- `market_router._resolve_symbol` (line 106) — resolver round-trip; tickers
  containing `:` pass through.
- `data_adapter._resolve_symbol` (line 128) — **master-first**: `master.search(s)`
  exact → prefer INDEX row → else `to_fyers` fallback. Used by
  `get_quotes`, `get_ohlc`, `get_ltp`, `get_option_chain`.
- `get_option_chain(underlying, expiry)` (line 425) — `_resolve_symbol` then
  `/data/options-chain-v3`; empty expiry → Fyers picks the nearest expiry.
  Exposed at `GET /api/intelligence/options?symbol=&expiry=`.

### 1.5 Frontend symbol input

- `Watchlist.svelte` add-row — plain text `<Input placeholder="SYMBOL">`
  (line 196-216), POSTs `/api/watchlist/{symbol}`. No autocomplete.
- `ChainGrid.svelte` — plain `<Input placeholder="SYMBOL">` (line 314-320),
  commits to `/api/intelligence/options`. No autocomplete.
- `lib/selection.ts` — `selectedSymbol` store `{symbol, exchange}`; set by
  Watchlist row select, read by ChainGrid/Header. A search result would set
  this to drive the chain.
- `KnowledgePanel.svelte` (line 132-165) — the existing **debounced search +
  keyboard-nav hit-list** UX precedent (300ms debounce, Enter, arrow nav,
  `/api/knowledge/search?q=&limit=`).

---

## 2. What's missing

| Gap | Evidence |
|---|---|
| **No `/api/symbols/search` endpoint** | `grep "/api/symbols"` → 0 matches; `app.py:553-565` includes 13 routers, none symbol-related |
| **No fuzzy/prefix match in the master** | `search()` builds `internal_symbol = ?` only (instrument_master.py:458); no LIKE, no FTS5 in `fyers_instruments.db` |
| **No alias resolution in trading path** | `SYMBOL_ALIASES` only consumed by `knowledge/tagger.py`; `BNF` fails `to_fyers` (→ `SymbolNotFoundError`) |
| **No natural contract parser** | nothing tokenizes `"nifty 24k ce"` → `{NIFTY, 24000, CE}`; chain endpoint takes symbol+expiry only, strikes never in the request |
| **No nearest-weekly expiry selector** | `get_option_chain` delegates to Fyers' nearest-expiry default; no local "prefer weekly over monthly" logic |
| **No frontend search UI** | both Watchlist and ChainGrid are plain inputs; no combobox/autocomplete anywhere |

---

## 3. Proposed fix approach (algorithm-level)

Layered, bottom-up — each layer is independently shippable:

### Layer 1 — Alias resolution in the trading path (smallest, highest value)

Promote the canonical-symbol table into the resolver layer. Either import
`SYMBOL_ALIASES`/`NSE_SYMBOLS` from `core/knowledge/lexicons.py` (D12-safe) or
mirror the map in `integration/fyers/symbols.py`.

Pipeline (single function, applied in `watchlist_router._resolve_security_id`,
`market_router._resolve_symbol`, `data_adapter._resolve_symbol` before the
master/resolver round-trip):

```
query → UPPERCASE → strip exchange prefix (NSE:/NSE_FNO:/BSE:) → alias-map → canonical
```

A `BNF` watchlist add then resolves `BANKNIFTY` → `NSE:NIFTYBANK-INDEX` and
ticks normally. Zero API surface change; existing resolver round-trip stays the
validation gate.

### Layer 2 — `GET /api/symbols/search?q=&limit=` endpoint

1. **New query method on `FyersInstrumentMaster`** — `search_prefix(q, limit)`
   (or `search_fuzzy`):
   - alias-map + uppercase the query first (Layer 1 helper);
   - prefix match `internal_symbol LIKE 'Q%'` (can use `idx_fi_internal`) +
     substring `LIKE '%Q%'` fallback for mid-token matches — a full scan over
     ~100k rows is acceptable on a local workstation; add FTS5 later if it
     isn't (see §4 precedent in `knowledge.db`).
   - filter out `UNKNOWN` instrument_type noise; cap with `LIMIT`; reuse
     `_row_to_dict`/`_COLUMNS`.
2. **New `symbols_router.py`** — `APIRouter(prefix="/api/symbols")`, handler
   reads `app.state.instrument_master` (already on state; degraded → 503 with
   the same honesty as the market router). Response model in
   `terminal/api/models.py`: `{query, canonical, hits: [internal_symbol,
   fyers_symbol, exchange, instrument_type, expiry, strike, option_type,
   lot_size, tick_size]}` — mirroring `WatchlistItem`/`MarketBar` conventions.
3. Register in `app.py` include list.

### Layer 3 — Natural contract parse ("nifty 24k ce" → NIFTY 24000 CE nearest weekly)

A small regex tokenizer in the same house style as `symbols.py`:

```
1. underlying  = leading alpha token(s)            → alias-map → canonical
2. strike      = "24k"/"24.5k"/"24,000"/"24500"    → normalize to int
3. option_type = ce|pe|call|put                    → CE/PE
4. expiry      = optional explicit (ddMMMyy / ISO); absent → nearest weekly
```

Nearest-weekly selection against the master:

```
rows = master.search(canonical, instrument_type="OPTION")
       filtered to strike + option_type
group by expiry; prefer future expiries only
prefer WEEKLY over MONTHLY (is_monthly semantics from symbols.py:
    monthly ⇔ expiry is the last weekday-of-month; skip those when a weekly exists)
→ resolve final ticker via to_fyers(..., is_monthly=False) + master validation
```

Output: a resolved contract descriptor `{internal_symbol, strike, option_type,
expiry, fyers_symbol, lot_size}`. Where it plugs in: a dedicated
`GET /api/symbols/resolve?q=` (or the same endpoint returning a "best match"
when the query contains strike/option tokens). This is the piece that makes the
SERP actually useful for options.

### Layer 4 — Frontend integration (both surfaces)

- Shared `SymbolSearch.svelte` combobox — debounced fetch to
  `/api/symbols/search` (copy the 300ms debounce + keyboard-nav pattern from
  `KnowledgePanel.svelte`), dropdown of hits showing
  `internal_symbol · exchange · type` in mono.
- **WatchlistRail** (`Watchlist.svelte` add-row): replace the plain input;
  on select → `POST /api/watchlist/{symbol}?exchange=...` (existing endpoint,
  unchanged).
- **ChainGrid** symbol input: replace the plain input; on select → set
  `symbol` + `commit()`. Also set `selectedSymbol` (`lib/selection.ts`) so the
  header/chain stay in sync.
- Optional: a CommandPalette entry ("Go to symbol…") reusing the same
  component.

---

## 4. Reusable existing code

| Asset | Where | Reuse for |
|---|---|---|
| `SYMBOL_ALIASES` + `NSE_SYMBOLS` + `normalize_symbol` | `core/knowledge/lexicons.py:20-110` | Layer 1 alias map (already the exact 5 aliases; tests in `tests/wave9/test_knowledge_lexicons.py`) |
| `FyersInstrumentMaster.search()` + `_row_to_dict` + `_COLUMNS` | `instrument_master.py:434/510/64` | Layer 2 fuzzy variant — same row shape, add LIKE clause |
| `data_adapter._resolve_symbol` (master-first, INDEX-preferred) | `data_adapter.py:128-151` | Canonical resolve order for the endpoint + Layer 3 ticker construction |
| `FyersSymbolResolver.to_fyers` + `_INDEX_INTERNAL_TO_TICKER` + monthly/weekly encoding | `symbols.py` | Layer 3 weekly-vs-monthly selection and validation gate |
| FTS5 virtual-table pattern | `knowledge/store.py:42` (`docs_fts`) | Optional later: FTS5 index on `fyers_instruments` if LIKE is too slow |
| Debounce + keyboard-nav search UX | `KnowledgePanel.svelte:132-165` | Layer 4 combobox behavior |
| `selectedSymbol` store | `lib/selection.ts` | Wiring a chosen symbol into ChainGrid/Header |
| Response-model conventions | `terminal/api/models.py` (`WatchlistItem`, `MarketBar`) | `SymbolSearchResponse` / `SymbolResolveResponse` models |

---

## 5. Test impact (manual gate — no CI)

- **New:** `tests/integration/test_fyers_instrument_master.py` — prefix/substring
  search cases; alias-aware search (BNF → BANKNIFTY rows).
- **New:** `tests/wave10`-style router tests for `/api/symbols/search`
  (mirror `tests/wave9/test_knowledge_api.py`), plus a `resolve` parser test
  ("nifty 24k ce", "BANKNIFTY 47000 PE", plain "RELIANCE").
- **Existing, unaffected:** exact-match `search()` tests (lines 92-113 of
  `test_fyers_instrument_master.py`) — the exact path is preserved.
- **Existing, now-relevant:** `tests/wave9/test_knowledge_lexicons.py` alias
  assertions — already assert the exact alias table; if the map is promoted,
  keep a single source of truth so these don't drift.

## 6. Notes

- Version drift is unrelated but visible: `app.py:525` says `0.13.0`, AGENTS.md
  tracks the 0.7.0/0.8.0 drift — out of scope for this finding.
- The Fyers chain endpoint already returns the nearest expiry when none is
  requested — Layer 3's nearest-weekly logic is a **local** preference (weekly
  > monthly) that Fyers itself does not express, so it must be computed from
  the master.
