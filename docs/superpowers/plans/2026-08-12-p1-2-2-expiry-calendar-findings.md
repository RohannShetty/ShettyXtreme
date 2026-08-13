# P1-2.2 Findings — Expiry Calendar Intelligence is Missing

**Date:** 2026-08-12
**Scope:** Instrument master schema, expiry API surface, option-chain UI, default-selection logic, Fyers expiry capability.
**Result:** Confirmed missing. There is no expiry calendar anywhere — no endpoint, no weekly/monthly calendar logic, no distinct-expiry enumeration. The chain UI learns expiries one-at-a-time from chain responses; the default is "whatever Fyers returns".

---

## 1. Current expiry handling

### 1.1 Instrument master — `src/shettyxtreme/integration/fyers/instrument_master.py`

**Schema** (`fyers_instruments`, lines 78–92):

| column | type | notes |
|---|---|---|
| `fyers_symbol` | TEXT PK | raw ticker `NSE:NIFTY24OCT25000CE` |
| `internal_symbol` | TEXT | `NIFTY`, `SBIN`, … |
| `exchange` | TEXT | `NSE`/`BSE`/`MCX` (ticker prefix) |
| `instrument_type` | TEXT | `EQUITY`/`INDEX`/`FUTURES`/`OPTION`/`UNKNOWN` |
| `expiry` | TEXT | **ISO `YYYY-MM-DD`, NULL for equity/index** (line 27, 84) |
| `strike` / `option_type` / `lot_size` / `tick_size` / `isin` / `raw_json` | | |

Key facts:
- **Expiry dates ARE stored** — parsed from the master's epoch `expiryDate` via `_parse_expiry()` (line 113) into ISO strings. So the data to build a calendar is present.
- **No weekly/monthly flag in the schema.** A row is monthly/weekly only by inference (see `is_monthly_expiry`, §1.2).
- **No distinct-expiry query.** Methods are `lookup()`, `search()` (filters: internal_symbol, exchange, instrument_type, expiry, strike, option_type), `get_lot_size()`, `count_instruments()`. No `DISTINCT expiry` / no "list expiries for underlying X" method (verified: no DISTINCT/GROUP BY anywhere in the file). A caller *can* derive distinct expiries by `search(symbol, instrument_type="OPTION")` and reading `expiry` off each row, but nobody does.
- Refresh: `ensure_fresh()` (24h staleness, F-INT-008), public JSON download — works with only an access token.

### 1.2 Weekly vs monthly distinction — `integration/fyers/symbols.py`

- `is_monthly_expiry(expiry)` (line 195): a date is **monthly iff it is the last occurrence of its weekday in the month** (`(d + 7).month != d.month`). Comment notes it covers the 2024 Thursday convention and post-2025 Tuesday convention.
- Used **only for ticker encoding** in `to_fyers()` (line 262/278) — decides monthly (`24OCT`) vs weekly (`24O08`) Fyers symbol format. It is a *per-date* heuristic, **not** a per-underlying calendar. It cannot encode "BANKNIFTY weekly expiry day is Mon/Tue/Wed/Thu" or "stock options are monthly-only" — those rules don't exist anywhere.
- `from_fyers()` returns `is_monthly` (True/False/None) so parse/construct round-trip exactly (F-INT-012).

### 1.3 API endpoints — `terminal/api/intelligence_router.py`

No expiry-calendar endpoint. Existing `/api/intelligence/*` routes (lines 330–453):

| endpoint | purpose | expiry handling |
|---|---|---|
| `GET /regime` | market regime projection | none |
| `GET /signal` | signal snapshot | none |
| `GET /voters` | strategy voter breakdown | none |
| `GET /options` | option chain | `expiry` query param, optional; empty → adapter omits `timestamp` → **Fyers returns nearest expiry** |
| `GET /strategy-hint` | strategy hint + EV | always fetches NIFTY chain with `expiry=None` (nearest) |
| `GET /options-summary` | max pain / PCR / IV rank | uses cached `app.state.options_chain` or fetches |

Helper `_parse_expiry_date()` (line 56) parses ISO / Fyers-symbol-style / epoch strings — reusable for calendar date parsing.

**Full API surface** (app.py:553–565): watchlist, intelligence, execution, scanner, health, auth, postback, settings, learning, research, knowledge, analytics, market routers. None exposes expiries beyond the `?expiry=` param on `/options`.

### 1.4 Option chain UI — `terminal/web/src/components/ChainGrid.svelte`

- **There IS an expiry selector dropdown** (lines 321–338): a `Select` with `SelectItem`s over `expiries: string[]`.
- **Population is passive/learned, not a calendar:** `expiries` is filled only from `resp.expiry` in `applyResponse()` (line 230) and `refreshSilently()` (line 250) — i.e. the list grows **one entry per distinct expiry the server has happened to return** across loads. It starts empty; the dropdown is only rendered when `expiries.length > 0`; otherwise a free-text `EXPIRY (optional)` input is shown (lines 340–346).
- No weekly/monthly grouping, no labels, no upcoming-calendar view. Items are plain ISO date strings, sorted lexically (line 230/251 `.sort()`), not chronologically-aware.
- Grid loads `/api/intelligence/options?symbol=…&expiry=…` (line 216); response aligns the committed request with the server-resolved expiry (lines 235–237).
- Tests (`ChainGrid.test.ts`) only assert a strike renders; no expiry-dropdown behavior is covered.

### 1.5 Default selection

- **There is no explicit default-selection logic anywhere.** When `expiry` is empty/None, `FyersDataAdapter.get_option_chain()` (data_adapter.py:425–441) omits the `timestamp` query param and **relies on Fyers returning "the nearest expiry"** (documented in the docstring, lines 430–432).
- So "nearest expiry for indices, nearest monthly for stocks" is *not* implemented — it is whatever Fyers' options-chain-v3 default does, with no per-underlying-type rule (weekly vs monthly) and no way to distinguish the two when the user needs the monthly series of an index.

### 1.6 Research layer (secondary consumer)

- `research_source.py:134 options_summary()` reads `app.state.options_chain` (`{symbol: {spot, contracts}}`), primed by `prime_options_chain()` (intelligence_router.py:235) with NIFTY at nearest expiry. No expiry awareness beyond what the chain cache holds.

---

## 2. What's missing

1. **No `GET /api/intelligence/expiry-calendar` endpoint** (nor any other expiry enumeration endpoint). Confirmed by grep across the whole tree — zero matches for `expiry-calendar`/`expiry_calendar`/`expiryCalendar`.
2. **No weekly/monthly distinction as calendar data.** The only distinction is the `is_monthly_expiry()` *date heuristic* used for ticker encoding. There is no per-underlying model of "which weekdays carry weekly expiries" (BANKNIFTY Mon/Tue/Wed/Thu; NIFTY/FINNIFTY Thu; MIDCPNIFTY Mon), no "monthly = last Thu", no "OPTSTK = monthly only", no "FUTURES = monthly + near month".
3. **No distinct-expiry query on the instrument master** — the SQLite mirror holds the dates but nothing enumerates them per underlying.
4. **UI dropdown is a learned list, not a calendar** — it can't show expiries the user hasn't already loaded, shows no weekly/monthly labels, and can't default correctly (e.g. monthly for a stock) because the backend has no calendar to consult.
5. **No default-selection rule** — defaults are delegated to Fyers' opaque "nearest" behavior.
6. **MIDCPNIFTY gaps:** `INDEX_SYMBOLS` in `_util.py:15` = `{NIFTY, BANKNIFTY, FINNIFTY}` only, and `_INDEX_INTERNAL_TO_TICKER` in `symbols.py:56` lacks MIDCPNIFTY (the fallback `f"{sym}-INDEX"` may or may not match the real master ticker). Any calendar/default logic must handle MIDCPNIFTY explicitly.

---

## 3. Proposed fix approach (algorithm)

**Source of truth: the instrument master** (public download, refreshable without a token, refreshed daily by `ensure_fresh`). Fyers has **no REST "list expiries" endpoint** used in this codebase — the master is the authoritative expiry source (F-INT-008 keeps it fresh).

1. **Add `list_expiries(internal_symbol, exchange="NSE", instrument_type="OPTION")` to `FyersInstrumentMaster`** — `SELECT DISTINCT expiry FROM fyers_instruments WHERE internal_symbol=? AND exchange=? AND instrument_type=? AND expiry IS NOT NULL`, parsed to ISO dates, sorted ascending, filtered to future dates (or with a `cutoff` arg). ~15 lines; the SQLite index `idx_fi_internal` already covers the lookup.
2. **Classify each expiry** with the existing `is_monthly_expiry()` from `symbols.py` (last-occurence-of-weekday ⇒ monthly, else weekly). For the per-underlying weekly-day rules (BANKNIFTY Mon/Tue/Wed/Thu, NIFTY/FINNIFTY Thu, MIDCPNIFTY Mon, OPTSTK monthly-only, FUTURES monthly+near-month), add a small **calendar policy table** keyed by internal symbol + instrument type — explicit, testable, and able to encode the user's rules. (The `is_monthly_expiry` heuristic alone can't express "BANKNIFTY has weeklies on four different weekdays"; the policy table pins the weekly day per underlying and derives monthly = last occurrence of that day, with last-Thu as the shared monthly anchor.)
3. **New endpoint `GET /api/intelligence/expiry-calendar?symbol=…`** on `intelligence_router` → `{symbol, instrument_type, expiries: [{date, kind: "weekly"|"monthly"}]}` (+ maybe `default`). Resolve the underlying's instrument type via the master (INDEX for the four indices, OPTION for stocks → but note stocks resolve as EQUITY in `_resolve_symbol`, so the router must map the calendar lookup to the F&O master rows by internal symbol). Serve from `app.state.instrument_master` (already wired in `instrument_init.py`); cache per symbol for the day.
4. **Frontend:** replace the passive `expiries` accumulation in `ChainGrid.svelte` with a fetch of the calendar on symbol commit; render the `Select` grouped weekly/monthly (or labeled `W`/`M`); keep free-text fallback when the master is unavailable. Default = per policy (index → nearest weekly, stock → nearest monthly, futures → nearest of monthly+near-month) instead of empty-string delegation.
5. **Backend default:** when `expiry` is empty, resolve the calendar default server-side and pass the concrete expiry to the adapter — removes the opaque "Fyers picks nearest" behavior (keep the fallback to empty-string only when no calendar exists).

## 4. Existing code that can be reused

- **`is_monthly_expiry()`** — `integration/fyers/symbols.py:195` — monthly-vs-weekly classification (extend with per-underlying policy).
- **`FyersInstrumentMaster.search()`** — already filters by `internal_symbol` + `instrument_type` and returns `expiry` — basis for the DISTINCT query (or just add the SQL).
- **`_parse_expiry_date()`** — `terminal/api/intelligence_router.py:56` — robust expiry-string parsing for the endpoint layer.
- **`FyersInstrumentMaster.ensure_fresh()`** — daily staleness; the calendar never needs a token.
- **`_expiry_epoch()`** — `integration/fyers/_util.py:118` — converts calendar dates to the Fyers `timestamp` query param (the endpoint can hand the resolved default expiry straight to the adapter).
- **ChainGrid `Select` + `expiries` plumbing** — the dropdown scaffolding exists; only the data source and labeling change.
- **`symbols.py` monthly/weekly regex + `_WEEKLY_MONTH_CODE`** — needed if the fix ever constructs tickers for arbitrary calendar dates (to_fyers already does this).

## 5. Verification notes (for the plan phase)

- New unit tests: `list_expiries` (DISTINCT, sorted, cutoff), policy-table classification (BANKNIFTY 4-day weeks, last-Thu monthly, OPTSTK single monthly, MIDCPNIFTY Mon), endpoint shape + default resolution.
- Existing tests to keep green: `tests/integration/test_fyers_instrument_master.py`, `tests/wave7/test_instrument_init.py`, symbols round-trip tests (F-INT-012).
- Gate: full suite via `.venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=…`; `npm run check` for the Svelte side.
- No CI in repo — manual gates per AGENTS.md.
