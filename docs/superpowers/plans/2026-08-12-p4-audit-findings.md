# P4 Audit Findings — Regression, Architecture Drift, Data Pipeline

**Date:** 2026-08-12
**Scope:** Phase 5 pre-gate audit (final before Phase 6)
**Method:** full pytest run, import-graph scan of `src/shettyxtreme/*`, source trace of every `[UNSOURCED]` path

---

## Executive Summary

| Area | Verdict | Details |
|---|---|---|
| Regression suite | ✅ **Green** | 1604 passed / 1 skipped / 0 failed in 78.5 s |
| D3 wall (LLM in research/ only) | ✅ **Clean** | sole touchpoint `research/provider.py` |
| D12 wall (knowledge → core only) | ✅ **Clean** | verified |
| Standalone rule (no openalgo) | ✅ **Clean** | zero matches in `src/` |
| File-size guard (≤1000 lines) | ✅ **Clean** | largest file 809 lines |
| Layer boundaries | ⚠️ **3 violations** | intelligence→learning cycle, integration→intelligence, execution→non-contract imports |
| Boundary enforcement | ❌ **Missing** | documented CI walk test does not exist; no `.github/` |
| Data pipeline `[UNSOURCED]` | ⚠️ **1 honesty bug + 1 quality gap** | regime_snapshot fabricates defaults; chain_snapshot too thin |

Net: no P0 blockers. Three fixes required before Phase 6 (see §4), all small.

---

## 1. Regression Tests

### 1.1 Current state (run: 2026-08-12, `pytest tests/ -q --durations=8`)

```
1604 passed, 1 skipped, 2 warnings in 78.51s
```

- **1604 tests collected** (up from the 1012 documented at v0.12.0 in AGENTS.md → +592 across Phases 1–4).
- **1 skipped**: `tests/core/test_time_series_store.py` ×2 marked
  `@pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="duckdb C extension not available on Python 3.14")`
  → environmental gate, not a code issue.
- **Slowest tests** (no egregious outliers, no time-based flakiness observed in this run):
  - `wave9/test_analytics_api.py` scorecard tests ~3.8 s each
  - `wave6/test_shadow_graduation_e2e.py` ~2.7 s
  - `wave9/test_lifespan_wiring.py` ~2.4 s
  - `wave6/test_shadow_manager.py` ~2.2 s
- **No flaky/failing tests observed.** Single full-suite run is green.
- **No `TODO`/`FIXME`/`XXX`/`HACK` comments in tests** — nothing to sweep.

### 1.2 Coverage gaps (real, per-method)

Coverage by package is broadly healthy — `auth` (wave7), `knowledge` (wave9), `learning`
(wave2–4/6), `research` (wave8) all have tests even though they lack mirror dirs:

| src package | test home |
|---|---|
| core / data / execution / integration / intelligence / options / terminal | mirror dirs under `tests/` |
| research | `tests/wave8/*` (10 files) |
| knowledge | `tests/wave9/test_knowledge_*.py` (7 files) |
| learning | `tests/wave2–4`, `tests/wave6` |
| auth | `tests/wave7/test_auth_router.py`, `test_credential_store.py`, `tests/integration/test_fyers_session.py` |

**Actual gaps found:**

1. **`ProjectionDataSource.regime_summary()` — untested.** `tests/wave8/test_research_source.py`
   covers `chain_summary` (×2) and `options_summary`/`render_options_posture` (×6) but has
   **zero tests for `regime_summary`, `scanner_summary`, or `knowledge_summary`**.
   This is the exact method that exhibits the default-fabrication bug in §3 — the bug is
   latent because nothing asserts its behavior.
2. **`research_router._current_regime()` — untested** (same default-fabrication pattern).
3. **No architecture/import-boundary test exists.** Section 05/07 of ARCHITECTURE_V2.md
   promise "a dedicated test that walks `src/` imports" and "Boundary import tests: CI walks
   `src/` and fails on forbidden imports". **No such test file exists in `tests/`** and the
   repo has no `.github/` CI (per AGENTS.md) — the promise is documentation-only. This is how
   the §2 violations went unnoticed.

---

## 2. Architecture Drift Check

Contract source: `docs/architecture/v2/ARCHITECTURE_V2.md` + `sections/05-system-boundaries.md`
(import rules are the binding contract) and AGENTS.md gates.

### 2.1 Gates that PASS

| Gate | Evidence |
|---|---|
| **D3 wall** — LLM only in `research/` | Grep of `openai|anthropic|langchain|deepseek|generativeai|vertexai|groq|together|litellm` across `intelligence/`, `execution/`, `knowledge/`, `options/`, `learning/`, `integration/`, `data/`, `core/` → **0 matches**. Sole LLM touchpoint: `research/provider.py` (`DeepSeekProvider`, OpenAI-compatible contract via raw `httpx`, `DEEPSEEK_API_KEY` env-only). |
| **D12 wall** — `knowledge/` imports core only | `knowledge/` imports only `shettyxtreme.core.knowledge.lexicons` + stdlib + `pydantic`. No intelligence/execution imports. ✓ |
| **Standalone rule** — no openalgo | `import openalgo` / `from openalgo` in `src/` → **0 matches**. `vendor/openalgo/` never imported by `src/`. ✓ |
| **File-size guard** — no file > 1000 lines | Largest files: `intelligence/risk/risk_engine.py` (809), `terminal/api/app.py` (782), `terminal/api/execution_router.py` (744), `terminal/projections.py` (729). All < 1000 across src+tests+scripts. ✓ |
| **core/ zero external imports** | Only the **known, pre-existing** violation: `core/config/config_manager.py:11` `import yaml` (documented in AGENTS.md, slated for fix). No new external imports. |
| **options/ and data/ are clean leaves** | `options/` → core only; `data/` → core + own subpackage. ✓ |
| **learning/ imports** | core + intelligence/execution — matches E-layer contract. ✓ |
| **knowledge→core only, research→no project imports** | verified. ✓ |

### 2.2 Layer-boundary violations found

**V1 — `intelligence/` imports `learning/` (upward import + package-level cycle).**
`C. INTELLIGENCE` contract: "imports core ONLY"; "No layer may import a sibling or a layer above it" (learning E sits above intelligence C).

- `intelligence/hints/strategy_hints.py:16` → `from shettyxtreme.learning.sizing import CalibratedSizing`
- `intelligence/signals/shadow_manager.py:17` → `from shettyxtreme.learning.outcome_tracker import OutcomeLabel`

And `learning/` imports `intelligence/` at module level
(`learning/outcome_tracker.py:18`, `learning/shadow_loop.py:24-31`, `learning/walkforward.py:12`, `learning/analytics.py:11`)
→ the **intelligence ↔ learning dependency cycle is real**. It currently resolves at import time
(no runtime failure), but it violates the acyclic layer contract and couples the RAPID intelligence
layer to learning internals.

*Suggested fix:* move `CalibratedSizing` and `OutcomeLabel`'s consumed surface into a
core-owned seam (e.g. core interface + learning implementation injected at composition root),
or ratify the cycle with an ADR + boundary-test exemption. Prefer the former.

**V2 — `integration/` imports `intelligence/` (upward import).**
`B. INTEGRATION` contract: "Never imports `intelligence/`, `execution/`, `terminal/`."

- `integration/external/iaf_adapter.py:22` → `from shettyxtreme.intelligence.risk.cost_model import CostBreakdown, compute_cost`

*Suggested fix:* move `CostBreakdown`/`compute_cost` into `core/` (it is a pure cost model, fits core
domain math) and have both `intelligence/risk/cost_model.py` and `iaf_adapter.py` import it from core.

**V3 — `execution/` reaches outside its listed contract.**
`D. EXECUTION` contract: "imports core + integration/contracts (interfaces only, never DhanHQ directly)."

- `execution/*` → `from shettyxtreme.integration.order_validator import OrderValidator` (a concrete
  implementation class, not a core/interfaces Protocol — "interfaces only" is stretched)
- `execution/*` → `shettyxtreme.intelligence.risk.{risk_engine,cost_model}` and
  `shettyxtreme.intelligence.signals.signal_engine` (imports not listed in the D contract)

Note: the ARCHITECTURE_V2.md layer diagram (execution above intelligence) would make
execution→intelligence a *downward* import — the two documents are internally inconsistent.
This is **drift to ratify, not necessarily to delete**: either amend §05's D import rule to
"core + integration/contracts + intelligence read models" (like E already says), or move the
risk/signal consumption behind EventBus per AGENTS.md's "no direct cross-layer calls".

**V4 — layout drift (not a violation): `options/` is a top-level package.**
§05 lists `options/` as belonging to the **intelligence layer** ("C) Intelligence — What belongs:
`options/` — IV rank, OI analysis, PCR context, expiry/strike selection, strategy analyzer"), but
it lives at `src/shettyxtreme/options/`. All the `intelligence/ → options/` imports are therefore
intra-layer in spirit. *Fix:* either relocate under `intelligence/` or amend the doc to name
`options/` as its own leaf layer (it is a clean core-only leaf today).

### 2.3 Root cause: enforcement is missing

- Section 05: "Enforcement: CI grep rules (per Section 07) + a dedicated test that walks `src/` imports."
- Section 07 line 62: "**Boundary import tests:** CI walks `src/` and fails on forbidden imports (core → external; intelligence → integration; src → openalgo)."
- **Reality:** no `.github/` directory, no boundary test in `tests/`, no CI anywhere. The gates are
  manual greps from AGENTS.md. The drift above survived precisely because nothing walks the imports.
- **Proposed fix (highest-leverage item of this audit):** add `tests/core/test_import_boundaries.py`
  that walks `src/` and asserts:
  - no `import openalgo` anywhere in `src/`
  - `core/` imports only stdlib + own subpackages
  - `knowledge/` imports only core + stdlib
  - `integration/` never imports intelligence/execution/terminal
  - `intelligence/` never imports learning/execution/terminal/integration (until V1 is fixed, scope
    with a documented allowlist or fix V1 first)
  - no file > 1000 lines

---

## 3. Data Pipeline Audit — every `[UNSOURCED]`

Marker lives in `research/tools.py:29` (`UNSOURCED = "[UNSOURCED] — no data"`) plus
`research/digest.py:40,43`. Tools render it only when the injected `DataSource` is missing or
returns falsy — the design is honest-by-construction.

**Wiring verified end-to-end:**
`terminal/api/app.py:320` → `set_data_source(ProjectionDataSource(app.state))` at lifespan;
`ProjectionDataSource` (`terminal/api/research_source.py`) implements the `DataSource` protocol
and reads live `app.state` projections; `prime_options_chain` (`intelligence_router.py:237`)
populates `app.state.options_chain` + feeds `IVRankCalculator`/`OITracker` on every successful
(re-)init (`terminal_init.py:280-284`).

| Tool | Wired to | Status |
|---|---|---|
| `chain_snapshot` | `watchlist_projection` (live MARKET_DATA_TICK stream) | ⚠️ wired but **thin** — see P2 below |
| `options_posture` | `iv_rank_calculator` + `oi_tracker` + `options_chain` (primed NIFTY) | ✅ fully live |
| `regime_snapshot` | `intelligence_projection` ← REGIME_CHANGED/SIGNAL_V2 (RegimeEngine/SignalEngine path) | ⚠️ wired but **fabricates defaults** — see P1 below |
| `scanner_alerts` | `alert_projection` (SCANNER_FINDING sink) | ✅ honest (None when empty → UNSOURCED) |
| `knowledge_search` | `knowledge_store.search(..., status="activated")` | ✅ honest (None when no store/hits) |

### P1 — `regime_snapshot` returns fabricated defaults instead of `[UNSOURCED]` (honesty bug)

`ProjectionDataSource.regime_summary()` (`research_source.py:104-119`) never checks
`proj.has_data()`. `IntelligenceProjection` (`terminal/projections.py:287-361`) initializes with a
hardcoded default and only sets `_has_data=True` on the first live REGIME_CHANGED/SIGNAL_V2 event
— and it exposes `has_data()` precisely for honest no-data detection. Before the first live event
(e.g. a fresh run with no ticks, or before the pipeline warms up), `regime_snapshot` feeds the LLM:

```
regime=range_bound adx=n/a conviction=0.0 D=0.0 P=0.0 G=0.0
```

i.e. **fabricated signal data**, the exact thing the `[UNSOURCED]` design exists to prevent.
The same pattern exists in `research_router._current_regime()` (`research_router.py:251-261`).
Both are untested (§1.2).

*Fix:* in `regime_summary`, return `None` when `proj` exists but `proj.has_data()` is False
(and same guard in `_current_regime`). Add regression tests for both.

### P2 — `chain_snapshot` ignores the chain depth it promises (quality gap)

Tool description: "Strike/spot/IV/volume digest for one NSE symbol." Actual
`chain_summary()` renders only `ltp` + `change_pct` from the watchlist row — it ignores
`volume`/`oi`/`strike`/`option_type` that `WatchlistProjection` already carries, and IV is
REST-only (never on the tick). The primed `app.state.options_chain` (spot, per-contract
IV + OI) is not consulted.

*Fix:* when the requested symbol matches a cached chain in `app.state.options_chain`, merge
spot/IV/OI (and per-strike pins) into the summary; keep the watchlist LTP as the live spot.

### Notes (not bugs)

- **options_posture has no greeks** — the primed chain stores raw adapter rows;
  greek enrichment happens only in `_enrich_chain` for `/api/intelligence/options` responses.
  The tool description promises only "IV rank, PCR, and OI buildup" → current behavior is
  contract-correct. If greeks are wanted in posture, enrich at prime time.
- **Only NIFTY is primed at startup**; other symbols populate `options_chain` only after
  `GET /api/intelligence/options` is hit for them. Acceptable (documented behavior).
- **Digest path is operator-supplied**: `orch.run(sources=req.context, ...)` — the
  `ContextDigest` is fed from the request body, not auto-populated from live projections.
  Per design ("operator attaches sources"). The tools are the live-data path.
- **Scheduler runs tools only when `RESEARCH_SCHEDULE_*` env sets them** (default: no tools →
  scheduled briefs get no live data unless context is supplied). Consider enabling tools by
  default if scheduled briefs should always see live state.
- `digest.py` renders `[UNSOURCED] — no data sources attached` only when zero sources exist —
  honest.

**No other `[UNSOURCED]` paths remain.** All remaining renderings are honest fallbacks
(no source injected / empty chain / empty alerts / no store).

---

## 4. Proposed fixes (priority order)

| # | Fix | Files | Size |
|---|---|---|---|
| F1 | **Add import-boundary enforcement test** (walk `src/`, assert D3/D12/standalone/layer rules; keep it green by fixing F2–F4 first or with a documented allowlist) | new `tests/core/test_import_boundaries.py` | ~120 lines |
| F2 | **P1 honesty fix**: `regime_summary` + `_current_regime` return None when `has_data()` is False; add regression tests | `research_source.py`, `research_router.py`, `tests/wave8/test_research_source.py` | < 30 lines (tiny-fix) |
| F3 | **V2 fix**: move `CostBreakdown`/`compute_cost` to `core/`; re-point `iaf_adapter` + `intelligence/risk/cost_model` | `core/`, `integration/external/iaf_adapter.py`, `intelligence/risk/cost_model.py` | medium |
| F4 | **V1 fix**: break intelligence→learning (inject `CalibratedSizing`/`OutcomeLabel` via core seam or composition root) | `strategy_hints.py`, `shadow_manager.py` | medium |
| F5 | **Ratify V3/V4**: amend §05 D import rule to include intelligence read models (or route via EventBus); move `options/` under `intelligence/` or rename it a leaf layer in the doc | docs only (or small moves) | docs |
| F6 | **P2 quality**: `chain_summary` merges primed `options_chain` data (spot/IV/OI/pins) | `research_source.py` | small |
| F7 | **Coverage**: add `regime_summary`/`scanner_summary`/`knowledge_summary` unit tests (folded into F2) | `tests/wave8/test_research_source.py` | small |

**No P0 items.** F2 is the only behavioral bug (fabricated data into the LLM) — it should land
before Phase 6 regardless of everything else. F1 is the highest-leverage prevention.

---

## Appendix — evidence commands

```powershell
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --durations=8 --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider
# → 1604 passed, 1 skipped in 78.51s

grep -r "import openalgo\|from openalgo" src/        # → 0 matches
# files > 1000 lines in src/ tests/ scripts/          # → none (max 809: risk_engine.py)
# LLM SDK grep across all layers except research/      # → 0 matches
```
