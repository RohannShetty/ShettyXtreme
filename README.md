# ShettyXtreme

**Unified Indian-market trading intelligence and execution platform.**

ShettyXtreme is a greenfield trading operating system for the Indian market -- combining terminal-grade market exploration, research depth, live decision support, options strategy intelligence, broker-integrated execution (Dhan-first), and modular data pipelines. Built on the shoulders of OpenAlgo, DhanHQ, and ShettyBot intelligence layer.

---

## Philosophy

| Principle | Description |
|-----------|-------------|
| **India-first** | NSE/BSE market structure, instruments, broker reality, trading workflows |
| **Dhan-native** | First-class Dhan integration via DhanHQ-py |
| **OpenAlgo-powered** | Execution plumbing delegated to OpenAlgo, not reinvented |
| **ShettyBot intelligence preserved** | Regime detection, signal interpretation, decision support |
| **Fincept breadth as inspiration** | Multi-asset terminal vision, not blind copy |
| **Update-resilient** | Anti-corruption layers protect core from upstream churn |
| **Phased delivery** | Useful product to powerful platform |

## Reference Repositories

| Repo | Role in Our Architecture |
|------|--------------------------|
| OpenAlgo (github.com/marketcalls/openalgo) | Execution backbone |
| DhanHQ-py (github.com/dhan-oss/DhanHQ-py) | Dhan broker integration |
| ShettyBot V1 (github.com/RohannShetty/ShettyBot_V1_Core) | Intelligence layer evolution |
| FinceptTerminal (github.com/Fincept-Corporation/FinceptTerminal) | Multi-asset terminal reference |
| Fincept Fork (github.com/RohannShetty/FinceptTerminal) | Breadth + research inspiration |

## Project Structure

```
src/shettyxtreme/
  core/           Stable domain: event bus, storage, config, interfaces
  integration/    Anti-corruption layer: OpenAlgo wrapper, Dhan adapter
  intelligence/   Signal engine, regime detection, options AI, risk
  terminal/       UI/UX: research workspace, execution cockpit
  data/           Data pipelines, market data ingestion, historical
  execution/      Order management, portfolio tracking
  risk/           Position sizing, exposure limits, VaR
  options/        Options strategy analysis, Greeks, payoff modeling
  research/       Backtest framework, scanner engine, analytics
  observability/  Logging, metrics, alerting, audit
  plugins/        Plugin system for strategies, data providers, brokers
```

## Development Status

**Phase 0** -- Architecture and Repo Strategy (current)

Full blueprint: docs/architecture/ARCHITECTURE.md

## License

Proprietary -- All Rights Reserved (c) Rohan Shetty
