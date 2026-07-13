# Changelog

All notable changes to ShettyXtreme are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.6.0] — 2026-07-13

### Architecture Reset
- ShettyXtreme is now STANDALONE software with NO runtime dependency on OpenAlgo or any third-party service
- OpenAlgo patterns absorbed as first-party code (broker adapter pattern, order validation, WebSocket architecture)
- DhanHQ-py remains as pip dependency (library, not a service — acceptable)
- Old Textual TUI replaced with web-based terminal (FastAPI + HTML/CSS/JS)
- Complete 22-section architecture blueprint written and committed

### Wave 1 — Standalone Integration Layer
- Deleted `integration/openalgo/` directory entirely — zero OpenAlgo references in src/
- Created `DhanTradingAdapter` (479 lines): order placement, positions, holdings, EDIS, margin, auth with SessionHealth auto-refresh wrapper (~3AM IST token expiry)
- Created `DhanDataAdapter` (427 lines): live market feed WS, historical OHLC, OI/PCR, separate credentials (error 806 handling), staleness detection
- Created `OrderValidator` (127 lines): validates exchanges (NSE/BSE), actions (BUY/SELL), price types (MARKET/LIMIT/SL/SL-M), product types (MIS/NRML/CNC/MARGIN), validity (DAY/IOC)
- Created `InstrumentMaster` (235 lines): fetches security list from Dhan, stores in SQLite, resolves symbols to security IDs, calculates expiry with holiday awareness (IST)
- Updated config: removed OpenAlgo fields, added dual Dhan credentials (Trading + Data API separate)
- Updated terminal: dual Dhan status indicators (trading + data)
- 80 tests in tests/wave1/

### Wave 2 — Intelligence Layer Core
- Created `FeatureEngine` (441 lines): streaming O(1) per tick indicators (SMA, EMA, ATR, ADX, VWAP, RSI, Bars) with staleness guard
- Created `RegimeClassifier` (159 lines): TRENDING_UP/DOWN, RANGE_BOUND, VOLATILE, TRANSITION — NO Markov chains, pure feature-based
- Created `SignalEngine` (271 lines): voter plugin system, conviction (D/P/G), explicit NEUTRAL state (no bearish tie-break)
- Created 4 voter plugins: options_flow (PCR contrarian + OI time-of-day normalized), ORB, micro (EMA crossover), breadth
- Created `OptionsIntel` (246 lines): IV rank/percentile, PCR contrarian, expiry selection (next-week chain fix), strike selection with SIGNAL-DRIFT EV (NOT risk-neutral GBM)
- Created `RiskEngine` (177 lines): loss limit blocks ENTRIES ONLY (position management always runs), composable filter chain
- Created `CostModel` (100 lines): slippage/spread/brokerage/STT in all EV computations, marginal flag
- Voter weights in `voter_weights.yaml` (not hardcoded)
- 84 tests in tests/wave2/

### Wave 3 — Terminal UI (Web-Based)
- Created FastAPI backend: 6 routers (watchlist, intelligence, execution, scanner, health), pydantic response models
- Created WebSocket manager for live data push (ticks, signals, alerts, regime changes)
- Created web terminal HTML: dark cockpit layout (#0A0A0A, #121212, #4AF626 green, #E61919 red, JetBrains Mono)
- Panels: watchlist, intelligence cockpit, execution cockpit, scanner/alerts/logs
- Keyboard shortcuts, progressive disclosure, WS reconnect
- Deleted old Textual TUI: app.py, config.py, panels/ (12 files, -1,987 lines)
- 25 tests in tests/wave3/

### Waves 4-6 — Learning Loop + Execution + Shadow Models
- Created `OutcomeTracker`: immutable signal decisions in SQLite
- Created `VoterQualityTracker`: hit rates CONSUMED (weights adjusted [0.1, 2.0] based on performance, not just logged)
- Created `MfeMaeCalculator`: one-directional MFE/MAE tracking with percentile
- Created `WalkforwardEvaluator`: honest evaluation using option premium + TP/TSL/EOD exit policy + cost-adjusted (NOT underlying % moves)
- Created `AnalyticsEngine`: signal quality by regime, voter contribution, cost analysis, performance summary
- Created `ExecutionEngine`: semi-auto approval flow, pre-trade risk check
- Created `PositionManager`: TP3 REACHABLE (check_targets before update_tsl), one canonical stop-loss (premium-relative, vol-aware)
- Created `execution_config.yaml`: TP targets, TSL, EOD exit time
- Created `ShadowManager`: shadow voters run alongside but DON'T gate
- Created 4 shadow voters: DPG, signal-drift EV, time-bucketed OI, ORB decay
- Created `CalibrationCurve`: conviction to win-rate mapping (isotonic/binning, 30+ min)
- Created `VoterCorrelation`: pairwise agreement, block caps (prevent over-representation)
- 56 tests across tests/wave4/, tests/wave5/, tests/wave6/

### Key ShettyBot V1 Bugs Fixed
1. Strike selection: signal-drift EV (was risk-neutral GBM noise)
2. Loss limit: blocks ENTRIES ONLY (was freezing all trading)
3. TP3: check_targets before update_tsl (was unreachable)
4. NEUTRAL signal state (was forced bearish tie-break)
5. OI normalized by time-of-day (was clock bias)
6. One canonical stop-loss definition (was 3 inconsistent definitions)
7. Dead voters removed from conviction (were diluting confidence)
8. Voter weights in config YAML (were hardcoded in add_vote())
9. Cost model in all EV computations (was no cost model)
10. Voter quality consumed (was logged but not consumed)

### Test Summary
- 245 wave tests (80 + 84 + 25 + 56) — all pass, zero warnings
- Zero lazy imports across entire codebase
- Zero OpenAlgo references in src/
- No file > 500 lines
- Type hints on all functions (AST verified)

## [0.1.0] — 2026-07-11

### Initial Setup
- Project created at D:\ShettyXtreme
- GitHub repo: https://github.com/RohannShetty/ShettyXtreme
- Initial architecture exploration with OpenAlgo dependency (later corrected)
- Core domain models, event bus, interfaces, config, storage
