# ShettyXtreme - Project Context

## Core Identity
ShettyXtreme is a greenfield Indian-market trading intelligence and execution platform. It is NOT a broker wrapper, NOT a charting tool, and NOT a strategy bot alone. It is a trading operating system combining terminal-grade research, live decision support, options intelligence, and broker-integrated execution.

## Architecture Principles
1. **India-first** - NSE/BSE structure, instruments, workflows are baked in
2. **Dhan-native** - Dhan is first-class, not an afterthought
3. **OpenAlgo-powered** - Execution plumbing is delegated to OpenAlgo
4. **ShettyBot intelligence preserved** - Regime detection, signal interpretation, decision support remain
5. **Update-resilient** - Anti-corruption layers between core and upstream dependencies
6. **Interface-driven** - Every integration point has a defined contract

## Key Reference Repos
- github.com/marketcalls/openalgo - Execution backbone
- github.com/dhan-oss/DhanHQ-py - Dhan broker SDK
- github.com/RohannShetty/ShettyBot_V1_Core - Intelligence layer
- github.com/Fincept-Corporation/FinceptTerminal - Terminal reference

## Project Structure
```
src/shettyxtreme/
  core/           - Stable domain, interfaces, event bus, config, storage
  integration/    - Anti-corruption layer for externals
  intelligence/   - Signals, regimes, options AI, risk
  terminal/       - UI/UX workspace and cockpit
  data/           - Market data ingestion pipelines
  execution/      - Order management via OpenAlgo
  risk/           - Position sizing, exposure, VaR
  options/        - Options strategy analysis
  research/       - Backtesting, scanners, analytics
  observability/  - Logging, metrics, alerting
  plugins/        - Extension system
```

## Naming Conventions
- Package: shettyxtreme
- Core interfaces: I{Name}Protocol or abstract base
- Integration adapters: {Vendor}Adapter
- Signals: {Name}Signal
- Risk models: {Name}RiskModel
- Tests: test_{module}.py

## Phase Status
Phase 0 - Architecture and Repo Strategy (active)
Phase 1 - Foundations (next)
Phase 2 - Usable MVP
Phase 3 - Advanced Intelligence
Phase 4 - Platform Maturity
