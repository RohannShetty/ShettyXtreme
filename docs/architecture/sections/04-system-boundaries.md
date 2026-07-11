# Section 4: System Boundaries

## A) Core Platform (shettyxtreme.core)

**Purpose:** Stable foundation that everything depends on. Changes slowly.

**What belongs:**
- Event bus (pub/sub message passing)
- Configuration system (YAML + env + CLI)
- Storage abstraction (key-value, time-series, document)
- Instrument master data model
- Market data models (Bar, Tick, Quote, OHLCV)
- Order models (Order, Fill, Position, Trade)
- Timer/scheduler infrastructure
- Error types and domain exceptions
- Plugin loader interface (Protocol/ABC)
- Logging and metrics interfaces

**What does NOT belong:**
- Any broker-specific code
- Any OpenAlgo imports
- Any DhanHQ imports
- Signal logic
- Strategy logic
- UI code
- Research/analysis code

**Stability:** HIGH - core interfaces change only through ADRs

## B) Integration Layer (shettyxtreme.integration)

**Purpose:** Anti-corruption layer between core and external systems.

**What belongs:**
- OpenAlgoAdapter - Wraps OpenAlgo API behind core interfaces
- DhanAdapter - Wraps DhanHQ-py for Dhan-specific operations
- DataProviderAdapter - Interface + implementations for data sources
- BrokerAdapter - Multi-broker abstraction via OpenAlgo
- Contract tests for each adapter
- Vendor-specific model transformers

**What does NOT belong:**
- Core business logic
- Signal intelligence
- UI rendering
- Storage implementations

**Stability:** MEDIUM-HIGH

## C) Intelligence Layer

**Purpose:** The unique value - trading intelligence.

**What belongs:**
- intelligence/regime/ - Regime detection
- intelligence/signals/ - Signal generation and scoring
- intelligence/hints/ - Market context and strategy hints
- intelligence/scanners/ - Gap/opportunity scanning
- risk/ - Position sizing, exposure limits, VaR
- options/ - Greeks engine, IV surface, strategy analysis

**What does NOT belong:**
- Order execution
- Data storage
- UI
- Broker-specific logic

## D) Terminal Layer

**Purpose:** The operator interface.

**What belongs:**
- Research workspace
- Execution cockpit
- Market terminal
- Strategy hints panel
- Session controls
- Logs and alerts
- Journaling interface

## E) External Dependencies

| Dependency | How Used | Strategy |
| OpenAlgo | REST + WS | Pinned, semver |
| DhanHQ-py | pip package | Lock file |
| httpx/websockets | pip | Semver range |
| pydantic | pip | >=2.0 |

## F) Future Expansion

- Additional brokers via new adapters
- Additional data providers
- AI-assisted workflows via plugins
- SaaS/cloud mode
- Community plugin SDK
