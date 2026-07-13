# Section 5: SYSTEM BOUNDARIES

> **CORRECTED from earlier session**: Integration layer no longer wraps OpenAlgo as external service. It contains first-party Dhan adapters absorbed from OpenAlgo patterns.

### A) Core Platform (`core/`) — STABLE

**Purpose:** Stable foundation that everything depends on. Changes slowly.

**What belongs:**
- Domain models (Instrument, Order, Position, Signal — frozen dataclasses)
- Event bus (asyncio pub/sub) + event types
- Contracts/interfaces (OrderExecutor, MarketDataStream, AccountInfo protocols)
- Config system (YAML + env loading + pydantic validation)
- Storage abstraction (DuckDB time-series + SQLite KV + migrations)
- Session state (market calendar, session lifecycle, runtime mode)
- Health check interfaces

**What does NOT belong:**
- Any broker-specific code
- Any DhanHQ imports
- Any httpx imports
- Signal logic, strategy logic, UI code, research code

**Import rule:** Zero external imports (only stdlib + own subpackages)
**Stability:** HIGH — core interfaces change only through ADRs

### B) Integration Layer (`integration/`) — SWAPPABLE

**Purpose:** Anti-corruption layer between core and external systems.

**What belongs:**
- Dhan Trading Adapter (first-party, using DhanHQ-py) — order placement, positions, holdings, EDIS, margin, auth with auto-refresh
- Dhan Data Adapter (first-party, using DhanHQ-py, separate credentials) — live market feed WS, historical OHLC, OI/PCR
- Order validation (absorbed from OpenAlgo constants + logic)
- Symbol/instrument master (first-party, seeded from Dhan API)
- Code absorbed from OpenAlgo (marked with origin markers in `_absorbed/`)

**What does NOT belong:**
- Core business logic, signal intelligence, UI rendering, storage implementations

**Import rule:** imports core/interfaces + external APIs (DhanHQ-py, httpx)
**Stability:** MEDIUM-HIGH

### C) Intelligence Layer (`intelligence/`) — RAPID EVOLUTION

**Purpose:** The unique value — trading intelligence.

**What belongs:**
- `features/` — Streaming feature computation (O(1) per tick: bars, MA, ATR, ADX, VWAP, PCR, OI, IV)
- `regime/` — Regime classifier (no Markov on 1m noise, coarser bars)
- `signals/` — Voter plugin system, conviction computation, D/P/G, NEUTRAL state
- `voters/` — Individual voter plugins (each in own file)
- `options/` — IV analysis, OI analysis, PCR context, expiry/strike selection
- `risk/` — Position sizing, loss limits (entries only), margin guardrails, composable filter chain
- `scanners/` — Gap detection, opportunity clusters

**What does NOT belong:**
- Order execution, data storage, UI, broker-specific logic

**Import rule:** imports core only
**Stability:** RAPID — our unique value

### D) Execution Layer (`execution/`) — Phase 2+

**What belongs:**
- Order lifecycle, position management (TP1/TP2/TP3 with FIXED ordering, TSL, EOD close)
- Semi-auto approval, one canonical stop-loss definition (premium-relative, vol-aware)

**Import rule:** imports core + integration/contracts

### E) Learning Layer (`learning/`) — Phase 2+

**What belongs:**
- Outcome tracking (immutable signal_decisions + execution_attempts + outcome_labels)
- Per-voter quality tracking (CONSUMED — feeds back to weight adjustments)
- MFE/MAE computation, walkforward with honest evaluation, calibration

**Import rule:** imports core only

### F) Terminal Layer (`terminal/`) — FAST EVOLUTION

**What belongs:**
- FastAPI backend (REST + WS endpoints)
- Web frontend using taste-skill (industrial-brutalist-ui) + ui-ux-pro-max-skill
- Panels: Watchlist, Intelligence Cockpit, Execution Cockpit, Scanner/Alerts/Logs

**Import rule:** imports core + intelligence (read models) + execution (commands)

### G) Knowledge Layer (`knowledge/`) — Phase 3+

**What belongs:**
- Document store, tagger, heuristic extractor, knowledge linker

**Import rule:** imports core only; CANNOT import intelligence or execution (physical separation)

### H) Observability Layer (`observability/`)

**What belongs:**
- Structured logging, latency metrics, health checks, session audit log

**Import rule:** imports core only

### External Dependencies

| Dependency | How Used | Strategy |
|------------|----------|----------|
| DhanHQ-py | pip package | Lock file, exact version pin |
| DuckDB | pip package | Semver range for analytics/time-series |
| httpx | pip package | For async HTTP if needed beyond DhanHQ-py |
| pydantic | pip package | >=2.0 for config validation |

### Future Expansion Layer

- Additional brokers via new adapters (implement core protocols)
- Additional data providers via new adapters
- AI-assisted workflows via plugins
- SaaS/cloud mode
- Community plugin SDK
- Knowledge ingestion pipeline (Phase 3+)

---

