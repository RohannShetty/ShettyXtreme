# ShettyXtreme — Complete Research Audit & Architecture Blueprint

> **Status:** Research-first audit, not implementation directive.
> **Date:** July 12, 2026
> **Scope:** Re-evaluation of the ShettyXtreme product direction from first principles.
> **Prior work assessed:** ShettyBot V1 Core (v1.5.19), prior ShettyXtreme 17-section blueprint, ShettyBot V2 Architecture Blueprint.
> **Critical correction (user-directed):** ShettyXtreme is STANDALONE software. NO runtime dependency on OpenAlgo or any third-party service. Patterns and code are absorbed/copied/modified from reference repos, but ShettyXtreme runs as independent software.

---

## SECTION 0 — RESEARCH METHOD

**How we evaluated the repos:**
- Deep-dived 7 reference repos via 3 parallel research sub-agents (OpenAlgo architecture, ShettyBot V1 intelligence, DhanHQ-py/OpenBB/Fincept/AST)
- Read ShettyBot V1's full architecture blueprint (66K chars), intelligence audit (54K chars), Markov investigation, and transition charter
- Cloned and studied both UI/UX skill repos (taste-skill, ui-ux-pro-max-skill)

**How we separated product ideas from implementation details:**
- For each repo, identified *what* it does well vs *how* it implements it
- Ideas/patterns/concepts = candidate for absorption; implementation specifics = evaluated case by case
- ShettyBot V1's monolithic code = extract concepts, not code

**How we distinguished reusable architecture from repo-specific noise:**
- Asked: "Does this pattern transfer to a standalone Python platform for Indian options?" If no = noise
- Fincept's C++20/Qt6 code = noise; their analytics breadth signal = signal
- OpenAlgo's Flask/React stack = noise; their broker adapter pattern = signal

**How we checked for blind spots:**
- Used Awesome Systematic Trading as a category checklist
- Compared our planned features against the catalog's categories
- Identified gaps: cost modeling, streaming TA, execution profiling, pre-trade risk gate

**How we avoided bias toward the current direction:**
- Started from first principles: "What does an Indian prosumer options trader actually need?"
- Questioned every prior decision: OpenAlgo dependency (wrong), Textual TUI (wrong), Markov voter (misleading), risk-neutral EV (noise)
- User directive to challenge everything was taken literally

---

## SECTION 1 — REVERSE-ENGINEERING LENS

### OpenAlgo — Execution Infrastructure (Absorb, Don't Depend On)

> **CORRECTED from earlier session**: Earlier plan said "compose with OpenAlgo as external dependency." User directed: NO runtime dependency. Absorb patterns as first-party code.

| Aspect | Decision |
|--------|----------|
| **Best used as** | Pattern source for broker adapter design, order validation, WebSocket architecture |
| **Inherit** | Broker adapter pattern (plugin.json discovery, standardized module structure), order validation constants, WebSocket proxy architecture concept, Options Tools (12 tools including Option Chain, IV Smile, Max Pain, GEX, Vol Surface) |
| **Don't copy** | Flask/Flask-RESTX backend, React frontend, single-worker Gunicorn constraint, ZMQ subprocess architecture |
| **Coupling risk** | If we import openalgo package → brittle. Solution: absorb adapter pattern + Dhan adapter code as first-party |
| **External vs internal** | Absorb as internal first-party code in `integration/`. Not an external dependency. |
| **Upstream harvest** | Monitor repo changes, review diffs, selectively absorb improvements via human review (not auto-merge) |
| **Blind spots revealed** | OpenAlgo has NO signal generation, NO regime detection, NO portfolio/risk management, NO backtesting — ShettyXtreme must fill all of these |

### ShettyBot V1 — Intelligence DNA (Extract Concepts, Fix Bugs)

| Aspect | Decision |
|--------|----------|
| **Best used as** | Reference for trading intelligence concepts. Code is extracted, NOT imported. |
| **Inherit** | Regime detection framework, conviction scoring concept, options-flow voter concept, shadow model concept, learning loop concept, cockpit thinking |
| **Don't copy** | Monolithic module structure, god modules (2,702 + 3,381 lines), direct database access patterns, Telegram bot as primary interface, hardcoded strategies |
| **Coupling risk** | If we import ShettyBot modules, we inherit architectural debt |
| **External vs internal** | Internal source material — extract concepts, reimplement cleanly |
| **Blind spots revealed** | 10 critical bugs: risk-neutral GBM noise for strike selection, loss-limit freezing position management, unreachable TP3, OI voter time-of-day bias, dead voters diluting confidence, forced bearish tie-break, no NEUTRAL state, no cost model, 3 inconsistent stop-loss definitions, ML voter with AUC 0.518 (random) |

### DhanHQ-py — Dhan Broker SDK (Pip Dependency)

| Aspect | Decision |
|--------|----------|
| **Best used as** | Direct pip dependency for Dhan API calls |
| **Inherit** | API client design, data models for Indian market, WebSocket subscription protocol |
| **Don't copy** | Don't rebuild HTTP client layer, don't rewrite data parsing |
| **Coupling risk** | Dhan API changes (endpoint deprecation, auth changes), SDK version changes, DhanHQ-py has NO auto-refresh and NO retry logic |
| **External vs internal** | External pip dependency — wrapped by our Dhan Trading Adapter + Dhan Data Adapter |
| **Upstream harvest** | Lock file with exact version, staging upgrades first, integration tests validate |
| **Blind spots revealed** | Dual credentials required (Trading ≠ Data API, error 806 if mixed), token expiry ~3AM IST, sync HTTP only, separate WS for live data (binary protocol), Super Orders/Forever Orders not in OpenAlgo |

### Fincept Terminal — Terminal Breadth Reference (Ideas Only)

| Aspect | Decision |
|--------|----------|
| **Best used as** | Breadth reference for what a serious terminal product covers |
| **Inherit** | Multi-asset thinking, research workflow concepts, analytics breadth (1,412 Python analytics scripts), options analytics concepts, backtesting framework aggregation pattern |
| **Don't copy** | C++20/Qt6 code (different stack entirely), AGPL-3.0 license prohibits code reuse, SaaS QuantLab API dependency |
| **Coupling risk** | Zero — no code enters ShettyXtreme |
| **External vs internal** | External — patterns and concepts only |
| **Blind spots revealed** | Our scope is narrower (India-first, options-first, single-broker) but deeper in intelligence |

### OpenBB — Research Platform Patterns (Selective Inspiration)

| Aspect | Decision |
|--------|----------|
| **Best used as** | Architecture pattern reference for research platform design |
| **Inherit** | Plugin/extension system for data providers, research workspace concept, tool discovery pattern for AI agents, single-source API definition pattern (one definition → FastAPI endpoint + Python SDK + MCP tool) |
| **Don't copy** | Actual data provider implementations (US/global), web framework choices, enterprise workspace, crypto/forex modules |
| **Coupling risk** | Zero — no code enters ShettyXtreme |
| **External vs internal** | External — patterns only |
| **Blind spots revealed** | We need a research workspace (not just live monitoring), and future MCP compatibility for AI-assisted research |

### Awesome Systematic Trading — Blind-Spot Checklist

| Aspect | Decision |
|--------|----------|
| **Best used as** | Category coverage checklist to ensure we're not missing important capabilities |
| **Inherit** | Awareness of: cost modeling, streaming TA, execution profiling, pre-trade risk gates |
| **Don't copy** | Any code — this is a curated link list, not a codebase |
| **Blind spots revealed** | Missing: cost modeling (no slippage/spread/brokerage), streaming TA (recomputing from scratch each cycle), execution profiling, pre-trade risk gate (bypassed on loss-limit breach) |

---

## SECTION 2 — RE-AUDIT OF THE CURRENT DIRECTION

### What Is Probably Right

- **Product vision**: Unified intelligence + execution + research terminal for Indian market
- **Dhan-first**: Correct broker choice for API quality and cost
- **Regime-awareness**: Markets do have regimes and trading should adapt
- **Operator-in-the-loop**: Semi-auto is safer than full auto for a prosumer product
- **Conviction-based signals**: Better than single-indicator signals
- **Shadow model concept**: Validate before activating

### What Is Probably Wrong (Architecture)

- **OpenAlgo as runtime dependency** → ShettyXtreme becomes a client of OpenAlgo. If OpenAlgo breaks, changes, or is unmaintained, ShettyXtreme breaks. **CORRECTED: standalone software.**
- **Textual TUI** → Limited interactivity, no real-time charts, no web access, hard to extend. **CORRECTED: web-based terminal.**
- **Composing with ShettyBot V1 code** → Inherits god modules and architectural debt. **CORRECTED: reimplement concepts.**

### What Is Probably Wrong (Intelligence)

- **Risk-neutral GBM for strike selection** → Noise optimization, not edge. GBM produces random strike rankings. **Fix: signal-drift EV.**
- **Loss limit freezes ALL trading** → Position management stops too. TSL and TP targets don't run on existing positions. **Fix: entries only.**
- **TP3 unreachable** → `update_tsl` runs before `check_targets`. **Fix: check_targets before update_tsl.**
- **No NEUTRAL state** → Forces UP or DOWN when voters disagree. **Fix: explicit NEUTRAL.**
- **OI voter time-of-day bias** → Raw OI compared across session. OI builds from open to close. **Fix: time-of-day percentile normalization.**
- **Dead voters dilute confidence** → ML voter (AUC 0.518 = random) and HMM voter contribute to D/P/G. **Fix: remove dead voters.**
- **No cost model** → Marginal strategies pass as profitable. **Fix: cost model in all EV.**
- **3 inconsistent stop-loss definitions** → **Fix: one canonical definition.**

### What Is Missing (Product)

- **Dhan Trading vs Data API split** → Two separate auth flows, two WS connections, different rate limits, different failover behavior.
- **Knowledge ingestion layer** → No way to feed reports, books, or strategy notes into the system.
- **Cost model** → No slippage/spread/brokerage in any EV computation.
- **Streaming TA** → Features recomputed from scratch each cycle (O(n) not O(1)).
- **Execution profiling** → No latency measurement from tick to signal to order.

### Architecture Smells

- **Terminal vs bot vs platform confusion**: ShettyBot V1 was a bot (Telegram), V2 blueprint tried to be a platform, but the terminal aspect was underspecified.
- **Analytics vs execution boundary confusion**: ShettyBot V1 mixed analytics (regime detection) with execution (order placement) in the same monolith.
- **Knowledge system vs trading system confusion**: No clear boundary between "what the system knows" and "what the system does."
- **Circular assumption**: Regime detection drives signal generation → signal generation validates regime detection. Without independent validation, this is circular.

---

## SECTION 3 — PRODUCT VISION

### What Problem It Solves

Indian prosumer traders use 4-7 disconnected tools (broker terminal, analytics platform, options analyzer, scanner, journal, risk monitor) to trade. This fragmentation costs money, time, and context. ShettyXtreme unifies the entire workflow into one standalone application.

### Who It's For First

The **prosumer Indian trader** who:
- Trades NSE/BSE equities, indices, and options (especially weekly expiry options)
- Uses Dhan as their broker
- Wants more than a broker terminal but less than a Bloomberg terminal
- Values intelligence and decision support over charting
- Runs a local application on their machine

### Why It's Better

| vs Broker Terminal | vs Analytics Terminal | vs Strategy Bot |
|--------------------|---------------------|----------------|
| Includes research, scanning, analytics, and decision support | Integrated execution — no "analyze here, trade there" gap | Full platform, not just signals |
| Not just order entry — covers full workflow | India-specific market structure is first-class | Research and analytics workspace |
| Regime-aware intelligence | Options intelligence beyond Greeks | Manual + automated execution |
| Conviction-based signals | Live decision support, not just historical | Operator-in-the-loop design |

### How It Helps Make Money

- **Gap identification**: Scanner detects anomalies, divergences, unusual activity
- **Regime shifts**: Early detection of trend changes, volatility expansion
- **Options structure**: Identify skewed IV, mispriced spreads, PCR contrarian signals
- **Risk awareness**: Avoid blow-ups by knowing exposure before it hurts
- **Cost-aware EV**: No marginal strategies passing as profitable (slippage/spread/brokerage in all EV)
- **Learning loop**: Every signal tracked, every outcome fed back to improve voter weights

### How It Thinks About Market Anticipation

**Not prediction.** The platform outputs conditions, not predictions. "Conditions X, Y, Z present, which historically precede outcome W with estimated probability P." Uncertainty is visible (conviction score, disagreement indicator, participation level).

### What "Unified Platform" Means in Practice

One standalone application where:
- One data model serves research, live monitoring, and backtesting
- One execution abstraction works for manual and automated orders
- One risk engine applies across all strategies and positions
- One terminal interface provides research, execution, and monitoring
- One plugin system allows extension without modifying core
- One intelligence engine generates conviction-based signals with full explainability

---

## SECTION 4 — INDIA-FIRST SCOPE

### NSE/BSE Market Reality

| Aspect | Indian Reality |
|--------|---------------|
| **Instruments** | Equities (EQ), Futures (FUT), Options (OPT), Indices (NIFTY, BANKNIFTY, FINNIFTY, MIDCAPNIFTY) |
| **Expiry** | Weekly on Thursdays, monthly on last Thursday. Expiry day volatility and rollover dynamics are central to options workflow |
| **Sessions** | Pre-open 9:00-9:15 IST, Regular 9:15-15:30 IST, Post-close 15:30-16:00 |
| **Settlement** | T+1 equities, T+1 F&O (daily MTM) |
| **Order types** | LIMIT, MARKET, SL, SL-M, AMO, CO (Cover), BO (Bracket), IOC |
| **Dhan-specific** | Super Orders (multi-leg coordinated), Forever Orders, Conditional Orders — NOT in OpenAlgo |

### Where Indian-Market Specialization is First-Class

1. **Instrument master** — NSE/BSE scrip codes, series, expiry calendar with holiday awareness
2. **Options chain** — Weekly/monthly expiry, strike ladder, Greeks
3. **Market status** — Session state machine (pre-open, live, post-close, holiday)
4. **Calendar** — Trading holidays, expiry schedule, result season
5. **Margin models** — SPAN, VAR, ELM based on Indian clearing corp rules
6. **PCR/OI** — Time-of-day normalized, expiry-aware

### Where Multi-Asset Should Be Generic

1. Event bus — instrument-agnostic message passing
2. Storage model — time-series data stores for any instrument
3. Plugin system — new asset classes added via plugins
4. Signal engine — indicator computation on normalized data
5. Risk models — position sizing and exposure limits (market-agnostic parameters)

### Dhan-Specific Considerations

**Strengths we exploit:**
- No minimum balance requirements
- Competitive brokerage (₹0 on delivery, low on intraday/F&O)
- Good API documentation and SDK support
- WebSocket support for live data
- Support for all major order types including AMO
- Position conversion between intraday and delivery
- Super Orders, Forever Orders, Conditional Orders (Dhan-unique)

**Constraints we must handle:**
- Dual credentials: Trading credentials ≠ Data API credentials (error 806 if mixed)
- Token refresh requirements (access tokens expire ~3AM IST, DhanHQ-py has no auto-refresh)
- Rate limits on API calls (per endpoint, per second)
- Historical data availability (limited duration for intraday)
- Positions response does NOT include LTP — separate `multiquote` call required
- WebSocket: DhanFeed for live data — binary protocol, separate from REST

---

## SECTION 5 — SYSTEM BOUNDARIES

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

## SECTION 6 — PROPOSED ARCHITECTURE

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

## SECTION 7 — UPDATE-RESILIENT DESIGN

> **CORRECTED from earlier session**: Not composition with OpenAlgo. Absorb patterns, track upstream, selectively incorporate.

### Anti-Corruption Layer (ACL) Pattern

| Boundary | ACL Pattern | How |
|----------|-------------|-----|
| DhanHQ-py | Dhan Trading Adapter + Dhan Data Adapter | Only code that imports dhanhq; core sees `OrderExecutor`/`MarketDataStream` protocols |
| Absorbed OpenAlgo code | `_absorbed/` directory with origin markers | Marked with source comments; reviewed when OpenAlgo publishes changes |
| Fincept | Zero (no code enters) | Patterns only |
| OpenBB | Zero (no code enters) | Patterns only |

### Absorb vs Composition vs Fork

| Strategy | When | Our Use |
|----------|------|---------|
| **Composition** (pip dep) | External library with stable API | DhanHQ-py |
| **Absorption** (copy + adapt) | External service with useful patterns | OpenAlgo broker adapter, order validation, Options Tools concepts |
| **Fork** | Never (unless upstream unmaintained 12+ months) | Not used |

### Upstream Sync Workflow (OpenAlgo)

1. Monitor OpenAlgo repo for changes (monthly review)
2. When changes detected, review the diff
3. Decision: absorb (copy + adapt), skip, or modify
4. If absorb: copy to `_absorbed/`, add origin marker, adapt to our interfaces
5. Run full test suite to validate
6. No auto-merge — human review always

### Upstream Sync Workflow (DhanHQ-py)

1. Version pin in pyproject.toml
2. Changelog-driven review before bumps
3. Integration tests validate adapter works with new version
4. Staged rollout: dev → staging → prod

### CI-Enforced Architecture Compliance

```bash
# core has zero external imports
! grep -r "import dhanhq\|import httpx\|import duckdb\|import openalgo" src/shettyxtreme/core/
# intelligence doesn't import integration
! grep -r "from.*integration\|import.*integration" src/shettyxtreme/intelligence/
# no file > 500 lines
! find src -name "*.py" -exec wc -l {} + | awk '$1 > 500'
# no openalgo dependency anywhere
! grep -r "import openalgo\|from openalgo" src/
```

---

## SECTION 8 — FEATURE MAP

| Feature | Phase | Classification |
|---------|-------|---------------|
| Watchlists with live prices | MVP (Phase 1) | Essential |
| Market internals (indices, A/D, P/C) | MVP | Essential |
| Option chain with Greeks | MVP | Essential |
| Gap scanner | MVP | Essential |
| Position viewer (read-only) | MVP | Essential |
| Connection status + health | MVP | Essential |
| Kill switch (file-based) | MVP | Essential |
| Regime classifier | Phase 2 | Essential |
| Signal engine (conviction, D/P/G, NEUTRAL) | Phase 2 | Essential |
| Options intelligence (IV rank, PCR, strike EV) | Phase 2 | Essential |
| Risk engine (entries-only loss limit) | Phase 2 | Essential |
| Cost model (slippage/spread/brokerage) | Phase 2 | Essential |
| Web terminal UI (taste-skill + ui-ux-pro-max) | Phase 2 | Essential |
| Signal + trade journal | Phase 2 | Essential |
| Scanner (opportunity clusters) | Phase 2 | Essential |
| Shadow models | Phase 2 | Essential |
| Execution engine (semi-auto) | Phase 3 | Essential |
| Position management (TP3 fixed) | Phase 3 | Essential |
| Learning loop (voter quality consumed) | Phase 3 | Essential |
| Walkforward (honest evaluation) | Phase 3 | Essential |
| Market anticipation (probabilistic) | Phase 3 | Valuable |
| Multi-leg strategy constructor | Phase 3 | Seductive distraction (defer until single-leg proven) |
| Backtest engine | Phase 3 | Valuable |
| Knowledge ingestion | Phase 4 | Future |
| Auto-execution | Phase 4 | Future (high risk) |
| Multi-broker | Phase 4 | Future |
| SaaS/multi-user | Phase 4+ | Optional |
| ML/RL models | Phase 5+ (never until data + pipeline proven) | Seductive distraction |
| Pattern recognition | Optional | Needs more evidence |
| Community plugin marketplace | Optional | Needs more evidence |
| Telegram as primary interface | Never | Deprioritized |

---

## SECTION 9 — SHETTYBOT EVOLUTION

### What Retains

| ShettyBot V1 Concept | New Home | Status |
|---------------------|----------|--------|
| Regime detection methodology | `intelligence/regime/` | Reimplemented (no Markov on 1m noise) |
| Conviction scoring concept | `intelligence/signals/` | Reimplemented (D/P/G, participation-normalized) |
| Options-flow voter concept | `intelligence/voters/options_flow.py` | Reimplemented (time-of-day normalized OI) |
| Shadow model concept | `intelligence/signals/` | Reimplemented (shadow voters logged, don't gate) |
| Learning loop concept | `learning/` | Reimplemented (voter quality CONSUMED, not just logged) |
| Cockpit thinking | `terminal/` | Reimplemented (web-based, not Textual) |
| Risk awareness | `intelligence/risk/` | Reimplemented (entries-only loss limit) |

### What Gets Refactored

- Monolithic `live_dispatcher.py` (2,702 lines) → split into: Event Bus + Signal Engine + Execution Engine + Position Manager
- Monolithic `dashboard.py` (3,381 lines) → replaced by: FastAPI backend + web frontend
- Hardcoded strategies → YAML-configured voter plugins with registry

### What Gets Deprecated

- V1 direct OpenAlgo integration → superseded by first-party Dhan adapters
- V1 database schemas → replaced by new storage model (DuckDB + SQLite)
- V1 Telegram bot → optional plugin, not primary interface
- V1 Textual/Rich TUI → replaced by web-based terminal
- Markov voter (momentum follower, misleads as regime predictor) → removed or renamed `MomentumVoter`
- ML voter (AUC 0.518 = random) → removed entirely
- HMM voter (poorly calibrated) → removed

### What Gets Preserved as Concepts

- Regime classification methodology (trend/range/volatile detection)
- Signal scoring algorithms (direction score, participation, disagreement)
- Risk calculation approaches (position sizing, loss limits)
- Strategy-to-regime mapping
- Cockpit information architecture

These are extracted as specs, then reimplemented cleanly with 10 critical bugs fixed.

### 10 Critical Bugs Fixed in ShettyXtreme

| # | Bug | Fix |
|---|-----|-----|
| 1 | Strike selection = risk-neutral GBM noise | Signal-drift EV with actual exit policy |
| 2 | Loss limit freezes all trading | Loss limit blocks ENTRIES ONLY |
| 3 | TP3 unreachable | check_targets before update_tsl |
| 4 | No NEUTRAL signal (bearish tie-break) | Explicit NEUTRAL state |
| 5 | OI time-of-day clock bias | Normalize OI by time-of-day percentile |
| 6 | 3 inconsistent stop-loss definitions | One canonical (premium-relative, vol-aware) |
| 7 | Dead voters dilute confidence | Conviction (participation-normalized) — dead voters removed |
| 8 | Weights hardcoded in add_vote() | Weights in config YAML |
| 9 | No cost model | Slippage/spread/brokerage in ALL EV |
| 10 | No voter correlation awareness | Block caps per voter correlation group |

---

## SECTION 10 — OPENALGO UTILIZATION (ABSORB, DON'T DEPEND)

> **COMPLETELY REWRITTEN from earlier session.** Old plan: "compose with OpenAlgo as external service." New plan: "absorb patterns as first-party code, NO runtime dependency."

### What to Absorb from OpenAlgo

| OpenAlgo Component | Absorb Into | How |
|-------------------|-------------|-----|
| Broker adapter pattern (plugin.json discovery, standardized module structure) | `integration/` | Copy pattern, implement for Dhan as first-party |
| Dhan adapter (auth_api, order_api, data mapping, streaming) | `integration/dhan/` | Copy code, adapt to our interfaces, mark origin |
| Order validation (exchanges, actions, price types, product types) | `integration/` | Copy constants and validation logic |
| WebSocket architecture concept (broker WS → internal bus → consumer) | `integration/dhan/` | Implement as first-party asyncio pattern, not ZMQ subprocess |
| Options Tools (Option Chain, IV Smile, Max Pain, GEX, Vol Surface) | `intelligence/options/` | Study and reimplement in our options intelligence |

### What to Delegate to Absorbed Code

- Order validation for NSE/BSE exchanges, actions, price types (already done well in OpenAlgo)
- Dhan order mapping (DhanHQ order format → standard order model)
- Broker adapter interface pattern (proven in OpenAlgo's multi-broker design)

### What to NEVER Build from Scratch

- Order validation constants for Indian exchanges (NSE/BSE) — already exists in OpenAlgo
- Broker adapter interface pattern — proven in OpenAlgo
- Dhan order mapping (DhanHQ order format → standard order model) — adapt from OpenAlgo's Dhan adapter

### What Should Remain Independent from OpenAlgo

- **All core domain models** — our own frozen dataclasses
- **All intelligence** — signal engine, regime, options intelligence
- **All execution logic** — order lifecycle, position management
- **All learning** — outcome tracking, walkforward, calibration
- **All UI** — web-based terminal
- **All storage** — our own DuckDB + SQLite schema
- **All config** — our own YAML + env system

### How to Structure the Code So OpenAlgo Is Used Heavily Without Becoming a Tangle

1. Absorbed code lives in `integration/_absorbed/` with clear origin markers
2. Core domain and intelligence have ZERO imports from absorbed code
3. Absorbed code is adapted to implement our `core/interfaces/` protocols
4. When OpenAlgo publishes changes, we review the diff and decide: absorb, skip, or adapt
5. No `import openalgo` anywhere in our codebase — ever
6. DhanHQ-py remains a pip dependency (library, acceptable) — it's NOT an external service

---
## SECTION 11 — DHAN INTEGRATION STRATEGY

### Dhan API Split: Trading vs Data

| Aspect | Trading APIs | Data APIs |
|--------|-------------|-----------|
| **Purpose** | Live trading and account operations | Market data for analysis and research |
| **Endpoints** | Orders, positions, holdings, tradebook, funds, EDIS | Live market feed (WS), historical OHLC (REST), OI data |
| **Auth** | OAuth consent flow → access token | SK_M_`{clientId}` API key, expiry-based token (~3:00 AM IST) |
| **Rate limits** | Trading-specific limits | Data-specific limits |
| **Failover** | Fail-closed (can't trade → block execution, surface warning) | Fail-open (data fails → show stale data with staleness indicator) |
| **Caching** | Never cache (always fresh) | Aggressively cache (bars, option chain snapshots) with TTL + freshness checks |
| **WebSocket** | Order update WS (status changes, fills) | Market feed WS (ticks, quotes, depth) — binary protocol with codes 2/4/5/8/41/51 |
| **Error handling** | Never auto-retry order placement (risk duplicates). Log, surface, human decides. | Retry with backoff for data subscriptions. Reconnect WS on disconnect. |

### Dhan Trading Adapter Design

- Order placement (standard: Market/Limit/SL/SL-M, Dhan-specific: Super Orders, Forever Orders, Conditional Orders)
- Position conversion (MIS → NRML)
- EDIS flow (equity delivery, isolated)
- Auth: OAuth consent flow with auto-refresh (DhanHQ-py has no auto-refresh — we build it)
- Funds/margin: Direct from Dhan for precision

### Dhan Data Adapter Design

- Live market feed: Dhan Data API WebSocket (binary, codes 2/4/5/8/41/51)
- **Separate subscription/credentials** (error 806 if using Trading creds)
- Historical OHLC: REST API, cached in DuckDB
- OI/PCR: Direct from Dhan Data API (more granular), normalized by time-of-day percentile
- Fail-open with staleness indicator: if data fails, show staleness, don't block trading unless beyond freshness threshold
- Health check watchdog for silent-stall detection

### How to Support More Brokers Later Without Degrading Dhan-First Experience

- Broker adapters implement `OrderExecutor`, `MarketDataStream`, `AccountInfo`, `HistoricalDataProvider` protocols
- Dhan adapter is the reference implementation — most polished, most tested
- New broker = new adapter implementation, zero changes to core/intelligence
- Config selects active broker; intelligence and UI don't know which broker is active
- Broker-specific capabilities (Super Orders, position conversion) exposed as optional interface methods; UI enables/disables based on capability discovery

---

## SECTION 12 — OPENBB LEARNINGS

### Research-Platform Lessons

1. **Data integration modularity**: Each data provider is a self-contained module with a standard interface (Fetcher pattern). New data sources are added without touching core.
2. **Standard Model + Fetcher**: Data providers implement a standard interface; the platform knows how to discover, call, and normalize their output.
3. **Tool discovery for AI agents**: OpenBB's MCP server lets agents explore categories, activate tools selectively. ShettyXtreme should expose its own capabilities for AI-assisted workflows.

### Data-Platform Lessons

1. **Platform = data pipeline + computation pipeline + presentation**: OpenBB separates these cleanly. ShettyXtreme should too.
2. **Single source definitions**: OpenBB defines FastAPI router = Python SDK = MCP tools from one definition. ShettyXtreme should consider defining API surfaces once and generating multiple consumers.

### AI-Agent/Workspace Lessons

1. **Research workspace**: OpenBB supports structured research commands, exploratory analysis, and historical investigation. ShettyXtreme needs a research workspace, not just live monitoring.
2. **MCP compatibility**: OpenBB exposes its capabilities via MCP. ShettyXtreme should consider MCP compatibility for future AI-assisted research workflows.

### What Should Inspire Us

- Plugin/extension system for data providers
- Research workspace concept (exploratory, not just monitoring)
- Tool discovery pattern for AI agents
- Standard interface for data normalization

### What Should Remain Outside Our Scope

- OpenBB's actual data provider implementations (US/global, different market)
- OpenBB's web framework choices
- OpenBB's enterprise workspace dependency
- Crypto/forex modules

### What Would Be Dangerous to Imitate Blindly

- Over-abstraction for a single-broker product (OpenBB supports many providers; we start with Dhan only)
- FastAPI coupling at the core (our backend is internal, not a public platform)
- No streaming data model (OpenBB is request/response; we need streaming)
- Western market focus patterns that don't translate to India

---

## SECTION 13 — SYSTEMATIC TRADING BREADTH CHECK

Using the Awesome Systematic Trading catalog as a blind-spot checklist:

### Categories We Cover

| Category | Our Coverage |
|----------|-------------|
| Backtesting | ✅ Phase 3 (strategy backtest viewer) |
| Live trading | ✅ Phase 2+ (execution cockpit) |
| Risk management | ✅ Phase 1+ (risk engine) |
| Strategy development | ✅ Phase 2+ (voter plugin system) |
| Technical analysis | ✅ Phase 2 (feature engine) |
| Logging/journaling | ✅ Phase 2 (signal + trade journal) |
| Visualization | ✅ Phase 1+ (terminal UI) |
| Market data | ✅ Phase 1 (Dhan Data API) |

### Categories We Might Be Missing

| Category | Assessment | Decision |
|----------|------------|----------|
| **Portfolio optimization** | We focus on single-instrument directional options, not portfolio-level optimization | Defer to Phase 4+. Not relevant for MVP. |
| **Cost modeling** | ShettyBot V1 had NO slippage/spread/brokerage anywhere | MUST include from Phase 1. Slippage model in feature engine, cost-adjusted EV in strike selection. |
| **Streaming TA** | ShettyBot V1 recomputed features from scratch each cycle | MUST implement O(1) per-tick streaming indicators from Phase 1. |
| **Execution profiling** | Latency measurement from tick to signal to order | Include from Phase 1 as part of observability. |
| **Pre-trade risk gate** | ShettyBot V1 had risk checks but they were bypassed on loss-limit breach | Include composable risk filter chain from Phase 1. |
| **DAG/incremental computation** | OpenBB uses this; could improve feature engine performance | Acknowledge but postpone. Not needed for MVP scale. |
| **Message queues** | OpenAlgo uses ZMQ; our event bus is asyncio pub/sub | asyncio pub/sub is sufficient for single-process. Postpone external MQ. |
| **Prediction markets** | Irrelevant for India-first practical product | Skip. |
| **Crypto/forex tools** | Irrelevant for India-first | Skip. |
| **QuantLib** | Heavy quantitative finance library, institutional-grade | Skip. We need practical options math, not institutional fixed-income pricing. |
| **ML/RL for trading** | ShettyBot V1's ML had AUC 0.518 (barely random) | Postpone entirely. No ML until we have enough data and a proven pipeline. |

---

## SECTION 14 — DATA + DECISION INTELLIGENCE

### How the Platform Identifies Gaps

A "gap" is a divergence between what price is doing and what market internals suggest should be happening:

| Gap Type | Detection | Operator Output |
|----------|-----------|----------------|
| Breadth divergence | Price rising but advance/decline ratio falling | "Price up but breadth weakening — transition risk" |
| PCR divergence | PCR trending bullish but price flat/down | "Contrarian PCR signal: crowding detected" |
| IV compression | IV dropping while OI building | "Volatility compression + OI build = breakout setup" |
| Regime transition | ADX falling, ATR percentile rising | "Trending regime weakening, volatility expansion likely" |

### How the Platform Identifies Opportunity Clusters

Not individual signals, but CONVERGENCE of multiple signals:

```
Cluster Score = f(
    voter_agreement,          # D (direction score)
    participation_health,     # P (participation)
    disagreement_level,       # G (should be LOW)
    regime_confidence,         # from regime engine
    options_context,           # IV rank, OI dynamics, PCR context
    breadth_confirmation,     # ADR, breadth divergence
```

High cluster score + low disagreement → high-conviction directional setup.

### How the Platform Handles Options vs Directional

| Regime | IV Level | OI Dynamics | Recommended Structure |
|--------|----------|------------|----------------------|
| Trending UP, IV low | IV percentile < 30 | OI building on calls | Long CE (directional) |
| Trending UP, IV high | IV percentile > 70 | PCR > 1.3 | Debit spread (defined risk) |
| Range-bound, IV high | IV percentile > 60 | OI stable | Wait (premium selling deferred until margin infra) |
| Range-bound, IV low | IV percentile < 30 | OI compressed | Long straddle (vol expansion bet) |
| Trending DOWN, IV high | IV expanding | PCR < 0.9, put OI building | Long PE (directional) |
| Volatile expansion | ATR percentile > 80 | IV expanding rapidly | Reduce size or stay flat |

### How the Platform Handles Uncertainty

- **No predictions.** The platform outputs conditions, not predictions.
- **Probabilistic framing**: "Conditions X, Y, Z present, which historically precede outcome W with estimated probability P"
- **Uncertainty visible**: conviction score, participation, disagreement — the operator sees WHY a signal fires and how confident the system is
- **Cost-aware**: every signal includes estimated slippage/spread/brokerage cost. Marginal signals (expected profit < 2× cost) are flagged as "marginal — high cost risk"
- **Shadow validation**: new strategies/heuristics run in shadow first. Never activate without 20+ session validation and human approval.

---

## SECTION 15 — KNOWLEDGE, REPORTS, AND REVERSE ENGINEERING

### Knowledge Ingestion Architecture

```
Upload Document (PDF/MD/TXT)
    ↓
[Knowledge Store] — document stored with metadata (title, author, date, source, tags)
    ↓
[Tagger] — auto-extract: topics, instruments, strategies, market conditions
    ↓
[Heuristic Extractor] — extract testable claims:
    "When PCR > 1.3 on expiry day and NIFTY gap-down → sell CE"
    ↓
[Backtest] — test the heuristic against historical data
    ↓
[Walkforward] — validate stability over time
    ↓
[Human Review] — is it economically sensible? Is it overfit?
    ↓
[Activate as Shadow Voter] — runs alongside live, doesn't gate
    ↓
[Shadow Validation] — 20+ sessions → compare shadow vs live outcomes
    ↓
[Human Approval] — promote to active voter
```

### What Can Be Structured

- Strategy definitions ("buy when X, sell when Y") → YAML strategy files
- Parameter sets ("IV threshold = 70, PCR threshold = 1.3") → config values
- Risk rules ("max 2% daily loss") → risk engine config
- Expiry rules ("switch to next week when DTE ≤ 2") → expiry selection config

### What Can Be Tagged

- Documents by topic (options, regime, intraday, swing, risk management)
- Documents by instrument (NIFTY, BANKNIFTY, FINNIFTY)
- Documents by strategy type (directional, spread, premium selling)
- Documents by market condition (bull, bear, range, volatile)

### What Can Become Heuristics

- "When PCR is above 1.3 on expiry day, market tends to reverse" → contrarian PCR voter threshold
- "ORB breakout above opening range with volume confirmation → directional long" → ORB voter parameters
- "When NIFTY opens with a gap > 0.5% and breadth < 40% → gap fade" → gap scanner rule

### What Should Remain Human-Reviewed

- All knowledge-derived heuristics MUST pass human review before activation
- Economic sensibility check: does the heuristic make economic sense?
- Overfit check: does it work on multiple time periods or just one?
- Context check: is it relevant to current market structure?

### How to Avoid Polluting Live Trading Logic

- Knowledge layer is PHYSICALLY SEPARATED from live trading logic
- Knowledge can READ from live data (to verify predictions) but CANNOT WRITE to live trading rules
- Heuristic activation is a gated process with explicit human approval
- Shadow mode for all new heuristics — never auto-activate
- Even after activation, heuristics can be disabled with a single config toggle

---

## SECTION 16 — UX / TERMINAL VISION

### Interface Stance: Web-Based Professional Workstation

NOT a CLI/TUI. A web-based workstation with professional terminal feel. The "terminal" in the product name means "professional trading workstation" (like Bloomberg Terminal), not "CLI application."

Informed by:
- https://github.com/leonxlnx/taste-skill (design taste/quality skill)
- https://github.com/nextlevelbuilder/ui-ux-pro-max-skill (UI/UX excellence skill)

### Cockpit Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│ STATUS BAR: [Session: OPEN] [Mode: OBSERVER] [Dhan: ●] [Data: ●] [Risk: OK] │
├──────────────┬─────────────────────────────┬───────────────────────────┤
│ WATCHLIST    │ INTELLIGENCE COCKPIT         │ EXECUTION COCKPIT         │
│              │                              │                           │
│ NIFTY 24500  │ Regime: TRENDING_UP (72%)    │ Positions: 1 active       │
│  +0.45%      │ Conviction: 0.68 [████░░]    │ NIFTY 24500 CE            │
│              │ Direction: UP  Disagree: 0.12│   Entry: 85  LTP: 112     │
│ BANKNIFTY    │                              │   MTM: +₹1,755           │
│  +0.62%      │ VOTERS:                      │                           │
│              │ ✓ Options Flow  ↑ 0.70       │ RISK:                     │
│ FINNIFTY     │ ✓ ORB           ↑ 0.65       │ Daily P&L: +₹1,755       │
│  +0.31%     │ ✓ Micro         ↑ 0.55       │ Margin: ₹45,200 / ₹2L    │
│              │ ✓ Breadth       ↑ 0.40       │ Loss Limit: ₹8,000 used  │
│ OPTIONS:     | ✗ HMM (disabled)              │                           │
│ NIFTY 24500CE│ ✗ ML (disabled)              │ [KILL SWITCH]             │
│  85 → 112   │                              │                           │
│              │ STRATEGY HINT:               │                           │
│              │ Long CE, 1 lot, 24500 strike │                           │
│              │ EV: +₹12 after cost          │                           │
│              │                              │                           │
├──────────────┴─────────────────────────────┴───────────────────────────┤
│ SCANNER + ALERTS + LOGS                                                 │
│ [GAP] NIFTY gap-up 0.6%, breadth weak (38%) → fade risk                 │
│ [ALERT] OI data 3min stale                                              │
│ [SIGNAL] 09:42 TRENDING_UP conviction=0.68 (Options+ORB+Micro)         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key UX Principles

1. **Keyboard-first**: All primary actions accessible via keyboard shortcuts
2. **Progressive disclosure**: Start with summary, drill down to detail
3. **Explainability surfaces**: Every signal shows WHY (voters, conviction, regime context)
4. **Not cluttered**: Max 3 main panels + status bar + bottom strip
5. **Session-aware**: UI adapts to session phase (pre-open, open, close)
6. **Mode-aware**: Observer mode hides execution panel; Live mode shows it
7. **Cost-visible**: EV shown as "after cost" not gross
8. **Honest uncertainty**: Conviction bar, disagreement indicator, participation level all visible

### Drill-Down Workflow

1. Scanner surfaces a candidate → click to open instrument
2. Instrument opens in Intelligence Cockpit → see regime, voters, conviction
3. If conviction passes threshold → Strategy Hint appears
4. Click Strategy Hint → see full explanation (voter breakdown, IV context, OI analysis)
5. If mode = Live → approve in Execution Cockpit (semi-auto)
6. Post-trade → outcome tracked in Journal

---

## SECTION 17 — MONETIZATION + BUSINESS LEVERAGE

### Primary: Direct Trading Utility (Phase 1-2)

The platform makes money by making YOUR trading better:
- Better signal identification (conviction, voter agreement)
- Better strike selection (signal-drift EV, not noise optimization)
- Better risk management (regime-aware sizing, loss limits that don't freeze position management)
- Better cost awareness (slippage-adjusted decisions)

### Secondary: Internal Prop-Style Usage (Phase 2-3)

Use the platform as your own trading desk:
- Daily signal generation with full logging
- Post-session calibration (per-voter quality tracking)
- Regime-aware position sizing
- Learning loop that improves over time

### Tertiary: SaaS Potential (Phase 4+, SOBER)

| Tier | Price | Features |
|------|-------|----------|
| Personal | ₹999/mo | Observer mode, watchlists, scanners, signal display |
| Pro | ₹2,999/mo | Live execution, risk management, journaling, analytics |
| Desk | ₹9,999/mo | Multi-user, advanced intelligence, API access |

**Reality check**: Revenue depends on user acquisition, which is NOT the focus of Phase 0-3. The first priority is a working platform that makes money through direct trading utility. SaaS is Phase 4+.

### What to NOT Build Yet

- Billing system
- User management infrastructure
- Multi-tenancy
- Marketing website
- API monetization

---

## SECTION 18 — DELIVERY ROADMAP

### Phase 0: Architecture Reset (THIS SESSION)

**Objective**: Reset the architecture from OpenAlgo-dependent to standalone. Write the complete blueprint. Clean the repo.

**Deliverables**:
- Complete 22-section architecture blueprint (this document)
- Implementation plan with test gates per wave
- Repo cleaned of temp scripts
- Kanban updated with new direction
- Obsidian project docs created
- UI/UX skills (taste-skill, ui-ux-pro-max-skill) studied and installed

**Risks**: Existing Phase 1+2 code depends on OpenAlgo — may need partial rewrite of integration layer.

**Dependencies**: None.

**Postpone**: All coding until architecture reset is complete and approved.

**Validation**: Blueprint reviewed, kanban reflects new direction, repo is clean.

### Phase 1: Standalone Foundations

**Objective**: Build the standalone execution infrastructure — broker adapters, storage, config, event bus, session state. NO OpenAlgo dependency.

**Deliverables**:
- Core domain models (Instrument, Order, Position, Signal, Event types)
- Event bus (asyncio pub/sub)
- Config system (YAML + env + validation)
- Storage (DuckDB time-series, SQLite KV)
- Dhan Trading Adapter (order placement, positions, holdings, EDIS, margin, auth with auto-refresh)
- Dhan Data Adapter (live market feed WS, historical OHLC, OI/PCR, separate credentials)
- Order validation (exchanges, actions, price types — absorbed from OpenAlgo's constants/logic)
- Symbol/instrument master (first-party, seeded from Dhan API)
- Session state (market calendar, session lifecycle, operator state)
- Health checks (Dhan Trading, Dhan Data, DuckDB, event bus)

**Test Gates to Pass**:
1. `test_core_domain.py` — all domain models instantiate, are frozen/immutable
2. `test_event_bus.py` — publish/subscribe/unsubscribe, event ordering, no memory leaks
3. `test_config.py` — YAML loading, env override, validation, secrets from env only
4. `test_storage.py` — DuckDB TS append/query, SQLite KV get/set, migration runs
5. `test_dhan_trading_adapter.py` — order placement (mock), position query (mock), auth refresh (mock), margin query (mock)
6. `test_dhan_data_adapter.py` — WS subscribe (mock binary protocol), historical OHLC (mock), error 806 handling, staleness detection
7. `test_order_validation.py` — all valid/invalid order combinations tested
8. `test_instrument_master.py` — symbol resolution, expiry calculation with holiday awareness
9. `test_session_state.py` — session lifecycle, market calendar, IST handling
10. `test_health_checks.py` — all health checks return correct status
11. **Architecture compliance**: `grep -r "import openalgo\|from openalgo" src/core/ src/intelligence/ src/options/` → ZERO matches
12. **No god modules**: `find src -name "*.py" -exec wc -l {} + | sort -rn | head -5` → no file > 500 lines

**Risks**: Dhan binary WebSocket protocol complexity; auth auto-refresh timing.

**Dependencies**: DhanHQ-py pip dependency, DuckDB.

**Postpone**: Intelligence modules, terminal UI, execution cockpit logic.

**Validation**: All 12 test gates pass. Single-process startup connects to Dhan and can place a paper order.

### Phase 2: Usable MVP — Observer Terminal

**Objective**: A working observer terminal that connects to Dhan, shows live prices, displays option chains, generates basic signals, and has risk guardrails. No live execution.

**Deliverables**:
- Feature engine (streaming, O(1) per tick: bars, MA, ATR, ADX, VWAP, PCR, OI, IV)
- Regime classifier (trending/range/volatile, confidence, transition detection)
- Signal engine (voter plugin system, conviction computation, D/P/G, NEUTRAL state)
- Options intelligence (IV rank/percentile, PCR contrarian, expiry selection, strike selection with signal-drift EV)
- Risk engine (position sizing, daily loss limit blocking ENTRIES ONLY, margin guardrails, composable filter chain)
- Scanner (gap detector, opportunity cluster identification)
- Web terminal UI (watchlists, option chain, market internals, signal cockpit, risk meters, session controls)
- Journaling (signal log, trade log, outcome tracking)
- Observability (structured logging, latency metrics, health dashboard)

**Test Gates to Pass**:
1. All Phase 1 test gates still pass
2. `test_feature_engine.py` — streaming indicators correct vs batch computation, freshness guards
3. `test_regime_classifier.py` — regime detection on historical data, transition detection
4. `test_signal_engine.py` — conviction computation, D/P/G, NEUTRAL state, voter plugin discovery
5. `test_options_intelligence.py` — IV rank, PCR contrarian, expiry selection (with next-week chain fix), strike selection with signal-drift EV (NOT risk-neutral)
6. `test_risk_engine.py` — loss limit blocks ENTRIES ONLY (position management runs), margin check, filter chain composability
7. `test_scanner.py` — gap detection, cluster identification
8. `test_journal.py` — signal logging, outcome tracking, immutable signal_decisions
9. `test_terminal_api.py` — all REST/WS endpoints respond correctly
10. `test_e2e_observer.py` — full cycle: Dhan data → features → signal → journal → UI display (mock data)
11. **Cost model test**: `test_cost_model.py` — slippage/spread/brokerage included in EV computation
12. **Shadow mode test**: `test_shadow_models.py` — shadow voters computed alongside, logged, don't gate

**Risks**: Streaming feature computation correctness; regime classifier accuracy; UI complexity.

**Dependencies**: Phase 1 complete.

**Postpone**: Execution (no live orders), multi-leg strategies, backtesting, knowledge ingestion, market anticipation.

**Validation**: Full session in OBSERVER mode — connects to Dhan, generates signals, logs everything, displays in terminal UI.

### Phase 3: Advanced Intelligence + Execution

**Objective**: Add execution capability (semi-auto), learning loop, advanced options intelligence, and market anticipation.

**Deliverables**:
- Execution engine (order lifecycle, semi-auto approval, position management with FIXED TP3 ordering, TSL, EOD close)
- Learning loop (per-voter quality tracking that IS consumed, MFE/MAE, walkforward with HONEST evaluation harness)
- Advanced options (IV skew/term structure, multi-leg strategy constructor, margin calculator)
- Market anticipation (regime transition detection, divergence accumulation, probabilistic outlook)
- Analytics (signal quality, voter contribution, win/loss by regime, cost analysis)
- Multi-leg order placement (requires Dhan Super Orders)

**Test Gates to Pass**:
1. All Phase 2 test gates still pass
2. `test_execution_engine.py` — order lifecycle, semi-auto approval, TP3 REACHABLE (check_targets before update_tsl)
3. `test_learning_loop.py` — voter quality consumed (weights adjusted based on hit rates), MFE/MAE percentiles, walkforward honest (option premium + exit policy, not underlying % moves)
4. `test_multi_leg.py` — spread construction, margin check, coordinated leg execution
5. `test_anticipation.py` — regime transition detection, divergence tracking, probabilistic output format
6. `test_calibration.py` — confidence→win-rate curve from actual data, isotonic/Platt mapping
7. **Stop-loss unification test**: `test_stop_loss.py` — one definition everywhere (premium-relative, vol-aware)
8. **Dead voter removal test**: ML voter removed, HMM removed, Markov retuned or removed — test confirms
9. **Correlation awareness test**: `test_voter_correlation.py` — pairwise agreement measured, block caps where needed

**Risks**: Multi-leg coordination; learning loop consuming quality metrics correctly; calibration data sufficiency.

**Dependencies**: Phase 2 complete, sufficient DRY_RUN data (20+ sessions).

**Postpone**: Knowledge ingestion, SaaS/multi-user, multi-broker.

**Validation**: Full session in LIVE mode (semi-auto) — signals → human approval → execution → position management → outcome tracking → learning loop feeds back.

### Phase 4: Platform Maturity

**Objective**: Knowledge ingestion, market automation, multi-broker foundation, SaaS potential.

**Deliverables**:
- Knowledge ingestion (document store, tagger, heuristic extractor, knowledge linker)
- Market automation (auto-execution for high-conviction signals, scheduled scanners/reports)
- Multi-broker foundation (second broker adapter, capability discovery)
- SaaS foundation (API versioning, multi-user auth, billing stub)
- Advanced analytics (risk-adjusted performance, portfolio heatmap, cost analysis)

**Test Gates to Pass**:
1. All Phase 3 test gates still pass
2. `test_knowledge_ingestion.py` — document upload, tagging, heuristic extraction, shadow validation flow, human approval gate
3. `test_auto_execution.py` — high-conviction auto-execute with risk guardrails, veto on disagreement
4. `test_multi_broker.py` — second broker adapter, capability discovery, config-based broker selection
5. `test_saas.py` — API versioning, auth, rate limiting

**Risks**: Knowledge layer contamination (weakly validated ideas reaching live trading); auto-execution safety; scope expansion.

**Dependencies**: Phase 3 complete, sufficient calibration data.

**Postpone**: Anything not in this list.

**Validation**: Knowledge ingestion → heuristic extraction → shadow validation → human approval → activation flow works end-to-end.

---

## SECTION 19 — REPO / CODEBASE STRATEGY

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

## SECTION 20 — RISKS AND FAILURE MODES

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Overbuilding** | HIGH | Phase gates: no Phase N+1 work until Phase N test gates pass. Feature map marks "seductive distractions" clearly. |
| **Duplicate infra** | HIGH | Absorb, don't reinvent. DhanHQ-py is pip dependency. OpenAlgo patterns are absorbed as first-party code. No duplicate broker adapters. |
| **Tight coupling to upstream** | MEDIUM | Anti-corruption layers at all boundaries. Absorbed code marked with origin. Upstream changes reviewed, not auto-merged. |
| **Poor boundary design** | HIGH | CI-enforced import rules. Zero external imports in core. Intelligence can't import integration. Knowledge can't import intelligence. |
| **Latency assumptions** | MEDIUM | Measure from Phase 1 (latency metrics in observability). Don't assume sub-ms — measure and design around reality. |
| **Broker brittleness** | HIGH | Auto-reconnect for WS. Token auto-refresh. Fail-closed for Trading, fail-open for Data. Separate sessions. |
| **UI complexity** | MEDIUM | Web-based (not TUI). Progressive disclosure. Max 3 main panels. Keyboard-first. Start simple, add complexity based on real operator friction. |
| **Signal overfitting** | HIGH | Shadow mode for ALL new heuristics. 20+ session validation. Walkforward with honest evaluation. Cost model in all EV computations. |
| **Operational fragility** | HIGH | Session state persisted to DB (survives restart). OI/PCR baselines persisted (fixes ShettyBot V1's in-memory baselines). Kill switch file-based (independent of platform). |
| **Maintainability collapse** | HIGH | No god modules (500-line CI check). Single schema owner. Single config source. Plugin discovery (not hardcoded imports). |
| **Knowledge-layer contamination** | HIGH | Physical separation. Knowledge can't import intelligence. Human approval gate for all heuristic activations. Shadow validation before activation. |
| **False-confidence forecasting** | HIGH | No predictions — probabilistic framing. Uncertainty visible (conviction, disagreement, participation). Cost-aware EV. "Conditions X precede Y with probability P" not "market will go up." |

---

## SECTION 21 — FINAL RECOMMENDATION

### 1. Recommended Architecture Stance

**Modular monolith, standalone software, interface-driven boundaries, event-driven data flow, DhanHQ-py as only external runtime dependency (pip), OpenAlgo patterns absorbed as first-party code.**

- Core: stable, frozen contracts, zero external imports
- Intelligence: rapid evolution, voter plugin system, conviction as primary metric
- Integration: Dhan-first, swappable adapters, anti-corruption layers
- UI: web-based professional workstation (NOT TUI), using taste-skill and ui-ux-pro-max-skill
- Knowledge: physically separated, human-gated activation
- Storage: DuckDB (time-series) + SQLite (KV)
- Events: asyncio pub/sub (single process)

### 2. Recommended Product Stance

**India-first options trading intelligence and execution workstation for prosumer traders using Dhan.**

- Observer mode first (signals without execution)
- Semi-auto execution second (intelligence proposes, human approves)
- Full execution third (conviction-gated auto-execute with risk guardrails)
- Learning loop throughout (every signal tracked, every outcome fed back)
- Market anticipation as probabilistic awareness, NOT prediction
- Knowledge ingestion as Phase 3+ with human-gated activation

### 3. Whether the Current Direction Should Be Evolved, Heavily Reworked, or Replaced

**HEAVILY REWORKED.** The prior ShettyXtreme direction had the right product vision but wrong architecture choices:

- **Wrong**: Runtime dependency on OpenAlgo as external service → **Correct**: Standalone software, absorb patterns
- **Wrong**: Textual TUI as primary interface → **Correct**: Web-based professional workstation
- **Wrong**: Preserving ShettyBot V1's intelligence math as-is → **Correct**: Reimplement concepts with critical bugs fixed
- **Wrong**: Not addressing Dhan Trading vs Data API split → **Correct**: Separate adapters, separate auth
- **Wrong**: No knowledge ingestion layer → **Correct**: Phase 3+ knowledge system with human-gated activation
- **Wrong**: No cost model → **Correct**: Slippage/spread/brokerage in all EV computations from Phase 1

The existing Phase 1+2 code in the repo needs significant refactoring:
- Integration layer: Replace OpenAlgo-dependent adapters with first-party Dhan adapters
- Terminal layer: Replace Textual TUI with web-based UI
- Intelligence layer: Add conviction, fix strike selection, add NEUTRAL state, add cost model
- Storage: Ensure single schema owner

### 4. Exact Research Areas That Must Be Closed Before Any Further Building

1. **Dhan Data API subscription flow**: How to get separate Data API credentials. Error 806 resolution. Token lifecycle for Data API vs Trading API.
2. **Dhan WebSocket binary protocol**: Full understanding of feed codes (2/4/5/8/41/51), subscription request codes (15/17/21/23), reconnection behavior.
3. **Actual intraday option spreads and slippage for NIFTY/BANKNIFTY**: This is the single most important unknown for realistic cost modeling.
4. **taste-skill and ui-ux-pro-max-skill**: How to install and use these skills for the terminal UI (sub-agent is studying these now).
5. **Dhan holiday calendar**: Exchange-specific holiday list and its effect on expiry calculation.

### 5. What to Intentionally NOT Build Yet

- ML/RL models (until enough data and a proven pipeline)
- Multi-broker support (until Dhan is flawless)
- Knowledge ingestion/auto-activation (until manual process proven)
- SaaS/billing/multi-tenancy
- Telegram/email as primary interface
- Multi-leg strategy constructor (until single-leg intelligence is proven)
- Market anticipation as prediction (until regime detection is proven)
- Any feature marked "seductive distraction" in the feature map
- ShettyOS
- Forum/community features

### 6. How to Maximize Long-Term Upside Without Drowning in Complexity

1. **Composition over fork for EXTERNAL libraries** (DhanHQ-py = pip dep)
2. **Absorb over compose for EXTERNAL services** (OpenAlgo patterns → first-party code)
3. **Shadow over activate for NEW intelligence** (20+ sessions before any new voter gates)
4. **Observer over live for NEW operators** (watch signals work before risking capital)
5. **Probabilistic over predictive for MARKET ANTICIPATION** (conditions, not predictions)
6. **Human-gated over auto for KNOWLEDGE ACTIVATION** (prevent contamination)
7. **Modular monolith over microservices** (single operator, single process)
8. **Web terminal over CLI** (professional feel, future-remote-access-flexible)
9. **Cost-aware from day one** (no marginal strategies passing as profitable)
10. **Fix ShettyBot V1's bugs in the reimplementation** (conviction without dead voters, strike selection without noise optimization, TP3 that's reachable, loss limits that don't freeze position management, NEUTRAL signal state, time-of-day-normalized OI)

---

## IMPLEMENTATION PLAN — TEST GATES PER WAVE

### Wave 0: Architecture Reset + Repo Cleanup (Current Session)

**Deliverables**:
- This blueprint document written to repo
- Temp scripts cleaned from repo root
- Kanban updated with new direction
- Obsidian project docs created
- UI/UX skills studied and installed

**Test Gate**: Repository is clean (no temp scripts), blueprint is committed, kanban reflects new plan.

### Wave 1: Standalone Integration Layer (Replacing OpenAlgo Dependency)

**Deliverables**:
- Dhan Trading Adapter (first-party, using DhanHQ-py)
- Dhan Data Adapter (first-party, using DhanHQ-py, separate credentials)
- Order validation (absorbed from OpenAlgo constants)
- Symbol/instrument master (first-party)
- Remove all OpenAlgo-dependent code

**Test Gates**:
1. `pytest tests/integration/test_dhan_trading_adapter.py -v` — All Trading API calls work with mock responses
2. `pytest tests/integration/test_dhan_data_adapter.py -v` — All Data API calls work, error 806 handled, staleness detected
3. `pytest tests/core/test_order_validation.py -v` — All valid/invalid order combinations
4. `grep -r "openalgo\|OpenAlgo" src/` → ZERO matches (no OpenAlgo dependency anywhere)
5. `pytest tests/core/ tests/integration/ -v` — All existing core tests still pass

### Wave 2: Intelligence Layer Core

**Deliverables**:
- Feature engine (streaming, O(1) per tick)
- Regime classifier (fixed: no Markov on 1m noise, coarser bars)
- Signal engine (conviction, D/P/G, NEUTRAL state, voter plugin system)
- Options intelligence (IV rank, PCR contrarian, expiry selection, strike selection with signal-drift EV)
- Risk engine (loss limit blocks ENTRIES ONLY, composable filter chain)
- Cost model (slippage, spread, brokerage — in all EV computations)

**Test Gates**:
1. `pytest tests/intelligence/test_feature_engine.py -v` — Streaming indicators correct
2. `pytest tests/intelligence/test_signal_engine.py -v` — Conviction correct, NEUTRAL state works, plugin discovery works
3. `pytest tests/intelligence/test_regime_classifier.py -v` — Regime detection on historical data
4. `pytest tests/options/test_strike_selection.py -v` — Signal-drift EV (NOT risk-neutral), next-week chain used when expiry switches
5. `pytest tests/risk/test_loss_limit.py -v` — Loss limit blocks ENTRIES ONLY (position management runs)
6. `pytest tests/risk/test_cost_model.py -v` — Slippage/spread/brokerage in EV
7. `find src -name "*.py" -exec wc -l {} + | awk '$1 > 500'` → ZERO matches (no god modules)

### Wave 3: Terminal UI (Web-Based)

**Deliverables**:
- FastAPI backend (REST + WS)
- Web frontend (React/Svelte, using taste-skill + ui-ux-pro-max-skill)
- Panels: Watchlist, Intelligence Cockpit, Execution Cockpit, Scanner/Alerts/Logs
- Session controls, kill switch, mode toggle
- Health dashboard

**Test Gates**:
1. `pytest tests/terminal/test_api.py -v` — All REST/WS endpoints respond
2. `pytest tests/terminal/test_panels.py -v` — Panel data models correct
3. `pytest tests/terminal/test_e2e_observer.py -v` — Full cycle with mock data
4. Frontend loads in browser, all panels render, WS connection works

### Wave 4: Learning Loop + Analytics

**Deliverables**:
- Outcome tracking (immutable signal_decisions + execution_attempts + outcome_labels)
- Per-voter quality tracking (CONSUMED — feeds back to weight adjustments)
- MFE/MAE computation
- Walkforward with honest evaluation (option premium + exit policy, not underlying % moves)
- Analytics dashboards

**Test Gates**:
1. `pytest tests/learning/test_outcome_tracking.py -v`
2. `pytest tests/learning/test_voter_quality.py -v` — Quality metrics consumed, weights adjusted
3. `pytest tests/learning/test_walkforward.py -v` — Honest evaluation (option premium + exit policy)
4. `pytest tests/learning/test_mfe_mae.py -v`

### Wave 5: Execution + Position Management

**Deliverables**:
- Execution engine (order lifecycle, semi-auto approval)
- Position management (TP1/TP2/TP3 with FIXED ordering, TSL, EOD close)
- One canonical stop-loss definition (premium-relative, vol-aware)

**Test Gates**:
1. `pytest tests/execution/test_order_lifecycle.py -v`
2. `pytest tests/execution/test_position_management.py -v` — TP3 REACHABLE (check_targets before update_tsl)
3. `pytest tests/execution/test_stop_loss_unified.py -v` — One definition everywhere

### Wave 6: Shadow Models + Calibration

**Deliverables**:
- Shadow DPG tier router (de-inverted)
- Shadow signal-drift EV (activate if validated)
- Shadow time-bucketed OI (activate if validated)
- Shadow ORB decay (activate if validated)
- Confidence→win-rate calibration curve
- Voter correlation awareness

**Test Gates**:
1. `pytest tests/intelligence/test_shadow_models.py -v`
2. `pytest tests/intelligence/test_calibration.py -v`
3. `pytest tests/intelligence/test_voter_correlation.py -v`

### Cross-Wave Test Gates (Every Wave)

- All previous wave test gates still pass (no regressions)
- `grep -r "import openalgo\|from openalgo" src/` → ZERO matches
- `find src -name "*.py" -exec wc -l {} + | awk '$1 > 500'` → ZERO matches
- `grep -r "import dhanhq\|import httpx" src/shettyxtreme/core/` → ZERO matches (core has no external deps)
- `PYTHONPATH="" python -m pytest tests/ -v --tb=short` → ALL PASS
