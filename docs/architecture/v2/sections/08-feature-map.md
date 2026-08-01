# Section 08 — Feature Map

> The capability map, grouped by the 13 product layers, phased and classified so the roadmap (per [Section 17](17-delivery-roadmap.md)) never guesses what matters.

**Phases.** MVP (Phase 2) = pipeline completion (two 501 stubs, landmines, credential fallback, WS request-code fix, observer default) + Svelte terminal — i.e., the Phase-2 milestone. Phase 3 = advanced intelligence (shadow activation, calibration, voter correlation, research workspace, AI research layer per D3, walkforward depth). Phase 4 = multi-broker (optional), backtest depth, knowledge layer (per D12). Optional = evergreen backlog, incl. **never** items (below).

**Classification.** Essential = load-bearing; Valuable = real edge/UX once essentials stand; Seductive-distraction = shiny, only after measured demand; Deprioritized = contradicts D2/D3/D10 or the options-first thesis.

Every MVP row ships in the Svelte terminal governed by DESIGN.md (per D4/D9); notes cite existing modules or landmines Phase 2 clears.

## 1. Market terminal

| Feature | Phase | Classification | Notes |
|---|---|---|---|
| Watchlist (symbols, LTP, % change; indices/stocks/futures groups) | MVP | Essential | |
| Market internals (indices panel, advance/decline, sector heatmap) | MVP | Essential | Breadth-voter inputs |
| Quote detail (OHLC, day range, volume, LTP tape) | MVP | Essential | |
| Top movers / most active tape | Phase 3 | Valuable | Fincept dashboard concept |
| Candlestick charting with indicators | Phase 3 | Valuable | No charting dependency without need (per [Section 15](15-design-system-terminal-ux.md)) |
| India economic calendar + news ticker | Phase 3 | Valuable | India-only (per [Section 04](04-india-first-scope.md)) |

## 2. Scanners

| Feature | Phase | Classification | Notes |
|---|---|---|---|
| Gap scanner | MVP | Essential | `scanners/gap_scanner.py` |
| Breakout scanner | MVP | Essential | `scanners/breakout_scanner.py` |
| Scanner console (config + results grid) | MVP | Essential | |
| Indicator-catalog scanner (RSI, MACD, Bollinger, ATR, ADX, Keltner, Ichimoku) | Phase 3 | Valuable | Indicator catalog |
| OI buildup / option-chain screener | Phase 3 | Valuable | Fincept OI pattern |

## 3. Research

| Feature | Phase | Classification | Notes |
|---|---|---|---|
| Research workspace (overview → financials → valuation → technicals → peers → sentiment tabs) | Phase 3 | Valuable | Fincept tabs |
| AI research briefers (LLM drafts typed briefs; human-approval loop) | Phase 3 | Valuable | Never order-gating (per D3; BRIEF-ai-hedge-fund) |
| Econometrics toolset (ARIMA/GARCH/VAR/cointegration) | Phase 3 | Valuable | |
| Outcome studies (signal/voter quality vs realized moves) | Phase 3 | Essential | Feeds the learning loop |
| Knowledge layer (ingest, tag, link; human-gated) | Phase 4 | Valuable | Imports core only (per D12) |
| Report builder / export | Optional | Deprioritized | |

## 4. Signal intelligence

| Feature | Phase | Classification | Notes |
|---|---|---|---|
| Streaming feature engine (O(1)/tick) | MVP | Essential | `features/feature_engine.py` |
| Regime classifier (coarser bars) | MVP | Essential | No Markov on 1m noise (per [Section 14](14-data-decision-intelligence.md)) |
| Signal engine + voters (breadth, micro, options_flow, orb, iv_rank) | MVP | Essential | `signals/` + `voters/` |
| Conviction computation (D/P/G, NEUTRAL state) | MVP | Essential | `conviction_engine.py` landmine cleared |
| `VoterRegistry` (pass-stub) | MVP | Essential | Phase-2 landmine |
| Shadow voters (incl. shadow DPG) | Phase 3 | Essential | `voters/shadow/` |
| Voter-correlation block caps | Phase 3 | Essential | Module delivered (`intelligence/signals/voter_correlation.py`); consumption/gating wired into the risk filter chain is Phase 3 |
| Calibration curves | Phase 3 | Essential | `learning/calibration.py` |
| Walkforward depth (purged CV) | Phase 3 | Essential | `learning/walkforward.py` |
| ML/RL signal models | Optional — **never until proven** | Deprioritized | v1 ML voter (AUC 0.518) removed |
| LLM in the live signal path | never | Deprioritized | Per D3: research layer only |

## 5. Options strategy assistant

| Feature | Phase | Classification | Notes |
|---|---|---|---|
| Option chain (501 stub) | MVP | Essential | `test_get_options` fixed in Phase 2 |
| Strategy hints (501 stub) | MVP | Essential | `strategy_hints.py` landmine cleared |
| Greeks, IV rank, OI tracker | MVP | Essential | `options/` |
| Strategy analyzer (single-leg hints, payoff, EV with cost model) | MVP | Essential | `options/strategy_analyzer.py` |
| Options EV strike selection (signal-drift EV, not risk-neutral GBM) | Phase 3 | Essential | Corrects v1 bug (per [Section 14](14-data-decision-intelligence.md)) |
| IV surface / smile visualization | Phase 3 | Valuable | Black-76 OTM convention |
| GEX, PCR, max-pain analytics | Phase 3 | Valuable | |
| Multi-leg strategy constructor | Phase 4 — **deferred** | Valuable | Single-leg proof first |
| Payoff / straddle simulator | Phase 4 | Valuable | |

## 6. Execution cockpit

| Feature | Phase | Classification | Notes |
|---|---|---|---|
| Order ticket with pre-trade risk + cost summary | MVP | Essential | Margin, limits, cost model |
| Semi-auto approval flow | MVP | Essential | `execution/execution_engine.py`; NEUTRAL cannot order |
| Position manager (TP/TSL/EOD 15:15 flatten) | MVP | Essential | One canonical SL definition |
| Paper trading engine | MVP | Essential | `execution/paper_trading.py` |
| Pending orders / action center | MVP | Essential | |
| Order / trade book views | MVP | Essential | |
| Basket / conditional orders (Dhan capabilities) | Phase 4 | Valuable | DhanHQ 2.3.0rc1 features; pinned 2.2.0 (per [Section 11](11-dhan-integration.md)) |
| Multi-broker adapters | Phase 4 — optional | Valuable | Dhan-first (per D6); implement `core/interfaces` protocols |
| Telegram as an execution channel | never | Deprioritized | Terminal is the only control surface |

## 7. Portfolio / risk

| Feature | Phase | Classification | Notes |
|---|---|---|---|
| Risk engine + cost model (slippage, spread, brokerage, STT) | MVP | Essential | `risk/risk_engine.py` + `cost_model.py` |
| P&L dashboard (today's P&L, positions, exposure) | MVP | Essential | |
| Pre-trade risk gates (margin, loss limits, position caps) | MVP | Essential | Filter chain |
| VaR / CVaR / stress | Phase 3 | Valuable | VaR/CVaR curriculum |
| Drawdown kill-switch | Phase 3 | Valuable | Auto kill (BRIEF-fincept) |
| Portfolio attribution / optimization | Optional | Deprioritized | |

## 8. Alerts

| Feature | Phase | Classification |
|---|---|---|
| Price / indicator alerts | MVP | Essential |
| Signal / conviction alerts | MVP | Essential |
| Risk & health alerts (margin, 806 entitlement, token expiry; 806 per [Section 11](11-dhan-integration.md)) | MVP | Essential |
| Notification channels beyond the terminal | Optional | Deprioritized |

## 9. Journaling

| Feature | Phase | Classification |
|---|---|---|
| Outcome tracking (immutable labels; `learning/outcome_tracker.py`) | MVP | Essential |
| Trade journal with auto-annotated fills | Phase 3 | Valuable |
| Review workflow (MFE/MAE, walkforward reports; `learning/mfe_mae.py`) | Phase 3 | Valuable |

## 10. Automation

| Feature | Phase | Classification |
|---|---|---|
| Session controls (OBSERVER default; LIVE is explicit per-session confirmation; per D10, fixes `test_execution_mode_default`) | MVP | Essential |
| EOD flatten (15:15 IST) | MVP | Essential |
| Scheduled maintenance (token refresh ~3AM, backfills, instrument master) | MVP | Essential |
| Auto-execute approved signals (human-approval loop preserved, per D3) | Phase 3 | Valuable |
| Visual automation DAG | Optional | Deprioritized |

## 11. Analytics

| Feature | Phase | Classification | Notes |
|---|---|---|---|
| Analytics engine dashboards | MVP | Essential | `learning/analytics.py` |
| Voter-quality reporting (CONSUMED → weight decay) | Phase 3 | Essential | `learning/voter_quality.py` |
| Calibration reports | Phase 3 | Essential | `learning/calibration.py` |
| Benchmark vs index / ATM straddle | Phase 3 | Valuable | Honest edge measurement |
| Backtest depth (vectorbt strategy library) | Phase 4 | Valuable | |

## 12. Operator controls

| Feature | Phase | Classification |
|---|---|---|
| Mode switcher with confirmation (observer / sim / paper / live; per D10) | MVP | Essential |
| Health panel (SessionHealth, feed status, credential health) | MVP | Essential |
| Credential manager (Fernet store; fallback data token; single-primary + fallback per D8) | MVP | Essential |
| Global kill switch | MVP | Essential |
| Incident / audit log viewer | MVP | Essential |

## 13. Admin / dev diagnostics

| Feature | Phase | Classification |
|---|---|---|
| Config editor (validated YAML; `configs/default.yaml`) | MVP | Essential |
| Observability views (logs, metrics, event bus) | MVP | Essential |
| Vendor sync status (`scripts/sync_vendor.py`; per D1/D7) | MVP | Essential |
| Test / landmine health dashboard | MVP | Valuable |
| Plugin registry UI | Optional | Deprioritized |

## Hard lines (never build)

- Multi-leg strategy constructor — deferred to Phase 4 (single-leg proof first)
- ML/RL signal models — never until proven (v1 ML voter was random)
- Telegram as primary channel — never (terminal is the only control surface)
- SaaS / multi-tenancy / billing — never (private use only, per D2)
- LLM order placement or gating — never (research layer only, per D3)
- Celebrity persona agents as edge — never; at most optional research lenses (BRIEF-ai-hedge-fund)

## Cross-references

[Section 05 — System Boundaries](05-system-boundaries.md) (layer ownership), [Section 06 — Proposed Architecture](06-proposed-architecture.md) (services and data flow), [Section 13 — Systematic Trading Breadth](13-systematic-trading-breadth.md) (curriculum over these capabilities), [Section 14 — Data & Decision Intelligence](14-data-decision-intelligence.md) (intelligence rows compose), [Section 15 — Design System & Terminal UX](15-design-system-terminal-ux.md) (terminal carrying the MVP rows), [Section 17 — Delivery Roadmap](17-delivery-roadmap.md) (milestones these phases bind to).
