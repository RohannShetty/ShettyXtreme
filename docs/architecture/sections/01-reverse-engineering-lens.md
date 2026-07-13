# Section 1: REVERSE-ENGINEERING LENS

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

