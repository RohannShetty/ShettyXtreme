# P2-3.4 — Backtesting Engine (IAF adapter) — Spec

**Date:** 2026-08-12
**Status:** IMPLEMENTING
**Trigger:** Strategy-comparison surface (IAF `BacktestReport` meets the DECIDED-DEFER trigger)

---

## Problem

ShettyXtreme's only backtest is a point-in-time, non-event-driven evaluator (`learning/walkforward.py`) — it is a library with no runtime caller, no bar loop, no position-sizing rules, no cooldown rules, no slippage, and only Sharpe + max-drawdown metrics. There is no strategy-comparison surface and no backtest engine.

## Solution

Vendor `investing-algorithm-framework` (IAF) and build an adapter behind an ACL.

### What we take from IAF

- Event-driven backtest engine (`app.run_backtest`)
- Vector screening (`app.run_vector_backtests`, Polars)
- Position sizing rules (`PositionSize`)
- Scaling rules (`ScalingRule`)
- Stop-loss/take-profit rules (`StopLossRule`, `TakeProfitRule`)
- Cooldown rules (`CooldownRule`)
- Metrics (Sharpe, Sortino, Calmar, drawdown, VaR/CVaR, profit factor)
- Comparison surface (`BacktestReport`)

### What we exclude

- CCXT integration (crypto venues irrelevant)
- Cloud deployment (AWS Lambda / Azure Functions)
- Live/paper trading path (conflicts with D10 OBSERVER-first)
- Finterion marketplace plugin
- OBTF storage layer / iaf CLI

### ACL boundary

- `core/interfaces/backtest_engine.py` — `BacktestEngine` Protocol (FR-005)
- `integration/external/iaf_adapter.py` — IAF implementation (FR-004)
- Nothing above `integration/` imports IAF

### Vendoring

- Via `scripts/sync_vendor.py` (openalgo precedent, ADR-002)
- `vendor/iaf/` with `FILES.yaml`, `ORIGIN.md`, `LICENSE`, `README.md`
- Pin v8 stable (v9 alpha has breaking OBTF changes)
- Apache-2.0 license (permissive)

### Data

- Historical bars from `integration/fyers/` + DuckDB TS
- India session-aware (FR-001)
- "Backtest path = live path" honesty (§14)

### Landing surface

- `learning/backtest.py` — `BacktestRunner` API over the adapter
- Replaces `learning/walkforward.py` (walkforward stays as legacy)
- Results feed `BacktestReport` for comparison dashboard

### Housekeeping

- Drop dead `vectorbt` optional dep (`pyproject.toml`)
- Add IAF optional dep (`investing-algorithm-framework>=8.0,<9.0`)
- IAF import grep gate
- Version bump to 0.14.0 (5 files)

---

## References

- Findings: `docs/superpowers/plans/2026-08-12-p2-3-4-backtesting-findings.md`
- ADR-009: `docs/decisions/ADR-009-iaf-backtesting-integration.md`
- Deferral: `.scratch/phase4-knowledge-dashboards/issues/08-backtest-depth-scope.md`
