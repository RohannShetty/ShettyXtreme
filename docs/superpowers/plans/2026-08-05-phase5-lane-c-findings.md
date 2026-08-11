# Phase 5 Lane C — Symbols + Instrument Master Fixes (F-INT-012, F-INT-008) — Findings

**Date:** 2026-08-05
**Scope:** Phase 5 (medium-effort correctness/reliability), Lane C — two fixes:
  1. **F-INT-012** — Monthly↔weekly symbol round-trip asymmetry (`integration/fyers/symbols.py`)
  2. **F-INT-008** — Instrument master refreshed only when DB empty (`integration/fyers/instrument_master.py` + bootstrap wiring)
**Status:** Both fixes implemented and regression-tested. Lane C scope: **1115 passed / 0 failed**. Full suite at time of writing: **1115 passed / 1 failed** — the single failure (`test_intelligence_layers`) is in Lane B's in-flight scope (see §4).

---

## Deliverables

| File | Change |
|---|---|
| `src/shettyxtreme/integration/fyers/symbols.py` | `from_fyers()` now returns an `is_monthly` flag (True/False for derivatives, None for index/equity); `to_fyers()` accepts an optional `is_monthly` format override; the two are now exact inverses |
| `src/shettyxtreme/integration/fyers/instrument_master.py` | New `fyers_meta` key/value table storing `last_refreshed`; `refresh()` stamps it only on real data; new `needs_refresh(max_age_hours)` / `last_refreshed()` / `ensure_fresh()`; `max_age_hours` ctor param (default 24h) |
| `src/shettyxtreme/terminal/api/instrument_init.py` | Bootstrap now calls `ensure_fresh(max_age_hours=…)` (refresh when empty **or** stale) instead of the empty-DB-only check |
| `tests/integration/test_fyers_symbols.py` | Round-trip identity tests (monthly/weekly options + futures, weekly-on-monthly-boundary), `is_monthly` flag assertions, extended `test_reencode_identity` to include monthly forms |
| `tests/integration/test_fyers_instrument_master.py` | `TestInstrumentMasterStaleness` — 9 tests: empty/fresh/stale/zero-age/missing-stamp/failed-refresh + `ensure_fresh` refreshes/skips/populates |
| `tests/wave7/test_instrument_init.py` | 3 tests: bootstrap refreshes stale master, skips fresh master, degrades to `None` on failure |
| `docs/superpowers/plans/2026-08-05-phase5-lane-c-findings.md` | This report |

---

## 1. F-INT-012 — Monthly↔weekly symbol round-trip asymmetry

### Symptom

`from_fyers()` and `to_fyers()` were **not inverses** for monthly derivatives. The monthly format encodes only year+month (`NSE:NIFTY24OCT25000CE`), so `from_fyers` could not recover the real expiry day — it set `expiry = date(2024, 10, 1)` as a placeholder. `to_fyers` then re-derived the format from that placeholder via `is_monthly_expiry()`:

- `NSE:NIFTY24OCT25000CE` (monthly) → parse → `expiry=2024-10-01` → `is_monthly_expiry(2024-10-01)` is **False** (Oct 1 is not the last weekday of October) → re-encoded as the weekly form `NSE:NIFTY24O0125000CE`.
- The reverse asymmetry: a weekly contract expiring on the last weekday of the month (e.g. `NSE:NIFTY24O3125000CE`, Oct 31 2024 = last Thursday) → parse → `is_monthly_expiry(2024-10-31)` is **True** → re-encoded as the monthly form `NSE:NIFTY24OCT25000CE`.

The existing `test_reencode_identity` test explicitly excluded monthly forms — the asymmetry was a known, un-tested gap. This corrupts any internal-symbol → Fyers → internal-symbol round trip (watchlist add path, tick decoding, proposal symbol resolution): a monthly contract can silently turn into a different (weekly) contract.

### Fix

Preserve the **encoded format** through the parse/construct boundary instead of trying to reconstruct it from the lossy placeholder date (impossible in general: the monthly format does not encode the weekday convention, which changed from Thursday to Tuesday in 2025).

1. `from_fyers()` adds `"is_monthly"` to every result: `True` for monthly options/futures, `False` for weekly, `None` for index/equity (which carry no format). Backward compatible — all consumers (`trading_adapter.py`, `data_adapter.py`) read via `.get()`.
2. `to_fyers()` gains `is_monthly: bool | None = None`. When provided it **overrides** `is_monthly_expiry(exp)` for FUTURES/OPTION (default `None` keeps the existing auto-detect, so all existing callers are unchanged).
3. `FyersSymbolResolver.to_fyers()` threads the kwarg through.

The round trip `to_fyers(from_fyers(sym)) == sym` now holds for every derivative form, both directions, including the previously-broken boundary cases.

### Regression tests

- `TestRoundTrip.test_round_trip_is_exact_identity` — parametrized over monthly option, weekly option, weekly-on-monthly-boundary, monthly future, weekly future: `to_fyers(from_fyers(sym), is_monthly=parsed["is_monthly"]) == sym`. **Red before fix** (monthly degenerated to weekly), green after.
- `TestRoundTrip.test_round_trip_without_flag_breaks_monthly` — documents the pre-fix asymmetry (`NSE:NIFTY24OCT25000CE` → `NSE:NIFTY24O0125000CE` without the flag), locking in why the flag exists.
- `TestFromFyers` — `is_monthly` flag assertions on monthly/weekly options, weekly-on-boundary, monthly/weekly futures; `test_parse_index` exact-dict updated with `"is_monthly": None`.
- `TestRoundTrip.test_reencode_identity` — now passes `is_monthly=decoded["is_monthly"]` and includes the monthly forms previously excluded.

---

## 2. F-INT-008 — Instrument master refreshed only when DB empty

### Symptom

The bootstrap (`terminal/api/instrument_init.py`) refreshed the master **only when `count_instruments() == 0`**. After the first successful run the DB is populated forever, so the master went stale indefinitely — new expiries, changed lot sizes, and new strikes never appeared. Fyers publishes a fresh master every trading day; a populated-but-days-old mirror misses all of it.

### Fix

1. **`fyers_meta` table** (key/value) added to the schema; `refresh()` writes `last_refreshed` (UTC ISO) via `_set_meta` **only when at least one master actually landed data** — a total download failure must not reset the clock, or a dead mirror would hide its staleness for another full `max_age_hours` window.
2. **`needs_refresh(max_age_hours=None)`** — True when the mirror is empty, when `last_refreshed` is missing (pre-fix databases self-heal on next boot), or when the stamp is older than the threshold. Threshold defaults to the ctor's `max_age_hours` (default 24h — matches Fyers' every-trading-day cadence).
3. **`ensure_fresh(max_age_hours, http_get, timeout)`** — refreshes only when `needs_refresh()`; returns `None` (no network call at all) when fresh. Injectable `http_get` keeps tests hermetic.
4. **Bootstrap** (`init_instrument_master`, new `max_age_hours: float = 24.0` param) now calls `master.ensure_fresh(max_age_hours=…)` instead of the empty-DB-only check — the stale-master path is exercised on every terminal start within a day of staleness.

### Regression tests (`TestInstrumentMasterStaleness` + `test_instrument_init.py`)

- `needs_refresh` True on empty DB; False after a successful refresh; True after backdating the stamp 25h (and False again with `max_age_hours=48`); True with `max_age_hours=0`; True when rows exist but no stamp (pre-fix DB).
- A total download failure does **not** stamp `last_refreshed` → mirror stays stale and retries next boot.
- `ensure_fresh` refreshes when stale (returns counts), **skips entirely when fresh** (asserts zero HTTP fetches via a spy), and populates an empty DB.
- Bootstrap wiring: stale → `ensure_fresh` called with the configured `max_age_hours`; fresh → returns the master without a refresh; ctor failure → `None` (no boot crash).

---

## 3. Verification

- Lane C scope (targeted): `pytest tests/integration/test_fyers_symbols.py tests/integration/test_fyers_instrument_master.py tests/wave7/test_instrument_init.py tests/wave7/test_terminal_init.py` → **100 passed / 0 failed** (includes the pre-existing 87 + 13 new/updated cases).
- Full suite (run with a **unique** `--basetemp` — see §4): **1115 passed / 1 failed**. The single failure is `tests/intelligence/test_intelligence.py::test_intelligence_layers` — Lane B's in-flight scope, not touched here.
- Red→green verified for both fixes (round-trip tests fail against the pre-fix behavior; staleness tests fail against the empty-DB-only bootstrap).
- `import openalgo` grep gate: zero matches in all touched files.
- God-module guard: symbols.py 434 lines, instrument_master.py 462 lines — both ≪ 1000.

---

## 4. Parallel-lane interference (important for the orchestrator)

The working tree is shared with Lane B, which is mid-refactor on `intelligence/`, `options/`, `execution/`, and `terminal/` **in parallel with this work**. Observed effects:

- **Two concurrent `pytest` runs** (from Lane B, `--tb=line`, same `--basetemp=…\pytest-phase5`) were live during Lane C's first full-suite attempt, causing the documented Windows SQLite `PermissionError` cascade (temp-dir `rmtree` collisions) and collateral failures in unrelated tests. Re-running with a **unique basetemp** eliminated the cascade.
- Lane B's intermediate source states briefly reverted `instrument_init.py` (a Lane C file) and changed `signal_engine.py`'s staleness behavior mid-run; the transient state has since converged and Lane C's files are intact on disk (verified by targeted re-run: 100/100 pass).
- The one remaining full-suite failure, `test_intelligence_layers`, is caused by Lane B's new staleness gate in `signal_engine.py` (the `Feature` created in that legacy test carries `timestamp=0.0`, which the gate treats as >60s stale → NEUTRAL). It is in Lane B's files and ownership; Lane C did not modify `intelligence/`.

**Recommendation:** the orchestrator should have Lane B confirm `test_intelligence_layers` before merging, and should re-run the full suite once all Phase 5 lanes have landed — the suite is not quiescent while parallel lanes are mid-edit.

## Files touched

- `src/shettyxtreme/integration/fyers/symbols.py` (owned)
- `src/shettyxtreme/integration/fyers/instrument_master.py` (owned)
- `src/shettyxtreme/terminal/api/instrument_init.py` (minimal bootstrap wiring required by F-INT-008 — the empty-DB-only check lives here)
- `tests/integration/test_fyers_symbols.py` (regression)
- `tests/integration/test_fyers_instrument_master.py` (regression)
- `tests/wave7/test_instrument_init.py` (new, regression)
- `docs/superpowers/plans/2026-08-05-phase5-lane-c-findings.md` (this report)

Nothing committed.
