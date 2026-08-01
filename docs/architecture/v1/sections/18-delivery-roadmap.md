# Section 18: DELIVERY ROADMAP

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

