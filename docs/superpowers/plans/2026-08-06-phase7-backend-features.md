# Phase 7 Backend — Knowledge Last Sync (#9) + Options Posture Live (#12)

**Date:** 2026-08-06
**Scope:** Backend (FastAPI) + KnowledgePanel header + tests
**Result:** 1244 passed / 0 failed / 0 skipped (gate was 1241+)

---

## Headline finding: both features were ~80% implemented in a prior session

Before this session, the codebase already contained substantial scaffolding for
both roadmap items. This session **completed the missing 20%** rather than
re-implementing from scratch:

| Feature | Already present | Added this session |
|---|---|---|
| #9 Knowledge last sync | `meta` KV in `KnowledgeStore` + `set_last_sync`/`get_last_sync`; `last_sync_at` on `KnowledgeStatusResponse`; status endpoint returned it; sync handler wrote it on success; panel header rendered `Last sync: HH:MM`/`Never` (`fmtLastSync`) | `last_sync_result` end-to-end (store → model → router → api.ts → panel); telemetry recorded on **failed** and **partial** paths (previously only the success path recorded anything); api.ts field; panel suffix for non-success outcomes |
| #12 Options Posture Live | `prime_options_chain()` in `intelligence_router.py`; wired into `init_terminal_adapters()` (covers lifespan + post-login); graceful degradation; full test file `tests/terminal/test_options_chain_prime.py` | None — already complete and covered (see deviations) |

---

## Item 1: Knowledge "last sync" (roadmap #9)

### Problem (as spec'd)
KnowledgePanel showed per-hit STALE chips but no "last sync" timestamp; the
operator could not tell when the store was last refreshed.

### Actual gap found
`last_sync_at` plumbing already existed. The genuine gaps were:
1. **No `last_sync_result`** ("success"|"partial"|"failed") anywhere.
2. **Failed sync attempts recorded nothing** — the three failure paths
   (`research store unavailable`, `research list failed`, `ingest failed`)
   returned early without touching the `meta` table, so a broken sync looked
   identical to a never-synced store.
3. Frontend type + panel did not model the outcome field.

### Changes per file

**`src/shettyxtreme/knowledge/store.py`**
- Added `set_last_sync_result(result)` / `get_last_sync_result()` using the
  existing `meta` KV table (`INSERT OR REPLACE` — overwrite, not append,
  matching `set_last_sync`).
- Updated `set_last_sync`/`get_last_sync` docstrings: `last_sync_at` is now the
  **last sync attempt** time (a failed attempt is still an attempt); the
  outcome lives in `last_sync_result`.

**`src/shettyxtreme/terminal/api/knowledge_models.py`**
- `KnowledgeStatusResponse` gains `last_sync_result: str | None = None`.

**`src/shettyxtreme/terminal/api/knowledge_router.py`**
- `GET /api/knowledge/status` now also returns
  `last_sync_result=_store().get_last_sync_result()`.
- `POST /api/knowledge/sync` rewritten around a `_record(result)` helper that
  writes **both** `last_sync_at` and `last_sync_result` on every attempt:
  - research store unavailable → `"failed"`
  - research list failed → `"failed"`
  - ingest raised → `"failed"`
  - ingest OK with nothing skipped → `"success"`
  - ingest OK with `skipped_undecided > 0` **or** `skipped_duplicate > 0` →
    `"partial"`
  - `_record` itself is exception-guarded so telemetry failures never break
    the sync response. All degradation paths still return 200, never 500.

**`src/shettyxtreme/terminal/web/src/lib/api.ts`**
- `KnowledgeStatusResponse.last_sync_result` typed as
  `"success" | "partial" | "failed" | null`.

**`src/shettyxtreme/terminal/web/src/components/KnowledgePanel.svelte`**
- Initial `status` state includes `last_sync_result: null`.
- Header keeps `Last sync: {fmtLastSync(status.last_sync_at)}` (HH:MM or
  "Never") and appends a `(partial)` / `(failed)` suffix via a derived
  `lastSyncSuffix` so a non-success sync is never mistaken for a healthy one.

### Tests
- `tests/wave9/test_knowledge_api.py`
  - `test_status_empty` → asserts the full body incl. `last_sync_result: None`
    (pins **initial state** per mission item a).
  - `test_sync_and_search` → additionally asserts
    `last_sync_result == "success"` (pins **after sync** per mission item b).
  - NEW `test_sync_partial_records_partial_result` — an undecided brief →
    `skipped_undecided=1` → status reports `"partial"` with a non-null
    `last_sync_at`.
  - NEW `test_sync_failure_records_failed_result` — points
    `RESEARCH_DB_PATH` at a directory so `ResearchStore.__init__` raises →
    sync still returns 200 and status reports `"failed"` with a non-null
    `last_sync_at`.
- `tests/wave9/test_knowledge_store.py`
  - NEW `test_last_sync_result_meta` — KV defaults to `None`, then overwrite
    semantics for `"success"` → `"failed"`.

---

## Item 2: Options Posture Live (roadmap #12)

### Problem (as spec'd)
`options_posture` showed `[UNSOURCED]` until `GET /api/intelligence/options`
had been hit once (chain cache is write-only as a side-effect of that route).

### Status on arrival
**Already implemented and tested** — no code changes were required:

- `prime_options_chain(app)` (`intelligence_router.py:197-233`): fetches the
  NIFTY chain once the data adapter exists; **never raises**; leaves the cache
  untouched on entitlement (Fyers 403/-373 → `DataEntitlementError`), missing
  adapter (`DataAdapterUnavailable`), network faults, and empty chains — so
  `[UNSOURCED]` stays the honest rendering while no real data exists.
- Wired into `init_terminal_adapters()` (`terminal_init.py:269-280`) guarded by
  `if ok:` — runs on every successful (re-)init, covering both the lifespan
  startup path (`app.py:426-428`) and the post-OAuth-login bootstrap, i.e. the
  "on data-adapter connect" requirement.
- Mission point 3 (`iv_rank_calculator` / `oi_tracker` construction): confirmed
  they are **not** constructed in `app.py`. `research_source.options_summary()`
  already falls back to the primed `app.state.options_chain` when they are
  absent, so posture renders from the live chain — the minimal-fix route the
  mission preferred. Wiring the calculators would additionally need a live
  tick/IV feed; out of scope and not required for posture to go live.
- Existing tests `tests/terminal/test_options_chain_prime.py` already cover the
  mission's required test: "priming doesn't crash on startup without
  credentials" (`test_prime_no_adapter_leaves_cache_untouched`) plus
  entitlement/network/empty-chain degradation and an end-to-end
  `options_summary()` render check.

**No deviation:** documented the `iv_rank_calculator`/`oi_tracker` limitation
(per the mission's "otherwise, document and move on") — posture is now live via
the primed chain; rank/pcr/oi-buildup lines still await a tick-driven feed.

---

## Verification

```powershell
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase7-backend -p no:cacheprovider
# 1244 passed, 0 failed, 0 skipped  (gate: 1241+)

# openalgo standalone rule
Get-ChildItem -Path src -Recurse -File -Include *.py | Select-String -Pattern "import openalgo|from openalgo"
# ZERO matches

# God-module guard (max line count across touched files): 600  (app.py)

# Frontend type gate (in src/shettyxtreme/terminal/web):
npm run check   # svelte-check found 0 errors and 0 warnings
```

Targeted run before the full suite:
`pytest tests/wave9/test_knowledge_api.py tests/wave9/test_knowledge_store.py tests/terminal/test_options_chain_prime.py tests/wave8/test_research_source.py`
→ 38 passed.

---

## Deviations from plan

1. **Most work was already done** — both items existed in a half-finished state.
   Rather than re-implement, I completed the missing `last_sync_result`
   plumbing and verified Item 2 end-to-end with its existing test suite.
2. **No `OptionsProjection` added** — the mission explicitly offered the
   minimal chain-prime fix as the preferred path; it was already wired, so the
   projection (and its tests) were skipped as over-engineering.
3. **`last_sync_at` semantics widened** — it now records the last sync
   *attempt* (any outcome) instead of strictly the last success, paired with
   `last_sync_result`. The panel disambiguates by appending `(failed)` /
   `(partial)`. This keeps a broken sync visible instead of silently re-showing
   an old success time.
4. **Failed-path tests use a directory-as-DB** to force
   `ResearchStore.__init__` to raise deterministically (sqlite cannot open a
   directory), matching the router's existing degrade-to-200 contract.
