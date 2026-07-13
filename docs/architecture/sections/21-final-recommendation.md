# Section 21: FINAL RECOMMENDATION

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
