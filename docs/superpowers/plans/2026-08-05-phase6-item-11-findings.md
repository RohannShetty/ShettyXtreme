# Phase 6 Item #11 — Scorecard carries current_regime (findings)

Date: 2026-08-05 · Phase 6 item #11 (tiny independent item) · Suite: **1127 passed / 3 failed** (failures pre-existing, in-flight refactor — see below)

## Summary

`AnalyticsPanel.svelte` issued a second REST call to `/api/intelligence/regime`
solely to accent one bar in the "By regime" block (`isCurrent(r)`). The scorecard
endpoint already aggregates every decided brief and knows the regime rows; the
current regime is now carried on the `ScorecardResponse` payload, so the SPA
drops the extra round-trip entirely.

## Changes

### Backend

- `src/shettyxtreme/terminal/api/analytics_models.py` — added
  `current_regime: str | None = None` to `ScorecardResponse` (optional; `None`
  when the intelligence projection is unwired, so the field is backward
  compatible).
- `src/shettyxtreme/terminal/api/analytics_router.py` — added a module-level
  `_current_regime(request)` helper that mirrors the research router's defensive
  access pattern: `getattr(request.app.state, "intelligence_projection", None)`,
  `try/except` around `proj.get_regime()`, string-coerced value or `None`. The
  `scorecard` endpoint now takes `Request` and passes `current_regime` into the
  response. A missing **or broken** projection degrades to `None` — the scorecard
  never 500s over the accent bar.

### Frontend

- `src/shettyxtreme/terminal/web/src/lib/api.ts` — `ScorecardResponse` gains
  `current_regime: string | null`.
- `src/shettyxtreme/terminal/web/src/components/AnalyticsPanel.svelte` —
  `load()` now performs a single `get<ScorecardResponse>("/api/analytics/scorecard")`
  and sources `currentRegime` from `resp.current_regime ?? null`. The
  `get("/api/intelligence/regime").catch(...)` call is gone; comment updated.
  `get` import still used (scorecard fetch). No `svelte-check` errors.

## Regression tests

`tests/wave9/test_analytics_api.py` — 3 new tests:

1. `test_scorecard_current_regime_null_without_projection` — no projection wired
   → `current_regime is None`, status 200.
2. `test_scorecard_carries_current_regime` — fake projection returning
   `{"regime": "trending_up"}` → field equals `"trending_up"`.
3. `test_scorecard_regime_lookup_failure_degrades_to_null` — projection whose
   `get_regime()` raises → `None`, status 200 (defensive path).

Implementation notes worth keeping:

- Starlette's `app.state` (`starlette.datastructures.State`) raises
  `AttributeError` under `monkeypatch.setattr` for a **new** attribute (default
  `raising=True`); pass `raising=False`. Since tests use `ASGITransport` (no
  lifespan), `app.state.intelligence_projection` is normally absent — the tests
  pin it explicitly and `monkeypatch.delattr(..., raising=False)` guards the
  "null" case against leftovers from `test_lifespan_wiring.py`.

## Verification

- `pytest tests/ -q ...` → **1127 passed, 3 failed** (failures pre-existing, see
  below); analytics file alone: **9/9 passed**.
- `npm run check` → **0 errors, 0 warnings**.

## Pre-existing failures — NOT caused by this item

The working tree carries ~900 lines of uncommitted in-flight refactor work
(`core/data_models`, `core/interfaces`, `execution/`, `integration/fyers/`,
`terminal/api/watchlist_router.py` — none in this item's ownership scope). Three
tests in that area fail; all run **before** wave9 in collection order and all sit
in files with in-flight modifications:

1. `tests/integration/test_fyers_data_adapter.py::TestQuotesBatching::test_unresolvable_symbol_skipped`
2. `tests/integration/test_fyers_data_adapter.py::TestQuotesBatching::test_failed_batch_isolated_from_successful_batch`
3. `tests/wave7/test_watchlist_hydration.py::test_cache_expiry_rehydrates`

Evidence they are unrelated to this item:

- The fyers batching tests pass **8/8 in isolation** — order-dependent flakiness
  in the in-flight quotes-batching work, not a scorecard regression.
- `test_watchlist_hydration.py` fails to even *import* in isolation
  (`ImportError: cannot import name 'Order' from
  'shettyxtreme.core.interfaces.order_executor'`) — import-order coupling from
  the in-flight `Order` model move; it only collects when earlier modules
  populate the namespace.
- None of the three reference analytics/scorecard/regime code paths.

## Files touched (ownership scope only)

- `src/shettyxtreme/terminal/api/analytics_models.py`
- `src/shettyxtreme/terminal/api/analytics_router.py`
- `src/shettyxtreme/terminal/web/src/lib/api.ts`
- `src/shettyxtreme/terminal/web/src/components/AnalyticsPanel.svelte`
- `tests/wave9/test_analytics_api.py`
