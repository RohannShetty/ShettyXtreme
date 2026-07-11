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

### 1.4 FinceptTerminal — Multi-Asset Terminal Reference (Inspiration Only)

**Best used as:** Product vision and breadth reference. No code consumed.

**Ideas worth inheriting:**
- Multi-asset terminal design thinking
- Research workflow breadth
- CLI + data views paradigm
- Modular data source approach
- "Terminal" aesthetic and information density

**What NOT to copy directly:**
- Absolutely no code is ported
- No architecture patterns are replicated
- No dependency on Fincept packages

**Coupling risk:**
- ZERO — we have no code dependency
- Only risk is design contamination (copying bad patterns)

**External dependency vs internal subsystem:**
- NOT a dependency in any sense
- Fork exists as reference only
- Periodic browsing for ideas (quarterly, low effort)

**Harvesting updates:**
- No harvesting — inspiration only
- Read upstream changes occasionally for new feature ideas
- No compatibility testing, no version pinning, no integration tests
