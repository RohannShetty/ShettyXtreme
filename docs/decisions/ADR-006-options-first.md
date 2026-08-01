# ADR-006: Options-First Market Focus

## Status
Accepted (2026-08-01).

## Context
ShettyBot V1's DNA is options intelligence (voters, OI, PCR, strike selection, TP3). The current codebase has a full `intelligence/options/` and `options/` package, but the two options API endpoints are 501 stubs. The Aug-01 brief demands a "complete pipeline."

## Decision
1. Index options (NIFTY/BANKNIFTY weekly expiries) are the primary intelligence + execution pipeline: option chain, IV/OI/PCR context, signal-drift EV strike selection, strategy hints, options-aware risk.
2. Equities/indices remain first-class in the terminal layer (watchlists, scanners, market internals, gap discovery) but are NOT the decision engine's focus.
3. "Complete pipeline" = no stubs: `/api/intelligence/options` and `/api/intelligence/strategy-hint` are implemented in Phase 2 (creating `strategy_hints.py` and a real `conviction_engine.py`), plus `VoterRegistry`.

## Consequences
- Phase-2 scope is precisely defined by the two 501 endpoints and the landmine inventory (Section 02).
- Scanner/gap features serve opportunity discovery for both asset classes without duplicating the options decision path.
