# Section 8: ShettyBot Evolution

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
