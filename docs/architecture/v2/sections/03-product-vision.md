# Section 03 — Product Vision

What ShettyXtreme is for, who it is for, why it beats the alternatives a prosumer options trader actually has today, and what "unified platform" means concretely. The stance is sober by design: this is a personal trading-edge tool (per D2, D11), not a fantasy about beating markets — it reduces friction, exposes structure, and makes decisions cost- and risk-aware.

## 1. The problem: fragmented tools, no pipeline

An Indian prosumer options trader (NIFTY/BANKNIFTY weekly, Dhan as broker) currently assembles a working setup from at least four unrelated pieces:

1. **Broker terminal** (Dhan web/mobile/desktop) — order placement, positions, P&L, basic chain. No intelligence beyond what Dhan ships.
2. **Analytics tooling** — TradingView/other charting for levels and indicators; scattered scanners; OI/max-pain data pasted from websites or scraped by hand.
3. **Personal scripts** — half-maintained Python notebooks and bots (the pre-v2 ShettyBot reality): regime logic, voters, risk rules, each with its own data fetches, its own conventions, its own rot.
4. **Spreadsheets and memory** — for cost math, journaling, and "what happened last time I did this".

Each piece speaks a different data model. No shared instrument/order/risk vocabulary. No single place where chain, regime, cost, risk, and P&L are reconciled. The cost of this fragmentation is not comfort — it is **decisions made without the full picture**: strike chosen without IV-rank context, entry sized without margin/cost-aware EV, a setup re-entered that the learning loop would have flagged as a loser. ShettyXtreme exists to collapse the four tools into one pipeline where every stage feeds the next.

## 2. Who it is for first

- **India prosumer options trader** on the NSE/BSE index-options complex (NIFTY/BANKNIFTY weeklies), equities as terminal breadth (per D6).
- **Dhan-first** (D8): one client_id, single-primary OAuth consent token with a data-fallback slot; no multi-broker ambition at launch.
- **Private use** (D2): never distributed or sold; single operator, own capital, prop-style scale (D11). This license posture is what makes the OpenAlgo vendoring strategy legal and keeps the product free of compliance theater.
- The user is the operator: OBSERVER mode by default, LIVE an explicit per-session action (D10). The platform is a decision-support and execution cockpit for one person, not a retail SaaS.

## 3. Why better than a plain broker terminal AND a plain analytics terminal

| Dimension | Plain broker terminal | Plain analytics terminal | ShettyXtreme |
|---|---|---|---|
| Options intelligence | Chain + order ticket only | Charts, sometimes IV; no chain context | Chain + IV/OI/PCR + regime overlay + strike/strategy hints in one pane (D6) |
| Execution | Native (but no validation) | None — signals in one app, orders in another | Execution engine with pre-trade validation, cost model, semi-auto approve, paper mode ([Section 11 — Dhan Integration](11-dhan-integration.md)) |
| Cost awareness | Brokerage shown after the fact | Usually absent | cost_model inside the risk engine: brokerage, STT, slippage, expiry/day trade math — EV is computed net, before entry |
| Risk | Per-position margin display | Generic risk metrics | One risk engine across positions: limits, drawdown awareness, kill-switch posture |
| Learning | Tradebook you never re-read | No outcome tracking | OutcomeTracker → VoterQualityTracker → WalkforwardEvaluator → CalibrationCurve: the platform gets measurably better at what IT says |
| Data model | Broker's own | Each tool its own | One data model end-to-end: the same symbols, ticks, and orders flow through every stage |
| Modes | Live only | Backtest or live, rarely both | Backtest / sim / observer / paper / live sharing one pipeline ([Section 06 — Proposed Architecture](06-proposed-architecture.md)) |

The broker terminal wins on placement; the analytics terminal wins on charting; neither connects the two, and neither learns. ShettyXtreme's edge is the connection: the chain you look at is the chain you trade, and what you trade is what gets measured.

## 4. How it helps make money — practically

Six mechanisms, each mapped to a concrete India-options workflow (no marketing claims — these are pipeline features; detail in [Section 14 — Data-Decision Intelligence](14-data-decision-intelligence.md)):

1. **Gap identification.** Scanners + market internals surface what most traders miss: OI buildup divergences, max-pain drift, FII/DII flow, breadth extremes. The platform names the gap (e.g., "PE OI building at 24,600 while spot sits below — sticky pin candidate") instead of leaving the trader to notice it.
2. **Regime shifts.** regime_classifier turns tick/feature data into a regime label (trending/range/high-IV/earnings-event). Options structure advice changes with regime — selling premium in a high-IV crush setup vs buying in a calm pre-event drift — and the platform says which regime it thinks it is in, with conviction.
3. **Options structure.** IV rank, smile skew, PCR, GEX-style gamma exposure and strike concentration tell you *where the market is positioned*, not just where it's pointing. Strike selection and strategy hints (the two Phase-2 501 features, per D6) are built on this structure.
4. **Risk awareness.** One risk engine evaluates the whole book: position limits, margin (NRML/MIS context), max-loss per setup, expiry-day behavior. The cost model folds in STT/brokerage/slippage so the displayed P&L is the real P&L.
5. **Cost-aware EV.** Every suggested or evaluated trade carries expected value computed net of costs and measured against historical fills (learning data). A 15-point credit that costs 12 in friction is not a trade; the platform refuses to romanticize it.
6. **Learning loop.** Every signal, vote, and trade is recorded; voter quality is tracked (VoterQualityTracker, MfeMaeCalculator), walkforward evaluation measures what would have worked, and calibration curves keep confidence honest. The edge compounds by editing itself — this is the part no terminal and no script collection provides.

## 5. "Unified platform" — what it means in practice

Six "ones", each a concrete contract (per [Section 05 — System Boundaries](05-system-boundaries.md) and [Section 06 — Proposed Architecture](06-proposed-architecture.md)):

| The one | What it is | What it eliminates |
|---|---|---|
| **One data model** | Shared instruments/symbols/ticks/order records across core, intelligence, execution, learning — not per-module ad-hoc dicts | The "five data conventions" rot of the script-and-sheet era |
| **One execution abstraction** | `core/interfaces` protocols that `DhanTradingAdapter` implements; adapters are swappable without touching the engine | Lock-in to a broker's API shape; makes multi-broker later non-degrading (D8 keeps Dhan first) |
| **One risk engine** | Risk + cost model as a single gate every path (intelligence hint, paper, live) passes through | Risk rules enforced in one place, not duplicated per script |
| **One terminal** | A Svelte frontend (D9) serving watchlists, scanners, chain, strategy hints, positions/risk, logs, session controls — governed by DESIGN.md (D4) | Context-switching between four tools |
| **One plugin system** | Vendored OpenAlgo adaptations implement our protocols (D1); voters/scanners register via registries; nothing hardcodes a vendor module | The tangle of "borrowed code with no boundary" |
| **One intelligence engine** | Deterministic/statistical features → regime → signal/voter conviction → options EV → risk → execution awareness → operator-facing explanation; LLM agents live in the research workspace only (D3, D12) | Black-box vibes in the live path |

## 6. Market anticipation: conditions, not predictions

Per D3, the platform does not claim to predict direction. It computes **conditions**: the current regime, the structure of the option chain, the cost/risk profile of candidate trades, and the historical quality of each signal it emits. "The market will go up" is never an output; "conditions for a short-straddle squeeze are present (IV rank high, OI concentrated ATM, regime range-bound, cost-adjusted EV positive on 35 trades in the journal)" is. Anticipation in this design means being positioned with the structure and risk the conditions warrant — and having the discipline, enforced by the platform's modes and gates, to do nothing when conditions don't warrant it. That is the honest, durable edge the product sells to its single user.

The India-first specifics of who/what/where this operates on are detailed in [Section 04 — India-First Scope](04-india-first-scope.md); how the product makes money over time (private-use framing, prop-style scale) in [Section 16 — Monetization & Business](16-monetization-business.md).
