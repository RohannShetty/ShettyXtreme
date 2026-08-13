# P2-3.4 — Backtesting Engine (IAF adapter) — Plan

**Date:** 2026-08-12
**Status:** IMPLEMENTING
**Spec:** `docs/superpowers/specs/2026-08-12-p2-3-4-backtesting-spec.md`

---

## Implementation steps

### 1. ADR-009 (DONE)

`docs/decisions/ADR-009-iaf-backtesting-integration.md` — integration boundary, dependency admission, vendoring-vs-pip stance, exclusion list, grep gate.

### 2. BacktestEngine Protocol (DONE)

`core/interfaces/backtest_engine.py`:
- `BacktestTrade` dataclass
- `BacktestMetrics` dataclass
- `BacktestReport` dataclass
- `BacktestConfig` dataclass
- `BacktestEngine` Protocol with `run_backtest` and `compare_strategies`

### 3. IAF vendor directory (DONE)

`vendor/iaf/`:
- `FILES.yaml` — file list for sync_vendor.py
- `ORIGIN.md` — manifest (pending upstream mirror)
- `LICENSE` — Apache-2.0
- `README.md` — usage and re-sync instructions

### 4. IAF adapter (DONE)

`integration/external/iaf_adapter.py`:
- `IAFBacktestAdapter` — implements `BacktestEngine`
- `IAFBacktestError` — exception for IAF failures
- `_IAF_AVAILABLE` — guard for missing IAF
- Maps ShettyXtreme signals → IAF TradingStrategy
- Maps cost model → TradingCost
- Maps sizing → PositionSize
- Maps TP/SL policy → TakeProfitRule/StopLossRule
- Adds CooldownRule

### 5. BacktestRunner (DONE)

`learning/backtest.py`:
- `BacktestResult` — wrapper with convenience accessors
- `BacktestRunner` — API over the adapter
- `run()` — run backtest with config, decisions, market data
- `run_from_tracker()` — run backtest using OutcomeTracker
- `compare()` — compare multiple reports

### 6. Tests (DONE)

`tests/wave8/test_iaf_adapter.py`:
- BacktestEngine Protocol compliance
- BacktestConfig defaults and custom values
- BacktestMetrics fields
- BacktestReport structure
- BacktestTrade exit reasons
- BacktestResult convenience accessors
- BacktestRunner with mock engine
- Strategy comparison surface

`tests/wave8/test_iaf_adapter_integration.py`:
- IAF adapter initialization (skipped if IAF not installed)
- run_backtest returns report
- Cost model integration
- Position sizing
- TP/SL policy
- Cooldown rule
- Strategy comparison

### 7. Housekeeping (DONE)

- `pyproject.toml`: dropped `vectorbt` optional dep, added `iaf` optional dep
- `learning/__init__.py`: exported `BacktestResult`, `BacktestRunner`
- `core/interfaces/__init__.py`: exported backtest engine types
- `docs/architecture/v2/ARCHITECTURE_V2.md`: ADR index updated
- `docs/architecture/v2/sections/17-delivery-roadmap.md`: Phase 4 updated
- `.scratch/phase4-knowledge-dashboards/issues/08-backtest-depth-scope.md`: re-opened

### 8. Version bump (PENDING)

Files to update:
- `src/shettyxtreme/__init__.py` (0.13.0 → 0.14.0)
- `src/shettyxtreme/terminal/api/app.py` (0.13.0 → 0.14.0)
- `pyproject.toml` (0.13.0 → 0.14.0)
- `CHANGELOG.md` (head: 0.14.0)
- `src/shettyxtreme/terminal/web/package.json` (0.13.0 → 0.14.0)

---

## Verification

- Full suite: 1430 passed, 1 skipped, 0 failed
- IAF import grep gate: zero matches outside adapter
- CCXT import grep gate: zero matches
- No file > 1000 lines
- core/ stays external-free (known yaml violation in config_manager.py)
