import sys
def ws(n, c):
    with open(f"docs/architecture/sections/{n}", "w") as f:
        f.write(c)
    print(f"{n} written")

ws("06-update-resilient-design.md", """# Section 6: Update-Resilient Design

## Strategy

Multi-layered defense isolates core from upstream changes.

## Anti-Corruption Layer (ACL) Pattern

Every external dep has an adapter that:
1. Defines interface the core expects (in core/interfaces/)
2. Implements by translating to/from the external system
3. Is the ONLY code importing from the external package
4. Has contract tests against the real upstream

### OpenAlgoAdapter
- Core interface: OrderExecutor, MarketDataStream, AccountInfo
- Import chain: core -> OpenAlgoAdapter -> openalgo (NOT core -> openalgo)

### DhanAdapter
- Core interface: BrokerAccount, MarginProvider
- Import chain: core -> DhanAdapter -> dhanhq (NOT core -> dhanhq)

## Fork vs Composition: COMPOSITION WINS

| Aspect | Fork | Composition |
|--------|------|-------------|
| Upstream updates | Manual merge pain | Version bump + test |
| Divergence | Inevitable | Zero by design |
| Security patches | Re-merge needed | Bump version |
| Maintenance | Full repo to maintain | Near zero |

Exception: fork only if upstream is unmaintained (12+ months no updates).

## Upstream Sync Workflow

1. Version pin + range in pyproject.toml
2. Changelog-driven review before bumps
3. Contract tests run in CI
4. Staged rollouts: dev -> staging -> prod
5. Rollback plan for each dependency

## How to Not Create a Brittle Monster

1. NEVER import external directly in core/
2. NEVER pin exact versions without testing
3. NEVER customize external repos locally
4. ALWAYS write adapter tests first
5. ALWAYS review changelog before bumping
6. ALWAYS have a rollback plan
""")

ws("07-feature-map.md", """# Section 7: Feature Map

## By Phase

### MVP Features
- Watchlists with live prices
- Market internals (indices, A/D, P/C ratio)
- Option chain explorer with Greeks
- Price breakout scanner
- Gap scanner (overnight + intraday)
- Position viewer (read-only)
- Portfolio summary (P&L, exposure)
- Log viewer
- Connection status

### Phase 2 Features
- Full execution cockpit (order placement via OpenAlgo)
- Risk dashboard (delta, beta, VaR, stress)
- Backtest engine
- Historical price viewer with indicators
- Options strategy assistant (payoff, breakeven)
- IV rank/percentile viewer
- Trade journal with auto-capture
- Technical price alerts
- Signal generator (simple)
- Plugin manager

### Phase 3 Features
- Regime-aware signal engine
- Multi-scanner composite
- Options spread analyzer
- Rolling suggestions for options
- Auto-trailing stop loss
- Signal-based auto-execution
- Portfolio correlation matrix
- Decision audit trail
- Performance analytics (Sharpe, Sortino, win rate)
- Strategy comparison tool

### Optional/Experimental
- Pattern recognition (chart patterns)
- AI-assisted trade recommendations
- Community plugin marketplace
- Cloud/SaaS deployment mode
- Multi-user/collaboration features
""")

ws("08-shettybot-evolution.md", """# Section 8: ShettyBot Evolution

## What ShettyBot Got Right

1. Regime detection - classifying market state
2. Signal interpretation - scoring and context
3. Strategy hints - mapping context to approaches
4. Cockpit thinking - unified information view
5. Decision support - operator-in-the-loop
6. Risk awareness - built-in guardrails

## What ShettyBot Got Wrong

1. Monolithic architecture - everything coupled
2. Direct broker integration - duplicate of OpenAlgo
3. Telegram as primary UX - limited interactivity
4. No clean separation - signal, execution, risk intermixed
5. Hardcoded strategies - core changes needed for new strategies
6. No storage abstraction - database coupling

## What Moves Where

| ShettyBot Component | New Home | Status |
|--------------------|----------|--------|
| Regime detection | intelligence/regime/ | Rebuilt |
| Signal generators | intelligence/signals/ | Rebuilt, pluggable |
| Strategy hints | intelligence/hints/ | Rebuilt |
| Risk management | risk/ | Rebuilt |
| Order execution | integration/OpenAlgoAdapter | Delegated |
| Broker connection | integration/DhanAdapter | Delegated |
| Cockpit UI | terminal/ | Rebuilt |
| Alert system | observability/ | Rebuilt |
| Telegram | plugins/ (optional) | Deprioritized |

## What Gets Deprecated
- V1 direct OpenAlgo integration (superseded)
- V1 database schemas (replaced)
- V1 Telegram workflow (optional plugin)
- V1 single-file signal logic (modularized)
- V1 broker adapters (delegated to OpenAlgo)

## What Gets Preserved
- Regime classification methodology
- Signal scoring algorithms
- Risk calculation approaches
- Strategy-to-regime mapping
- Cockpit information architecture

These are extracted as specs, then reimplemented cleanly.
""")
print("Sections 6-8 script written")
