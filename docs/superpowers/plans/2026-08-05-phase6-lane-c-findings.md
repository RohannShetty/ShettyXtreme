# Phase 6 Lane C — Findings: Watchlist hydration batching

**Date:** 2026-08-05
**Status:** Complete · v0.13.0 baseline (1116 tests) · backend-only change (F-TERM-003 / roadmap #3)
**Scope:** `data_adapter.py` + `watchlist_router.py` + related test files (per lane ownership)
**Files changed:**
- `src/shettyxtreme/integration/fyers/data_adapter.py`
- `src/shettyxtreme/terminal/api/watchlist_router.py`
- `tests/wave7/test_watchlist_hydration.py`
- `tests/integration/test_fyers_data_adapter.py`
- `docs/superpowers/plans/2026-08-05-phase6-lane-c-findings.md` (this file)

---

## 1. What was implemented

### 1.1 `FyersDataAdapter.get_quotes(symbols: list[str])` — batched quotes

New adapter method that turns N idle-symbol REST calls into **⌈N/50⌉ calls**:

- Resolves every symbol up front to a Fyers ticker (per-symbol `ValueError` from
  the resolver is caught and the symbol skipped — an unresolvable symbol no
  longer fails the whole hydration).
- Groups tickers into batches of ≤50 (`_QUOTES_BATCH_SIZE`, Fyers' per-request
  cap) and issues one `/data/quotes?symbols=a,b,c` per batch.
- Parses the response dict `d` (keyed by ticker) back to the **internal symbol**
  the caller passed in, so the router can look results up directly. Handles
  percent-encoded response keys via the pre-existing `unquote` fallback.
- Folds the `get_ltp` fallback in: `ltp` falls back from the quote's top-level
  `ltp` when `fp.ltp` is absent — no second call per symbol.
- Degrades per batch (`FyersError` → warn + skip) instead of throwing; non-dict
  responses yield `{}`. All requests still flow through the client's 8/s token
  bucket (`client.py:43`) — the batch cap never bypasses it.

`get_ohlc(symbol)` and `get_ltp(symbol)` are now thin single-symbol delegations
to `get_quotes`, so the `market_router.py` endpoints and any other callers keep
working unchanged.

### 1.2 `watchlist_router._hydrate_from_rest` — one batched lookup + TTL cache

The per-symbol loop (`get_ohlc` then `get_ltp` per row) is replaced by:

1. **Collect idle rows** (ltp ≤ 0), dedupe to their `security_id` query.
2. **Prefer `adapter.get_quotes(queries)`** — one call for all idle symbols; the
   adapter does the ≤50 grouping. Adapters that predate batching (no
   `get_quotes`) fall back to the old per-symbol `get_ohlc`/`get_ltp` pair, so
   the router stays broker-neutral.
3. **TTL cache** (`_hydration_cache`, keyed by `security_id`): every outcome —
   hit or miss — is recorded with a `time.monotonic()` stamp for
   `_HYDRATION_TTL = 10s` (bounded at `_MAX_HYDRATION_CACHE = 512`). A repeat
   `GET /api/watchlist` within the TTL restores the cached values instead of
   re-triggering REST. This matters most for **halted securities** whose ltp
   stays 0 — without it, every GET of a watchlist containing one re-fetches it
   forever.

## 2. Findings

### 2.1 Call-count reduction (the headline number)

| Scenario | Before | After |
|----------|--------|-------|
| 10 idle symbols, all with fp.ltp | 10 sequential REST calls | **1 call** |
| 10 idle symbols, none with fp.ltp | 20 sequential REST calls (ohlc + ltp each) | **1 call** |
| 60 idle symbols | 60–120 sequential REST calls | **2 calls** |
| Halted symbol (ltp stays 0), client GETs 5× | 5 calls | **1 call** (cached miss), re-fetch only after 10s TTL |

At the client's 8/s token bucket, the 10-symbol case drops from ~1.25 s of pure
throttle wait (recon §3.1) to effectively zero (the bucket admits one request
immediately).

### 2.2 Why a per-symbol fallback path was kept in the router

`get_ohlc`/`get_ltp` are adapter-specific (they are **not** in the
`DataProvider` protocol — `core/interfaces/data_provider.py`), so a future
non-Fyers adapter wired as `data_adapter` may implement the old pair but not
`get_quotes`. The `callable(getattr(adapter, "get_quotes", None))` capability
check keeps the broker-neutral router working with both. The fallback path is
exercised by `tests/wave7/test_watchlist_hydration.py`
(`LegacyFakeDataAdapter`).

### 2.3 Folding `get_ohlc`/`get_ltp` into `get_quotes` changes a corner-case behavior

Previously `get_ohlc` returned `"ltp": None` when `fp.ltp` was absent, and the
router made a **second** `get_ltp` call. The folded `get_quotes` resolves the
top-level `quote.ltp` into the payload, so callers get a usable `ltp` in one
call. `get_ltp` still returns `0.0` when no ltp exists anywhere. The
`market_router` `GET /api/market/ltp` endpoint is unaffected (its `_as_price`
guard treats a now-present ltp identically to the `get_ltp` fallback it would
have made).

### 2.4 TTL cache semantics worth knowing

- The cache is **module-level** in `watchlist_router.py` (matches the
  `scanner_router` module-global pattern). It is cleared on the `reset_state`
  autouse fixture in the hydration tests.
- Successful hydrations also populate the cache, but they are usually moot: a
  backfilled row has `ltp > 0`, so the next GET skips it at the idle check
  before the cache is consulted. The cache's real value is the **miss** path.
- The TTL is `time.monotonic()`-based, so expiry is deterministic and testable
  by backdating the stamp.

### 2.5 Verification

- Full pytest suite: **1182 passed / 0 failed** (baseline 1116 + Lane A
  F-CORE-001 work landing concurrently + 12 new tests from this lane).
- `grep "import openalgo|from openalgo" src/` → zero matches.
- God-module guard: no file > 1000 lines (largest touched file:
  `test_fyers_data_adapter.py` at 530 lines).
- Batching regression tests use mocked transports (`AsyncMock` client /
  fake adapter) and assert **call counts** (1 batched call for N symbols;
  2 calls for 60 symbols), not just payload correctness.

### 2.6 Operational note — concurrent Lane A edits

During verification, Lane A (F-CORE-001 model consolidation) was mid-flight on
`core/interfaces/order_executor.py` and its ~15 importer/test files; collection
intermittently failed with `cannot import name 'Order'` while files were
half-migrated. This lane's files never depended on those models, but the shared
`app` import chain does, so the full-suite gate was momentarily un-runnable.
Re-run after Lane A landed: clean.

## 3. Follow-ups (not done — out of scope)

- **Parallelism vs grouping** (recon §3.2): grouping already collapses the
  throttle wait; `asyncio.gather` over batches would only help when a
  watchlist exceeds 50 idle symbols, and the 8/s bucket serializes anyway. Left
  as-is; revisit only if watchlists routinely exceed 50 idle rows.
- **Per-symbol subscription scoping** (recon §2.4): hydration only fires when
  the live feed is idle; a symbol-routed WS protocol would shrink the idle set
  further. That is roadmap #2's scope, not this lane's.
