# Section 14: DATA + DECISION INTELLIGENCE

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

