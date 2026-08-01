# Section 09 — ShettyBot Evolution

> ShettyBot V1's intelligence DNA carried into v2: what is retained and reimplemented, what is refactored into engines, what is deprecated, and the 10 critical bug fixes — with delivery status verified against the current codebase (v0.6.0, Phase 3 of v1 delivered, per pack). This section supersedes `docs/architecture/v1/sections/09-shettybot-evolution.md`; it is a rewrite, not a copy.

## 1. Retain (reimplemented, not ported)

Every V1 concept below is preserved as a *specification* and reimplemented cleanly on the v2 layer map ([Section 05 — System Boundaries](05-system-boundaries.md)) — no V1 code is copied wholesale.

| ShettyBot V1 concept | v2 home | Status |
|---|---|---|
| Regime detection methodology | `intelligence/regime/regime_classifier.py` | Reimplemented — deterministic trend/range/volatile on coarser bars; **no Markov model on 1m noise** |
| Conviction concept | `intelligence/signals/` | Reimplemented — direction/participation/disagreement (D/P/G), participation-normalized |
| Options-flow voter concept | `intelligence/voters/options_flow_voter.py` | Reimplemented — PCR contrarian with OI time-of-day percentile normalization |
| Shadow model concept | `intelligence/voters/shadow/` + `signals/shadow_manager.py` | Reimplemented — shadow voters (DPG, signal-drift EV, time-bucketed OI, ORB decay) logged and scored against realized outcomes; never gate live conviction |
| Learning loop concept | `learning/` | Reimplemented — `OutcomeTracker`, `VoterQualityTracker` (quality **consumed** → weight adjustments, not just logged), `MfeMaeCalculator`, `WalkforwardEvaluator`, `CalibrationCurve`, `AnalyticsEngine` |
| Cockpit thinking | `terminal/` | Reimplemented — web cockpit (FastAPI + Svelte per D9), not Textual |
| Risk awareness | `intelligence/risk/risk_engine.py` | Reimplemented — entries-only loss limit, composable filter chain, cost model |

## 2. Refactor (monoliths split into event bus + engines)

| V1 monolith | v2 decomposition |
|---|---|
| `live_dispatcher.py` (2,702 lines) | `core/event_bus/` (Topic/Event pub-sub) + `intelligence/signals/` (SignalEngine) + `execution/` (ExecutionEngine, PaperTradingEngine, PositionManager) |
| `dashboard.py` (3,381 lines) | FastAPI backend + Svelte frontend (D9), routers: watchlist, intelligence, execution, scanner, health, auth, postback, settings |
| Hardcoded strategies in one file | Voter plugin system (`intelligence/voters/` breadth, micro, options_flow, orb, iv_rank) with a registry; `VoterRegistry` is a Phase-2 stub (per pack landmines) — Phase 2 wires it to YAML config |
| V1 direct OpenAlgo-server integration | First-party Dhan adapters + vendored execution plumbing (D1, see [Section 10 — OpenAlgo Utilization](10-openalgo-utilization.md)) |
| V1 database schemas | SQLite KV (`data/shetty_kv.db`) + DuckDB TS (`data/shetty_ts.db`) |

## 3. Deprecate

| V1 component | Fate |
|---|---|
| Markov voter (momentum follower misread as regime predictor) | Removed. Regime classification is deterministic; no hidden-Markov layer |
| ML voter (AUC 0.518 ≈ random) | Removed entirely |
| HMM voter (poorly calibrated) | Removed |
| Telegram as primary interface | Deprecated — optional alert channel at most; the cockpit is the primary surface |
| Textual/Rich TUI | Replaced by the web terminal (D9) |
| V1 OpenAlgo runtime dependency | Superseded by vendoring (D1): zero runtime dependency, no `import openalgo` anywhere in `src/` |

## 4. UI / cockpit concepts carried forward

The V1 cockpit information architecture survives as the v2 terminal spec (per D4 DESIGN.md, detailed in [Section 15 — Design System & Terminal UX](15-design-system-terminal-ux.md)): session controls with explicit mode (OBSERVER default, D10), watchlists, scanner panels, market internals, positions/risk panel, logs/alerts, drill-down from signal to evidence, and explainability surfaces (why a voter voted, what the regime is, what a signal is saying in plain language).

## 5. Signal / risk / research components

- **Signal components:** direction score, participation, disagreement (D/P/G), weighted voter aggregation with explicit NEUTRAL state, conviction as `abs(weighted_dir)` — same algorithms as V1, reimplemented in `intelligence/signals/signal_engine.py`.
- **Risk components:** position sizing, entries-only loss limit, margin guardrails, composable filter chain, cost model in every EV calculation (`intelligence/risk/`).
- **Research components (new in v2):** strategy-to-regime mapping and signal interpretation are the bridge into the research workspace and strategy-hints panel (Phase 2, per D6; see [Section 12 — AI Agentic References](12-ai-agentic-references.md) for the research layer).

## 6. Unique strengths preserved

These are the platform's moat — every one has an explicit owner in v2:

| Strength | v2 owner |
|---|---|
| Trading intelligence (voter system, conviction) | `intelligence/signals/`, `intelligence/voters/` |
| Regime-awareness (context for every signal) | `intelligence/regime/` |
| Signal interpretation (D/P/G breakdown, voter-level explanation) | `intelligence/signals/` + terminal explainability |
| Strategy hints (strategy-to-regime/strike selection) | `intelligence/hints/` — Phase 2 (501 stub today, per D6) |
| Cockpit thinking (all context on one screen) | `terminal/` (D9, DESIGN.md per D4) |
| Decision support (semi-auto approval, operator decides) | `execution/` (D10) |

## 7. The 10 critical bug fixes — delivery status

Verified against the current codebase (v0.6.0). "Delivered" means the fix is live in `src/`; "Phase 2" items are stubs or wiring gaps on the pack's landmine list.

| # | Bug (V1) | Fix (v2 spec) | Status in codebase |
|---|---|---|---|
| 1 | Strike selection = risk-neutral GBM noise | Signal-drift EV with actual exit policy | **Shadow-only** — `shadow_signal_drift_ev` runs and is scored; live strategy-hint/strike-selection endpoint is a 501 stub (`intelligence/hints/` landmine). Live delivery is Phase 2 |
| 2 | Loss limit freezes ALL trading | Loss limit blocks **entries only** | **Delivered** — `risk_engine.py` `LossLimitRule`; source comment cites the V1 fix ("Position management always allowed regardless of loss limit") |
| 3 | TP3 unreachable | `check_targets` before `update_tsl` | **Delivered** — `execution/position_manager.py` calls `_check_targets` before `_update_tsl`, with docstring documenting the ordering |
| 4 | No NEUTRAL signal (bearish tie-break) | Explicit NEUTRAL state | **Delivered** — `signal_engine.py` `SignalDirection.NEUTRAL` emitted when weighted direction is inconclusive |
| 5 | OI time-of-day clock bias | Normalize OI by time-of-day percentile | **Delivered** — `options_flow_voter.py` uses `oi_percentile_rank`; `shadow_time_bucketed_oi` validates the bucket approach as a shadow |
| 6 | 3 inconsistent stop-loss definitions | One canonical (premium-relative, vol-aware) | **Partial** — a single TSL implementation exists in `PositionManager` (ATR-based); the canonical premium-relative, vol-aware entry-SL rule is specified for the risk filter chain and lands with it in Phase 2 |
| 7 | Dead voters dilute confidence | Conviction participation-normalized; dead voters removed | **Delivered** — live voter set is breadth, micro, options_flow, orb, iv_rank; Markov/ML/HMM voters are gone (section 3) |
| 8 | Weights hardcoded in `add_vote()` | Weights in config YAML | **Not delivered** — `SignalEngine.register_voter(weight=...)` API exists but `VoterRegistry` is a pass-stub and `configs/default.yaml` carries no voter weights; YAML wiring is Phase 2 |
| 9 | No cost model | Slippage/spread/brokerage/STT in ALL EV | **Delivered** — `risk/cost_model.py` (`compute_cost`, `adjust_ev`, `CostBreakdown`); consumed by execution and `learning/walkforward.py` |
| 10 | No voter correlation awareness | Block caps per voter correlation group | **Delivered** — `signals/voter_correlation.py` computes the correlation matrix, groups correlated voters, and scales group weights to a configured cap |

Net: 7 of 10 delivered in the current codebase; #1 (live hints), #6 (canonical SL rule in the filter chain), #8 (YAML weights) close in Phase 2 alongside the landmine fixes. Cross-references: [Section 02 — Current-State Reaudit](02-current-state-reaudit.md) (landmines), [Section 06 — Proposed Architecture](06-proposed-architecture.md) (event flow), [Section 14 — Data → Decision Intelligence](14-data-decision-intelligence.md) (feature → regime → signal → options EV → risk chain this section's strengths feed).
