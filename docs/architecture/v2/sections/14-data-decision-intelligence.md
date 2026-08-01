# Section 14 — Data & Decision Intelligence

> The practical intelligence architecture: how the platform identifies gaps and setups, prices them in options terms, checks risk, and explains itself to the operator. **No magical AI** — live signal generation is deterministic/statistical with measurable conviction; LLM agents live in the research layer only (per D3). The chain is: **feature engine → regime → signal/conviction → options EV → risk → operator-facing explanation**.

## The decision chain

| Stage | Input | Output | Module |
|---|---|---|---|
| 1. Features | Ticks, bars, OI, IV (streaming) | O(1) numeric features | `intelligence/features/feature_engine.py` |
| 2. Regime | Coarser bars (5m+) | Volatility/trend regime state | `intelligence/regime/regime_classifier.py` |
| 3. Signal | Features + regime | Direction, conviction, D/P/G, NEUTRAL | `intelligence/signals/signal_engine.py` + voters |
| 4. Options EV | Signal + chain + cost model | Per-strike expected value, side/strike recommendation | `options/` + `intelligence/risk/cost_model.py` |
| 5. Risk | EV candidate + portfolio | Margin, loss limits, position caps (go / no-go) | `intelligence/risk/risk_engine.py` |
| 6. Explanation | All stages | Conviction score, disagreement, participation, per-voter rationale | Terminal surfaces (per [Section 15](15-design-system-terminal-ux.md)) |

## 1. Market gap identification

| Mechanism | Inputs | Output | Module |
|---|---|---|---|
| Gap scanner | Overnight vs current price, open gaps | Gap-up/down events with size | `intelligence/scanners/gap_scanner.py` |
| Opportunity clusters | Scanner hits grouped by sector/theme | Cluster of related setup candidates | `intelligence/scanners/` |
| Unusual activity | Volume z-score, OI spike vs time-of-day baseline | Anomaly flags feeding `options_flow_voter` | `intelligence/voters/options_flow_voter.py` |

Unusual activity is always judged **relative to time-of-day baseline** — raw OI/volume deltas at 09:30 are normal; the same delta at 14:00 is information (v1's OI time-of-day bias was a fixed bug, not a feature).

## 2. Directional setups

The signal engine aggregates **conviction voters** (breadth, micro, options_flow, orb, iv_rank) into a **D/P/G** output — Direction / Participation / Grouping, the v1 signal vocabulary re-implemented cleanly:

- **Direction** = sign of the participation- and disagreement-adjusted score: `sign(directional_score × participation × (1 − disagreement))` (de-inverted shadow-DPG logic, `intelligence/voters/shadow/shadow_dpg_voter.py`).
- **Participation** = share of eligible voters that produced usable votes (data completeness). Dead or data-starved voters never dilute conviction (v1 fix).
- **Grouping** = how the active voters cluster into a stance — unanimous, split, or contested.

When voters disagree, the engine returns an explicit **NEUTRAL** state with near-zero conviction — never a forced UP/DOWN (v1 bug: forced bearish tie-break; fixed). The execution engine refuses to build orders from NEUTRAL signals (`execution/execution_engine.py`).

## 3. Volatility regimes

The regime classifier runs on **coarser bars** (5m+), never 1-minute noise — **no Markov/HMM state inference on 1m noise**, per the pack's corrected facts and [Section 05](05-system-boundaries.md). Regimes are smoothed, explainable states:

| Regime | Typical features | Consequence |
|---|---|---|
| Low-vol drift | ATR ratio low, realized vol percentile low, IV>HV | Premium-selling territory if IV rank also high |
| High-vol expansion | Realized vol spike, wide ATR, gap activity | Reduce size; directional-only with high participation |
| Trending | ADX high, VWAP drift consistent | Directional structures favored |
| Choppy | ADX low, mean-reversion in features | Neutral structures or stand aside |

HMM/ML regime models are **never until proven** (per [Section 08](08-feature-map.md)) — v1's HMM voter was removed as a dead voter.

## 4. Options selling vs buying conditions

The platform never assumes risk-neutral pricing. Strike/side selection uses **signal-drift EV**: expected payoff from the signal's direction and drift, net of the full cost model (slippage, spread, brokerage, STT) — explicitly **NOT risk-neutral GBM** (v1's noise-optimized strike selection was a top-10 bug; corrected).

| Condition | Sell premium when | Buy options when |
|---|---|---|
| IV rank | High (e.g. > 70th percentile) | Low (< 30th percentile) |
| IV percentile / IV-HV spread | IV above realized vol (fat premium) | IV below realized vol (cheap) |
| PCR (contrarian) | Extreme one-sided put OI → contrarian premium side | PCR extreme + regime shift → cheap protective/decisive side |
| OI buildup | Time-of-day-normalized buildup away from extremes | Time-of-day-normalized buildup confirming direction |
| Signal | NEUTRAL/low participation (no edge to pay up for) | High conviction + high participation + trending regime |

Cost model is **in every EV** — a strike whose gross premium looks attractive but nets negative after slippage/spread/brokerage is shown red, not recommended.

## 5. Neutral vs directional structure preference

| Conviction | Participation | Regime | Structure preference |
|---|---|---|---|
| High | High | Trending | Directional (per signal side) |
| High | Low | Any | Stand aside — data-incomplete signal |
| NEUTRAL | Any | High-vol, high IV rank | Neutral premium-selling structure (straddle/strangle window) |
| NEUTRAL | Any | Low-vol, low IV rank | Stand aside — no edge either way |

The strategy assistant surfaces this preference in the hints panel: direction, structure class, and the reason in plain terms (per [Section 08](08-feature-map.md) options strategy assistant).

## 6. Intraday context

- **ORB**: opening-range breakout voter (`intelligence/voters/orb_voter.py`) — the first 15-minute range anchors intraday bias.
- **Time-bucketed OI**: `options/oi_tracker.py` normalizes OI by session phase; buildup/deletion is read per bucket, not across the day.
- Session phases (pre-open / continuous / close) and weekly-expiry behavior (09:15–15:30 IST) gate which features are trusted at which time (per [Section 04](04-india-first-scope.md)).

## 7. Historical + live combination

The same pipeline runs for both: features → regime → signal → EV → risk. Historical mode adds **point-in-time discipline** (as-of/filing-date filtering, no lookahead) and **fail-loud data** (infrastructure failures raise; only genuine "no data" returns empty — patterns per BRIEF-ai-hedge-fund §2). Walkforward and outcome studies feed back into feature weights and voter quality; live mode additionally consumes the current chain and instruments.

## 8. Operator-facing explanation (explainability surfaces)

Every signal the terminal shows carries four things:

1. **Conviction score** — 0..1, participation-normalized.
2. **Disagreement indicator** — how far voters split (0 = unanimous, 1 = fully contested).
3. **Participation** — share of eligible voters with usable data.
4. **Why each voter voted** — per-voter rationale: feature values in, threshold hit, vote direction/weight (e.g. "orb_voter: price above 15m range high, weight 0.2").

The options EV line itemizes: premium, expected drift payoff, slippage, spread, brokerage, STT, net EV per lot; the risk line states margin, max loss, and limit consumption. The drill-down workflow in [Section 15](15-design-system-terminal-ux.md) exposes exactly these surfaces.

## 9. Learning loop (feedback)

- `learning/outcome_tracker.py` labels signals and execution attempts with realized outcomes (immutable).
- `learning/voter_quality.py` tracks per-voter quality; voters whose tracked quality degrades are marked **CONSUMED** and their weight decays — the dead-voter problem cannot recur silently.
- `learning/calibration.py` recalibrates confidence curves against realized frequencies.
- `learning/walkforward.py` re-validates the whole pipeline on rolling windows (purged-CV protocol, per [Section 13](13-systematic-trading-breadth.md)).
- The loop is honest-by-construction: the backtest path is the live path (per BRIEF-ai-hedge-fund §2), so evaluation is never a separate simulator.

Cross-references: [Section 05 — System Boundaries](05-system-boundaries.md) (layer imports), [Section 08 — Feature Map](08-feature-map.md) (phasing of each stage), [Section 12 — AI & Agentic References](12-ai-agentic-references.md) (research layer boundary per D3), [Section 13 — Systematic Trading Breadth](13-systematic-trading-breadth.md) (methodology curriculum), [Section 15 — Design System & Terminal UX](15-design-system-terminal-ux.md) (how the explanation surfaces render).
