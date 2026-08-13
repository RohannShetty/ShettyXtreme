# ShettyXtreme Domain Model

## Core Concepts

### Trading Modes
- **OBSERVER**: Watch-only mode, never places orders (default, safe)
- **PAPER**: Practice money with realistic fills, fees, margin (simulated trading)
- **LIVE**: Real orders with typed confirmation (actual trading)

### Market Data
- **Watchlist**: User-curated list of symbols to monitor
- **Option Chain**: Strikes, expiries, greeks for a given underlying
- **Expiry**: Contract expiration date (weekly/monthly distinction)
- **Strike**: Option exercise price
- **Greeks**: Δ (delta), Γ (gamma), Θ (theta), V (vega) — risk metrics

### Execution
- **Proposal**: System-generated trade suggestion with full leg details
- **Order**: User-approved trade request
- **Position**: Open trade with P&L tracking
- **Kill Switch**: Emergency stop (Ctrl+Shift+K)

### Intelligence
- **Regime**: Market state (ranging/trending/volatile)
- **Scanner**: Automated opportunity detection (11 types)
- **Hints**: Strategy suggestions based on market conditions
- **Research**: AI-generated analysis briefs (DeepSeek LLM)

### Risk Management
- **Margin**: Capital required for positions
- **Heat Map**: Portfolio risk visualization (sectoral, greeks, stress tests)
- **Stop Loss / Target**: Exit levels for positions

## Architectural Decisions

### v0.15.0 Complete Refactor (2026-08-12)
**Decision**: Refactor entire frontend + backend API from scratch using shadcn-svelte + awesome-design-md, with incremental migration strategy.

**Rationale**: 
- Tests were passing but UI was broken (data not loading, interactions failing)
- Design debt accumulated across 6 phases of development
- Need professional, modern UI for production use

**Scope**:
- Frontend: Complete rebuild with shadcn-svelte components
- Backend API: Redesign contracts, data models, component architecture
- Migration: Incremental with parallel build (old system runs until new validated)

**Trade-offs**:
- Larger scope than bug-fix-only approach
- Addresses root causes, not symptoms
- Enables future feature development on solid foundation

## Glossary

| Term | Definition |
|------|-----------|
| **Instrument** | Tradeable asset (stock, index, option, future) |
| **Underlying** | Base asset for derivatives (e.g., NIFTY for NIFTY options) |
| **Lot Size** | Minimum tradeable quantity (varies by instrument) |
| **Premium** | Option price (what buyer pays seller) |
| **IV Rank** | Implied volatility percentile (0-100, historical comparison) |
| **PCR** | Put-Call Ratio (sentiment indicator) |
| **Max Pain** | Strike where option writers lose least at expiry |
