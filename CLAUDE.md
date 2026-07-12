# ShettyXtreme - Project Context

## Core Identity
ShettyXtreme is a STANDALONE Indian-market trading intelligence and execution platform. It is NOT a broker wrapper, NOT a charting tool, and NOT a strategy bot alone. It is a trading operating system combining terminal-grade research, live decision support, options intelligence, and broker-integrated execution.

## Critical Architecture Rule (July 12, 2026 Reset)
ShettyXtreme is STANDALONE SOFTWARE. NO runtime dependency on OpenAlgo or any third-party service. Patterns and code are absorbed/copied/modified from reference repos, but ShettyXtreme runs as independent software.

- DhanHQ-py: pip dependency (library, acceptable)
- OpenAlgo: patterns absorbed as first-party code, NOT a service dependency
- Dhan Trading API and Data API: separate adapters, separate credentials

## Architecture Layers
- core/ → ZERO external imports (domain models, event bus, contracts, config, storage)
- integration/ → Dhan Trading + Dhan Data adapters (first-party, DhanHQ-py)
- intelligence/ → Feature engine, regime, signal engine (conviction, D/P/G), options intelligence, risk, scanners
- execution/ → Order lifecycle, position management (TP3 FIXED), semi-auto
- learning/ → Outcome tracking, MFE/MAE, walkforward, calibration
- terminal/ → FastAPI + web frontend (using taste-skill + ui-ux-pro-max-skill)
- knowledge/ → Phase 3+ document store, tagger, heuristic extractor (physically separated)

## Import Rules (CI Enforced)
- core/ imports NOTHING external
- intelligence/ imports core/ only
- integration/ imports core/interfaces + external APIs
- knowledge/ imports core/ only; CANNOT import intelligence/ or execution/
- No file > 500 lines

## Key ShettyBot V1 Bugs Fixed in ShettyXtreme
1. Strike selection: signal-drift EV (NOT risk-neutral GBM noise)
2. Loss limit: blocks ENTRIES ONLY (position management ALWAYS runs)
3. TP3: check_targets BEFORE update_tsl (TP3 is REACHABLE)
4. NEUTRAL signal state (no bearish tie-break)
5. OI normalized by time-of-day (no clock bias)
6. One canonical stop-loss definition (premium-relative, vol-aware)
7. Dead voters removed (ML AUC 0.518 removed, HMM removed, Markov retuned)
8. Voter weights in config, not hardcoded in add_vote()
9. Cost model: slippage/spread/brokerage in ALL EV computations
10. Voter correlation awareness (block caps where needed)

## Test Gates
Every wave must pass:
1. All previous wave tests still pass (no regressions)
2. `grep -r "import openalgo\|from openalgo" src/` → ZERO matches
3. No file > 500 lines
4. core/ has zero external imports
5. `PYTHONPATH="" python -m pytest tests/ -v --tb=short` → ALL PASS

## Python
Python 3.11+. Use `PYTHONPATH=""` prefix for non-hermes Python commands.
