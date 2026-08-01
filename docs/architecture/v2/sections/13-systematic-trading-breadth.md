# Section 13 — Systematic Trading Breadth

> Quant-Developers-Resources (cybergeekgyan/Quant-Developers-Resources) as a **blind-spot checklist** for the v2 feature map (per [Section 08](08-feature-map.md)): per-capability top resources mapped to our modules, the gaps the list exposes, and what we must not touch.

## What this repo actually is

A ~3,578-star **quant-career and interview link list** — topic outlines, book lists, YouTube playlists, project *descriptions* (~30-60-line READMEs, no source files), and employer lists. There is **no code to absorb** (BRIEF-quant-developers-resources §5). We treat it as a **pointer index**: anything we adopt (Natenberg's strike-selection framework, de Prado's walkforward, GARCH recipes) comes from the original books/papers, acquired legitimately.

**License flags (binding):**
1. The repo itself is **unlicensed** (`license: null`, no LICENSE file) — default copyright = all-rights-reserved. Fine for reading and linking; **never copy its outline content wholesale** into our docs or code.
2. `TextBooks/readme.md` hosts direct PDF links to **copyrighted books** (lib.ysu.am, knowen-production S3, tfal.in, sea-stat.com, archive.org mirrors). Do not download, vendor, or distribute those PDFs. **Buy the books** (Hull, Natenberg, Sinclair, Taleb, de Prado, Jansen).
3. **Nothing Dhan-specific exists in the repo.** The only Indian-market item is the KiteConnect (Zerodha) option-chain project — a broker-API integration pattern, not a Dhan resource. Dhan execution is fully in-house (per [Section 11](11-dhan-integration.md)).

## Capability mapping (repo resource → our module)

| Capability | Top resources in the repo | Our module | Adoption |
|---|---|---|---|
| Market terminal | `Python/readme.md` checklist (returns, covariance/correlation, portfolio risk, VaR, Black-Scholes); Hilpisch pandas/NumPy playlists | `terminal/`, `core/storage/` (DuckDB TS) | Calculation specs + data-layer grounding for terminal panels |
| Scanners | `Technical_Indicators/readme.md` formula catalog (SMA/EMA/MACD, RSI, Stochastic, CCI, Bollinger, ATR, Chaikin, Keltner, ADX, Parabolic SAR, Ichimoku); EMA/Bollinger strategy blueprints | `intelligence/features/` (O(1) indicator engine), `intelligence/scanners/` | Ready-made indicator catalog for scanner definitions (Phase 3) |
| Research | `Econometrics/readme.md` (OLS, ARIMA/Box-Jenkins, ARCH/GARCH, VAR, cointegration, causal inference); portfolio theory (MPT/CAPM/APT) | `research/` workspace (Phase 3) | Outline for the research toolset and outcome studies |
| Signal intelligence | GARCH volatility forecasting; cointegration pairs blueprint (stationarity, z-score); LSTM template (repo's own bias favors gradient boosting for tabular signals) | `intelligence/voters/` (breadth, micro, options_flow, orb, iv_rank), `intelligence/regime/` | Vol/regime feature fodder; LSTM **not** adopted (ML never until proven, per [Section 08](08-feature-map.md)) |
| Options intelligence | **Option Chain Analyser (KiteConnect)** — ATM/ITM/OTM classification, live NSE chain, payoff diagrams, IV surface, expiry selection; Natenberg/Sinclair/Hull/Taleb texts; Black-Scholes/greeks implementation checklist | `options/` (greeks, iv_rank, oi_tracker, quantlib_pricer, strategy_analyzer), `integration/dhan/` (chain via Dhan, not KiteConnect) | The single most relevant item; swap KiteConnect for Dhan's option-chain endpoint |
| Risk | `Risk Management/README.md` — best-structured file: VaR/CVaR/ES, drawdown, Greeks, GARCH/EWMA, stress, scenario analysis, liquidity (bid-ask, slippage, Almgren-Chriss), model validation, backtesting; Python VaR recipes (historical/variance-covariance/Monte-Carlo + Kupiec) | `intelligence/risk/` (risk_engine, cost_model) | Ready curriculum; Phase 3 adds VaR/CVaR/stress |
| Execution | **Nothing Dhan-specific**; nearest analogs: KiteConnect project (broker-integration pattern) and execution-risk theory in `Risk Management/README.md` | `integration/dhan/` adapters, `execution/` engine | Dhan execution is fully in-house; repo only validates the approach |
| Learning loop | de Prado "Advances in Financial Machine Learning" (purged K-fold, combinatorial purged CV, walkforward, backtest-overfitting prevention) | `learning/` (outcome_tracker, voter_quality, calibration, walkforward, mfe_mae, analytics) | This IS our learning-loop methodology |
| Backtesting | ARIMA+GARCH and cointegration strategy blueprints | Phase-4 backtest depth on vectorbt | Port the *strategy rules*; vectorbt knowledge stays in-house |
| India-specific | Only the KiteConnect project; README Indian-companies table as competitive intelligence | — | No NSE historical-data vendors, no Indian F&O data, no SEBI material in the repo — Indian data/API knowledge comes from outside (BRIEF-quant-developers-resources §3) |

## Blind-spot checklist (what the list reveals about us)

| Blind spot | Status | Verdict / action |
|---|---|---|
| **Cost modeling** (brokerage, slippage, STT/charges, market impact) | **Already covered** — `intelligence/risk/cost_model.py` (slippage/spread/brokerage) | Verify STT/exchange-levy line items for index options against current NSE slabs; cost model must appear in every options EV (per [Section 14](14-data-decision-intelligence.md)) |
| **Streaming technical analysis** | **Already covered** — `intelligence/features/feature_engine.py` computes O(1)/tick | Keep the O(1) discipline; the repo's indicator catalog is a spec source, not a runtime need |
| **Execution profiling** (fill quality, realized vs intended slippage per order type / time-of-day) | **MISSING** | Phase-3 addition: record intended vs actual fill in `learning/outcome_tracker.py` execution attempts; produce per-session slippage stats feeding the cost model |
| **Pre-trade risk gates** (limits checked before an order may exist) | **Partially covered** — risk engine's composable filter chain (margin, loss limits, position caps) | Wire the full chain into the order ticket pre-trade summary (MVP, per [Section 08](08-feature-map.md) execution cockpit) |
| Volatility forecasting (GARCH/EWMA) | Partial — regime classifier on coarser bars | GARCH features are Phase-3 voter fodder, not a new engine |
| Liquidity / order-book dynamics (Almgren-Chriss) | Out of scope | Retail lot scale on NSE; slippage model in `cost_model.py` suffices |
| Credit risk (PD/LGD/EAD, Merton) | Out of scope | NSE index options are CCP-cleared; no counterparty exposure (BRIEF-quant-developers-resources §2 Risk) |
| Model-risk curriculum (overfitting, bias-variance, purged CV) | Covered — `learning/walkforward.py` + calibration | Formalize purged-CV protocol in Phase-3 walkforward depth |
| HFT/parallel systems (C++, CUDA, FPGA) | Out of scope | Python shop; latency-critical HFT is not retail-NSE relevant |

## Adopted reading curriculum (acquired legitimately)

| Text (from repo's lists) | Applies to | When |
|---|---|---|
| Natenberg, *Option Volatility and Pricing* | Strike selection, IV, pricing intuition | Phase 2 strategy hints |
| Sinclair, *Volatility Trading* | Volatility regimes, premium selling | Phase 3 |
| Hull, *Options, Futures and Other Derivatives* | Greeks, pricing reference | Phase 2 |
| Taleb, *Dynamic Hedging* | Hedging/risk in volatile regimes | Phase 3 (reference) |
| de Prado, *Advances in Financial Machine Learning* | Walkforward, purged CV — the learning-loop backbone | Phase 3 |
| Jansen, *Machine Learning for Algorithmic Trading* | Feature engineering context | Phase 3 (reference) |
| Hilpisch, *Python for Finance* (+ playlists) | Data layer, backtesting concepts | Phase 2 |

All purchases, never PDF mirrors (license flag above).

## Verdict

The repo is a **checklist, not a dependency**: it validates that our modules map onto a recognized systematic-trading curriculum, exposes exactly two real gaps (execution profiling; pre-trade risk gates in the UI) and confirms Dhan-side work is entirely in-house. Cross-references: [Section 08 — Feature Map](08-feature-map.md), [Section 14 — Data & Decision Intelligence](14-data-decision-intelligence.md) (how features become decisions), [Section 17 — Delivery Roadmap](17-delivery-roadmap.md) (when each gap closes).
