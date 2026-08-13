# Vendored: investing-algorithm-framework

**Upstream:** [coding-kitties/investing-algorithm-framework](https://github.com/coding-kitties/investing-algorithm-framework)
**License:** Apache-2.0 (permissive — unlike openalgo's AGPL-3.0)
**Version pinned:** v8.x stable (v9 alpha has breaking OBTF changes)
**Vendored:** 2026-08-12 via `scripts/sync_vendor.py`

## What is vendored

- Core models: TradingStrategy, PositionSize, ScalingRule, StopLossRule, TakeProfitRule, CooldownRule, TradingCost, MarketDataType
- Backtesting engine: event-driven backtest, vector backtest (Polars)
- Metrics calculator: Sharpe, Sortino, Calmar, drawdown, VaR/CVaR, profit factor
- BacktestReport: HTML comparison dashboard

## What is excluded (per ADR-009)

- **CCXT integration** — crypto venues irrelevant (FR-002/ADR-008: Fyers primary)
- **Cloud deployment** (AWS Lambda / Azure Functions) — out of scope (private-use, ADR-003)
- **Live/paper trading path** — conflicts with D10 OBSERVER-first and our own execution stack
- **Finterion marketplace plugin** — monetization out of scope
- **OBTF storage layer / iaf CLI / BacktestStore** — optional, defer for v1

## Usage

The IAF adapter lives at `integration/external/iaf_adapter.py` (FR-004 ACL).
Nothing above `integration/` imports IAF directly.

```python
from shettyxtreme.integration.external.iaf_adapter import IAFBacktestAdapter
```

## Re-sync

To update from upstream:

1. Clone upstream mirror to `references/upstream/iaf/`
2. Update `FILES.yaml` with new file list
3. Run `python scripts/sync_vendor.py --vendor-dir vendor/iaf --files-yaml vendor/iaf/FILES.yaml --mirror references/upstream/iaf --apply`
4. Review diff, update this README and ORIGIN.md
