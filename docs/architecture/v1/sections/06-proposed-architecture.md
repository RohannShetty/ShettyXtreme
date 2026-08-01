# Section 6: PROPOSED ARCHITECTURE

> **CORRECTED from earlier session**: No OpenAlgo as external service. No Textual TUI. First-party Dhan adapters. Web-based terminal.

### Layer Diagram

```
  TERMINAL LAYER (FastAPI + Web Frontend — taste-skill + ui-ux-pro-max-skill)
       │
  EXECUTION LAYER (Order Lifecycle | Position Mgmt | Semi-auto)
       │
  INTELLIGENCE LAYER (Regime | Signal Engine | Voters | Options Intel | Risk | Scanners)
       │
  CORE PLATFORM (Domain Models | Event Bus | Contracts | Config | Storage | Session)
       │
  INTEGRATION LAYER (Dhan Trading Adapter | Dhan Data Adapter | Instrument Master)
       │
  EXTERNAL DEPS (DhanHQ-py pip | Dhan APIs)
```

### Core Data Flow

```
Dhan Data WS → Dhan Data Adapter → Event Bus (MarketDataReceived)
    ↓
Feature Engine (streaming O(1)/tick) → Event Bus (FeaturesComputed)
    ↓
Regime Classifier → Event Bus (RegimeUpdated)
    ↓
Signal Engine (voters → conviction → D/P/G) → Event Bus (SignalGenerated)
    ↓
Options Intelligence (IV rank, PCR, strike EV) → Strategy Hint
    ↓
Risk Engine (entries only, cost-aware) → Event Bus (RiskAssessed)
    ↓
[If OBSERVER mode: display in terminal UI]
[If LIVE mode: Execution Engine → Dhan Trading API → Event Bus (OrderPlaced)]
    ↓
Learning Loop → Outcome Tracking → Voter Quality → Weight Adjustment
```

### Storage Model

- **DuckDB** (time-series): bars, ticks, indicators, option chain snapshots, OI history
- **SQLite** (KV): instrument master, configs, session state, signal log, trade log
- **File-based**: kill switch (independent of platform), journal entries (markdown)

### Runtime Modes

| Mode | Data | Execution | Use |
|------|------|-----------|-----|
| Backtest | Historical | Simulated | Evaluation |
| Simulation | Live/Delayed | Simulated | Tuning |
| Observer | Live | Read-only | Monitoring (Phase 2 MVP) |
| Live | Live | Real (semi-auto) | Production (Phase 3) |
| Paper | Live | Paper | Rehearsal |

### Plugin System

- Strategies, scanners, voters as plugins
- Protocol-based interface
- Python packages from configured dirs
- Registry for discovery (not hardcoded imports)

---

