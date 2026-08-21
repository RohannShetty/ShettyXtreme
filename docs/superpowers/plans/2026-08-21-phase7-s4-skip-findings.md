# Phase 7 S4 — Skipped Test Findings

**Date:** 2026-08-21
**Status:** Investigated — legitimate skip, no code change
**Suite run:** `1833 passed / 0 failed / 1 skipped` (92.46s)

---

## 1. Which test is skipped

**File:** `tests/wave8/test_iaf_adapter_integration.py:28`
**Tests affected:** Entire module — 13 tests across 7 classes (counts as **1 skipped collection** in `pytest -rs` summary; with IAF installed would be 13 passed).

| Class | Tests |
|---|---|
| `TestIAFAdapterInitialization` | `test_adapter_creation`, `test_adapter_has_run_backtest`, `test_adapter_has_compare_strategies` |
| `TestIAFAdapterBacktest` | `test_run_backtest_returns_report`, `test_run_backtest_with_empty_signals` |
| `TestIAFCostModelIntegration` | `test_cost_model_maps_to_trading_cost` |
| `TestIAFPositionSizing` | `test_position_size_percentage`, `test_conviction_scales_position` |
| `TestIAFStopLossTakeProfit` | `test_tp_sl_policy_from_config`, `test_eod_time_from_config` |
| `TestIAFCooldownRule` | `test_cooldown_bars_from_config`, `test_cooldown_prevents_reentry` |
| `TestIAFStrategyComparison` | `test_compare_strategies_returns_dict` |

**Evidence — full suite with `-rs`:**

```
SKIPPED [1] tests\wave8\test_iaf_adapter_integration.py:28: investing_algorithm_framework not installed
1833 passed, 1 skipped, 2 warnings in 92.46s (0:01:32)
```

**Focused repro:**

```powershell
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave8/test_iaf_adapter_integration.py -v --tb=line --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider
# => collecting ... collected 0 items / 1 skipped  |  1 skipped in 0.12s
```

---

## 2. Skip decorator / reason

```python
# tests/wave8/test_iaf_adapter_integration.py:28
iaf = pytest.importorskip(
    "investing_algorithm_framework",
    reason="investing_algorithm_framework not installed"
)
```

- Pattern: `pytest.importorskip` at module top-level — canonical optional-dependency gate. When the import fails, pytest marks the **entire module collection** as one skipped node (hence `1 skipped`, not 13).
- Source guard in production code is consistent: `src/shettyxtreme/integration/external/iaf_adapter.py:29-47` uses `try/except ImportError` with `_IAF_AVAILABLE` flag and raises `IAFBacktestError` with install hint on `IAFBacktestAdapter.__init__`.

**Optional-dependency declaration:**

```toml
# pyproject.toml:46
iaf = ["investing-algorithm-framework>=8.0,<9.0"]
```

`investing-algorithm-framework` is **not** in `project.dependencies` — it is `[project.optional-dependencies].iaf` only. `importlib.util.find_spec("investing_algorithm_framework")` returns `None` in the default `.venv`; `pip list` confirms not installed (while `duckdb 1.5.4` and `QuantLib 1.43` are installed).

---

## 3. Verdict: legitimate environment-gated skip — DO NOT FIX

**Classification: legitimate optional-dependency gate. No fix applied.**

Rationale:

1. **Same pattern as other optional gates that are correctly installed here.** `tests/options/test_quantlib_pricer.py:27` (`pytestmark = pytest.mark.skipif(not QUANTLIB_AVAILABLE)`) and `tests/core/test_time_series_store.py:16` (`duckdb C extension not available on Python 3.14`) are *not* skipping because `QuantLib 1.43` and `duckdb 1.5.4` are in the default venv. The IAF gate is the same idiom — it only skips when the extra is absent. That is intentional.

2. **Not fixable by mocking.** The 13 tests exercise real IAF surface (`IAFBacktestAdapter.run_backtest` → `App.run_backtest` → `TradingStrategy`/`PositionSize`/`TradingCost` etc.). Mocking `investing_algorithm_framework` would turn integration tests into unit tests that assert mocks, not the adapter — false confidence. The adapter already has its own import guard; the integration tests' job is to run against the real library when present.

3. **Not fixable by installing by default.** Promoting `iaf` from optional to required would inflate every developer/CI install with a heavy backtest engine that is only needed for the `BacktestEngine` research path (FR-004/FR-005). The `AGENTS.md` / `pyproject.toml` design is `pip install -e ".[iaf]"` on demand.

4. **Other skip sites verified not firing:**
   - `tests/core/test_import_boundaries.py:125,157,191,217` — `pytest.skip("core/ not found")` etc. — not hit (modules present).
   - `tests/terminal/test_integration.py:84` — health projection skip — not hit (projection initialised).
   - `tests/integration/test_fyers_data_socket.py:153` — `importorskip("fyers_apiv3.FyersWebsocket.data_ws")` — not hit (`fyers-apiv3 3.1.15` installed).

**If you want 0 skipped locally (opt-in):**

```powershell
.venv\Scripts\python.exe -m pip install "investing-algorithm-framework>=8.0,<9.0"
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider
# Expected: 1846 passed / 0 skipped (1833 + 13 IAF tests)
```

Do not add this to the default `pip install -e .` or CI base image.

---

## 4. Updated suite counts (no change)

- Before: `1833 passed / 1 skipped`
- After: `1833 passed / 1 skipped` (legitimate — no code change)
- With `.[iaf]` installed: `1846 passed / 0 skipped` (projected; 13 additional)

No quality-gate violation — the skip is documented and expected.

---

## 5. Recommended doc alignment

### AGENTS.md — `## Test Gates` (line ~30)

Current text is stale (`v0.16.0 — 1831 passed / 0 failed / 0 skipped`). Replace with:

```markdown
1. Full suite passes (command above). Suite: **1833 passed / 0 failed / 1 skipped** (v0.17.0).
   The 1 skip is legitimate and expected: `tests/wave8/test_iaf_adapter_integration.py` is gated on
   `investing-algorithm-framework` (`[project.optional-dependencies].iaf = "investing-algorithm-framework>=8.0,<9.0"`).
   Install with `pip install -e ".[iaf]"` to run it (then 1846 passed / 0 skipped). Other optional gates
   (QuantLib, duckdb, fyers-apiv3) are installed in the default venv and do not skip.
```

If the orchestrator tracks counts separately, update it to the same numbers.

### `orchestrator_append.md` (or `.projectos/` equivalent)

No `orchestrator_append.md` exists at repo root. If one is created, add:

```markdown
## Test suite — known skip (Phase 7 S4, 2026-08-21)

- **Count:** 1833 passed / 1 skipped / 0 failed is the expected green for the default venv.
- **Skip:** `tests/wave8/test_iaf_adapter_integration.py:28` — `pytest.importorskip("investing_algorithm_framework", reason="investing_algorithm_framework not installed")` — entire module (13 tests) skipped when `[iaf]` extra not installed.
- **Action:** None. This is an optional-dependency gate (same idiom as `tests/options/test_quantlib_pricer.py` for QuantLib). To verify locally: `pip install -e ".[iaf]"` then re-run; expect 1846 passed.
- **Do not** promote `iaf` to required dependencies or mock IAF in these tests.
```

### Alternative: `pyproject.toml` marker documentation (optional)

If you want the gate visible in `pytest --markers`:

```toml
# No change required — importorskip already self-documents.
# Optionally add to [tool.pytest.ini_options] markers:
# markers = ["iaf: investing-algorithm-framework integration tests (require `.[iaf]` extra)"]
```

---

## 6. How to verify

```powershell
# Default venv — expect 1 skip
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider -rs

# With IAF — expect 0 skipped
.venv\Scripts\python.exe -m pip install "investing-algorithm-framework>=8.0,<9.0"
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave8/test_iaf_adapter_integration.py -v --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider
```

---

## 7. Conclusion

Single skipped **collection** is not a regression or a bug — it is the intended `importorskip` gate for the optional `iaf` extra. Keep the skip, update `AGENTS.md` counts from `1831/0/0 (v0.16.0)` to `1833/1/0 (v0.17.0)` with the note above, and align any orchestrator tracker to the same numbers. No code fix warranted.
