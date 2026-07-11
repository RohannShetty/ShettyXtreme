# Section 1: Reverse-Engineering Lens

## How Each Reference System Maps Into Our Architecture

### 1.1 OpenAlgo — Execution Backbone (External Dependency)

**Best used as:** Composable external dependency consumed via REST API + WebSocket protocol. Never forked, never embedded.

**Ideas worth inheriting:**
- Broker adapter pattern (clean interface per broker, standardized order models)
- WebSocket subscription management with auto-reconnect
- REST API design for strategy management and order operations
- Multi-broker support model (Dhan, Zerodha, Angel, Kotak, etc.)
- Config-driven broker switching
- Strategy abstraction (though we'll likely build our own on top)

**What NOT to copy directly:**
- The Flask-based API server architecture (we build our own stack)
- The strategy execution engine (too coupled to their model)
- The database schema and persistence layer
- The UI/UX (we build our own terminal)
- Any code that predates v2 architecture (if present)

**Coupling risk:**
- If we import OpenAlgo's Python package directly in core code, upstream breaking changes cascade
- If we depend on OpenAlgo's internal models/classes, refactoring is painful
- If we use OpenAlgo's database directly, schema changes break us

**External dependency vs internal subsystem:**
- OpenAlgo stays EXTERNAL — consumed via HTTP/WebSocket API
- We DO NOT import openalgo package in our core/
- We DO wrap its API behind our own interfaces in integration/

**Harvesting upstream updates:**
- Version pin in requirements.txt (semver-compatible range)
- Integration contract tests validate adapter works with new version
- Changelog-driven: review CHANGELOG.md before bumping version
- Run integration tests against new version in CI before merging

### 1.2 DhanHQ-py — Dhan-Specific SDK (External Dependency)

**Best used as:** Direct dependency for Dhan-specific operations. Used alongside OpenAlgo's Dhan adapter.

**Ideas worth inheriting:**
- Auth token generation (access token + TOTP pattern)
- API client design (endpoints, rate limiting)
- Data models for Indian market structures (scrip codes, series, expiry)
- WebSocket subscription protocol
- Order types specific to Indian brokers (SL, SL-M, AMO, CO, BO)

**What NOT to copy directly:**
- Don't rebuild the HTTP client layer
- Don't rewrite the data parsing
- Don't try to abstract Dhan to match other brokers (that's OpenAlgo's job)

**Coupling risk:**
- Dhan API changes (endpoint deprecation, auth changes)
- SDK version changes with breaking API modifications
- Dhan-specific error handling leaking into our core logic

**External dependency vs internal subsystem:**
- DhanHQ-py is EXTERNAL, consumed as pip package
- Wrapped by DhanAdapter in integration/ for Dhan-specific paths
- Also accessible through OpenAlgo for generic execution

**Harvesting upstream updates:**
- Lock file with exact version for production
- Staging upgrades first, integration tests validate
- DhanAdapter interface isolates core from SDK changes

### 1.3 ShettyBot V1 — Intelligence Layer Origin (Internal Source)

**Best used as:** Reference implementation and source of truth for trading intelligence concepts. Code is extracted, NOT imported.

**Ideas worth inheriting:**
- Regime detection framework (trend, range, volatility states)
- Signal generation pipeline architecture
- Strategy hint / market context system
- Cockpit monitoring concept
- Risk-aware execution thinking
- Decision support logic

**What NOT to copy directly:**
- Monolithic module structure (everything tightly coupled)
- Direct database access patterns
- Coupled broker integration code
- Telegram bot as primary interface
- Legacy OpenAlgo integration (already superseded)

**Coupling risk:**
- If we import ShettyBot modules, we inherit its architectural debt
- If we keep the same data models, we carry forward bad decisions

**External dependency vs internal subsystem:**
- ShettyBot is INTERNAL SOURCE MATERIAL — we extract concepts, not code
- Extracted intelligence logic goes into our intelligence/ module
- NOT consumed as a dependency

**Harvesting updates:**
- ShettyBot V2 development IS this project — it's being evolved, not separately maintained
- V1 remains as reference but receives no further active development

### 1.4 FinceptTerminal — Multi-Asset Terminal Reference (Patterns + Concepts)

**Reverse engineering status:** DONE - cloned, analyzed, and understood (2026-07-12).

**What Fincept Terminal actually is:**
A 342,000-line C++20/Qt6 native desktop monolith - a Bloomberg-style multi-window financial workstation. However, the REAL value is its 1,412 Python analytics scripts that aggregate the entire Python quant ecosystem into a unified terminal, plus a C++ algo trading engine and a SaaS QuantLab (api.fincept.in).

**Key structural relationships to understand:**
1. Their QuantLib screen calls a REMOTE API (api.fincept.in) - the local binary is a thin client
2. Their Indian broker real-time streaming imports OPENALGO streaming adapters - they depend on OpenAlgo same as us
3. Their crypto trading uses CCXT exchange daemon - direct CCXT integration
4. Their Python analytics layer is mostly wrappers around industry-standard libraries

**What we SHOULD learn from Fincept (patterns, not code):**

Domain | Pattern | How We Use It
Options analytics | Their IV surface/smile/strategy charts use Black-76 with JSON I/O convention | Build our own in shettyxtreme/options/ with same analytical depth
Portfolio optimization | Mean-variance, Black-Litterman, risk parity wrappers | Inform shettyxtreme/risk/ design
Data connector architecture | Databento + 25 AkShare modules + CCXT unified pattern | Inform shettyxtreme/data/ pipeline design
Backtesting aggregation | They unified 6 frameworks (backtesting.py, bt, vectorbt, zipline, fasttrade, custom) behind a single interface | Inform shettyxtreme/research/backtest/ architecture
Tool/wrapper pattern | Every analytics domain has a CLI entry point with JSON stdin/stdout convention | Adopt for our research/analytics modules
AlgoTradingService (C++) | A real C++ algorithmic trading engine with strategy scheduling, risk checks, execution hooks | Study architecture patterns, build Python equivalent in shettyxtreme/execution/
Paper trading bridge | Python dataclass models for portfolio/order/position, connects to host paper trading engine | Build into shettyxtreme/execution/paper/ for simulation mode
Exchange daemon | Persistent CCXT worker with JSON-RPC stdin/stdout protocol (eliminates 600-1200ms startup overhead) | Pattern to consider for our OpenAlgo adapter performance
Broker WS bridge | Spawns OpenAlgo streaming adapters as subprocess, captures ZMQ, re-emits normalized JSON | Pattern for our data pipeline subprocess management

**What is NOT useful for ShettyXtreme:**
- NO code can be used (AGPL-3.0 + different tech stack)
- QuantLib C++ screen is a thin client to a SaaS API - no local computation to extract
- 37 AI agent personas (Buffett, Graham, etc.) - our conviction engine is more rigorous
- AkShare Chinese data modules - not India-relevant
- Maritime/geopolitical tracking - zero value for Nifty options
- C++ UI framework - we use Python/Textual

**Fork status:** Same commit as upstream (1511793d). No divergence.

**Upstream health:** Moving to one update/month. Team focused on private paid edition.

**License constraint:** AGPL-3.0. No code can enter ShettyXtreme. Patterns and concepts only.

**Harvesting cadence:** Read quarterly for new patterns. No version pinning or integration tests..