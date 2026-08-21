# ADR-009: IAF Backtesting Integration

## Status
Accepted (2026-08-12). Re-opens the DECIDED-DEFER on backtest depth (Phase 4, `issues/08-backtest-depth-scope.md`) — the strategy-comparison surface trigger is now met by IAF's `BacktestReport`.

## Context
ShettyXtreme's only backtest is a point-in-time, non-event-driven evaluator (`learning/walkforward.py`) — a library with no runtime caller, no bar loop, no position-sizing rules, no cooldown rules, no slippage, and only Sharpe + max-drawdown metrics. There is no strategy-comparison surface and no backtest engine.

The roadmap recorded "backtest depth" as DECIDED-DEFER since Phase 4 (last re-confirmed 2026-08-06), with trigger = "strategy-comparison surface". IAF's `BacktestReport` is precisely that comparison surface.

**Upstream:** `coding-kitties/investing-algorithm-framework` (~1.6k stars, 1,859 commits). **License: Apache-2.0** (permissive). PyPI package `investing-algorithm-framework`, v8 stable / v9.0.0a2 alpha (breaking OBTF changes). Every capability needed — event-driven backtest, `PositionSize`/`ScalingRule`, `StopLossRule` (trailing), `CooldownRule`, Sharpe/Sortino/Calmar/drawdown — exists in IAF.

## Decision

### 1. What we take from IAF

| Need | IAF facility | Maps to |
|---|---|---|
| Event-driven backtesting | `app.run_backtest` event engine, pluggable slippage/fill models | Replaces walkforward's static `_simulate_exit` |
| Vector screening | `app.run_vector_backtests` (Polars) | Supersedes dead `vectorbt` optional dep |
| Position sizing rules | `PositionSize` (fixed or `percentage_of_portfolio`) | Replaces fixed-lot math; driven by `CalibratedSizing` |
| Scaling rules | `ScalingRule` (`scale_in_percentage`, `max_entries`, `cooldown_in_bars`) | New capability |
| Stop-loss engine | `StopLossRule` (fixed/trailing, partial `sell_percentage`) + `TakeProfitRule` | Ports walkforward TP1-3/TSL policy as declarative rules |
| Cooldown rules | `CooldownRule` (per-symbol/portfolio-wide, side-aware) | New capability |
| Metrics | Sharpe, Sortino, Calmar, drawdown, VaR/CVaR, recovery, profit factor | Upgrades walkforward's Sharpe+max_dd |
| Comparison surface | `BacktestReport` HTML dashboard | The deferred trigger |
| Data seams | Custom data-provider and `OrderExecutor` protocols | Fyers/duckdb historical data in |

### 2. What we exclude

- **CCXT integration** — FR-002/ADR-008: Fyers is primary; crypto venues irrelevant. Excluded at vendor boundary.
- **Cloud deployment** (AWS Lambda / Azure Functions) — out of scope (private-use, ADR-003).
- **IAF's live/paper trading path** — conflicts with D10 OBSERVER-first and our own `integration/fyers/` + `execution/` stack.
- **Finterion marketplace plugin** — monetization out of scope.
- **OBTF storage layer / `iaf` CLI / `BacktestStore`** — optional, defer for v1.

### 3. Dependency admission

Per §05 external-deps table ("new deps require an ADR"), IAF becomes a tracked row:

| Dependency | Version | License | Admission | Notes |
|---|---|---|---|---|
| `investing-algorithm-framework` | v8.x (pinned) | Apache-2.0 | ADR-009 | Vendored; excludes ccxt/cloud/Finterion |

### 4. Vendoring vs pip decision

**Decision: vendor via `scripts/sync_vendor.py`** (openalgo precedent, ADR-002).

Rationale:
- Apache-2.0 makes a plain pip dep legal, but IAF's install pulls ccxt and other unwanted transitive deps.
- Vendoring gives byte-idempotent sync + exclusion control (strip ccxt/cloud/Finterion at source).
- FR-004 ACL holds regardless of mechanism.
- Pin v8 stable (v9 alpha has breaking OBTF/API changes).

### 5. ACL location

The ACL lives at `integration/external/` + a `core/interfaces` Protocol (FR-003/FR-005):
- `core/interfaces/backtest_engine.py` — `BacktestEngine` Protocol
- `integration/external/iaf_adapter.py` — IAF implementation

Nothing above `integration/` imports IAF (FR-004).

### 6. Grep gates

```bash
# Mirrors the openalgo standalone rule
grep -r "import investing_algorithm_framework" src/   # must be zero outside the adapter
grep -r "import ccxt" src/ vendor/                    # must be zero
```

## Consequences

- `vendor/iaf/` added alongside `vendor/openalgo/`.
- `integration/external/` package created for IAF adapter.
- `core/interfaces/backtest_engine.py` adds `BacktestEngine` Protocol.
- `learning/walkforward.py` stays as legacy; new `learning/backtest.py` provides `run_backtest` API over the adapter.
- Dead `vectorbt` optional dep removed from `pyproject.toml`.
- Version bumped to 0.14.0 across the 5 drifted files.
- ADR index updated in `docs/architecture/v2/ARCHITECTURE_V2.md`.

## References

- Findings: `docs/superpowers/plans/2026-08-12-p2-3-4-backtesting-findings.md`
- Deferral record: `.scratch/phase4-knowledge-dashboards/issues/08-backtest-depth-scope.md`
- Re-evaluation: `docs/superpowers/plans/2026-08-05-phase7w4-decided-defer.md`
- Upstream: `coding-kitties/investing-algorithm-framework` (Apache-2.0)
