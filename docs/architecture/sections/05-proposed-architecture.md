# Section 5: Proposed Architecture

## Architecture Layers

```
  TERMINAL LAYER (Research Workspace | Execution Cockpit | Monitoring)
       |
  INTELLIGENCE LAYER (Regime | Signal | Options AI | Risk)
       |
  CORE PLATFORM (Event Bus | Storage | Config | Plugin Loader)
       |
  INTEGRATION LAYER (OpenAlgoAdapter | DhanAdapter | DataProvider)
       |
  EXTERNAL DEPS (OpenAlgo Server | DhanHQ-py | Data APIs)
```

## Core/Event Bus
- In-process pub/sub via asyncio
- Events: MarketDataReceived, SignalGenerated, OrderPlaced,
  FillReceived, PositionChanged, RiskAlert, ConfigChanged
- Decouples producers from consumers

## Core/Storage
- KV: instrument master, configs, prefs (SQLite)
- Time-series: bars, ticks, indicators (DuckDB)
- Document: journal, research notes (JSON/Markdown)
- Accessed via StorageProtocol interfaces

## Core/Config
- YAML + env var overrides
- Secrets from env vars (never git-committed)
- Pydantic validation models

## Data Pipeline
- WebSocket stream manager (OpenAlgo + Dhan)
- Bar builder: tick to EOD aggregation
- Gap detection: overnight and intraday
- Historical fetcher with local cache
- All published to event bus

## Execution Engine
- Thin wrapper over OpenAlgoAdapter
- Pre-execution risk checks
- Order lifecycle tracking
- Position aggregation
- No broker-specific logic (delegated)

## Signal Engine
- Consumes event bus market data
- Runs registered generators
- Outputs scored signals with metadata

## Regime Engine
- Analyzes: trend, range, volatility, momentum
- Multiple timeframes
- Drives strategy hints and risk params

## Options Intelligence
- Greeks computation
- IV surface construction
- Strategy analysis (payoff, breakeven, POP)
- Chain scanner (unusual activity, skew)
- Scenario analysis

## Risk Engine
- Per-strategy and portfolio limits
- Stop-loss management
- Exposure tracking
- Drawdown monitoring
- Position sizing calculators

## Observability
- Structured logging (structlog)
- Metrics for latencies/volumes/errors
- Health checks
- Session audit log
- Configurable alert rules

## Plugin System
- Strategies, scanners, providers as plugins
- Protocol-based interface
- Python packages from configured dirs

## Runtime Modes

| Mode | Data | Execution | Use |
| Backtest | Historical | Simulated | Evaluation |
| Simulation | Live/Delayed | Simulated | Tuning |
| Observer | Live | Read-only | Monitoring |
| Live | Live | Real | Production |
| Paper | Live | Paper | Rehearsal |

## UI Strategy
Phase 1-2: Local terminal UI (Rich + Textual)
Phase 3-4: Web API layer for cloud/SaaS mode
