# Section 19: REPO / CODEBASE STRATEGY

### Recommendation: Modular Monolith with Plugin-Based Intelligence

**Not microservices**: Single operator, single machine. Microservices add operational overhead without proportional benefit.

**Not pure monolith**: ShettyBot V1's monolith created god modules (2,702 + 3,381 lines). We need strict internal boundaries.

**Not plugin-only core**: Too loosely coupled for trading safety. Execution and risk need tight integration.

**The answer**: Modular monolith with:
- Stable core (domain models, event bus, contracts, storage, config)
- Fast-evolving intelligence layer (voters as plugins, strategies as YAML)
- Swappable integration layer (broker adapters)
- Replaceable UI layer (web-based, separate from backend)
- Plugin registry for discovery

### Package Boundaries

```
shettyxtreme/
├── core/              # STABLE: domain models, event bus, contracts, config, storage
│   ├── domain/        # Instrument, Order, Position, Signal, etc. — zero external imports
│   ├── events/        # Event bus, event types
│   ├── interfaces/    # OrderExecutor, MarketDataStream, AccountInfo protocols
│   ├── config/        # YAML + env loading + validation
│   ├── storage/       # DuckDB/SQLite abstractions + migrations
│   └── session/       # Market calendar, session lifecycle, runtime mode
├── integration/       # SWAPPABLE: broker adapters, data source adapters
│   ├── dhan/          # Dhan Trading Adapter + Dhan Data Adapter (first-party code)
│   ├── contracts/     # (re-exports core interfaces for convenience)
│   └── _absorbed/     # Code absorbed from OpenAlgo (marked with origin markers)
├── intelligence/       # RAPID EVOLUTION: our unique value
│   ├── features/      # Streaming feature computation
│   ├── regime/        # Regime classifier
│   ├── signals/       # Voter plugin system, conviction, D/P/G
│   ├── voters/        # Individual voter plugins (each in own file)
│   ├── options/       # IV analysis, OI analysis, PCR context, expiry/strike selection
│   ├── risk/          # Position sizing, loss limits, margin guardrails, filter chain
│   ├── scanners/      # Gap detection, opportunity clusters
│   └── anticipation/  # Regime transition, divergence tracking (Phase 3)
├── execution/         # Order lifecycle, position management, semi-auto
├── learning/          # Outcome tracking, MFE/MAE, walkforward, calibration
├── terminal/          # FastAPI backend + web frontend assets
│   ├── api/           # REST + WS endpoints
│   └── static/        # Frontend (React/Svelte + taste-skill + ui-ux-pro-max-skill)
├── knowledge/         # Phase 3+: document store, tagger, heuristic extractor
├── observability/     # Structured logging, metrics, health checks
└── plugins/           # Plugin discovery, adapter registry
```

### Import Rules (Enforced by CI)

```
core/           → imports NOTHING external (only stdlib + own subpackages)
intelligence/   → imports core/ only
integration/    → imports core/interfaces/ + external APIs (DhanHQ-py, httpx)
execution/      → imports core/ + integration/contracts
learning/       → imports core/ only
terminal/       → imports core/ + intelligence/ (read models) + execution/ (commands)
knowledge/      → imports core/ only; CANNOT import intelligence/ or execution/
observability/  → imports core/ only
```

CI check:
```bash
# core has zero external imports
! grep -r "import dhanhq\|import httpx\|import duckdb\|import openalgo" src/shettyxtreme/core/
# intelligence doesn't import integration
! grep -r "from.*integration\|import.*integration" src/shettyxtreme/intelligence/
# no file > 500 lines
! find src -name "*.py" -exec wc -l {} + | awk '$1 > 500'
```

---

