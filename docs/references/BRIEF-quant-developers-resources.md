# BRIEF: quant-developers-resources (cybergeekgyan/Quant-Developers-Resources)

Source: `D:\ShettyXtreme\references\quant-developers-resources` (shallow clone, HEAD 2772004, branch main).
GitHub: https://github.com/cybergeekgyan/Quant-Developers-Resources — ~3,578 stars, actively pushed (Jul 2026).
Audience note: this repo is a **quant-career / interview-preparation link list** (topic outlines + links + book
lists), not a software library. There is no code to absorb. Value for ShettyXtreme = curated pointers (books,
courses, project ideas, learning roadmaps) that we map to our Python/NSE/BSE stack below.

---

## 1. How the repo is organized

Root `README.md` (465 lines) is the hub: hiring-process stages, "21 most important quant interview topics,"
math/stat/programming/data-stack checklists, book lists (interview, technical rounds, quant traders), 21 YouTube
playlists (Hilpisch, Ernie Chan, IIT/IIM courses, Two Sigma), Indian companies hiring quants, global prop-shop and
hedge-fund employer lists, and 20 fellowship programs.

Then ~36 topic directories, mostly each containing a single `readme.md` outline plus links:

| Group | Directories |
|---|---|
| Math foundations | Mathematics/ (subdirs: Calculus, Linear Algebra, Numerical Methods, Optimization, Probability Theory, Statistics, Stochastic Calculus), Game Theory/, Optimization Theory/ |
| Programming | Python/, C++/, R/, Matlab/, PyTorch/ (EMPTY), SQL/, Statsmodels/ (EMPTY) |
| Finance theory | Financial Theory/ (Portfolio Theory/ subdir), Econometrics/, Risk Management/, Credit Risk Modeling/ (+Projects/), Technical_Indicators/ |
| AI/ML | Artificial Intelligence/ (Machine Learning/, Deep Learning/ with 9 numbered subdirs, LLMs/, NLP/, RAG & Advanced RAG/), Reinforcement Learning/ |
| Systems/HPC (low relevance) | CUDA/, FPGA/, High Performance Computing/, Parallel Computing/, Quantum Computing/, Computer Architecture/, Digital Logic/, Operating Systems/, Computer Networks/, Distributed Systems/, Signal Processing/ (EMPTY) |
| Interview/career | BrainTeasers_Puzzles/, Poker Theory/, ResumeTemplates/, QuantCompaniesList.md (400+ firms), QuantCompetition_Fellowships.md (70+ programs) |
| Books | TextBooks/ (curated reading lists, some with direct PDF links — see license flags in section 4) |
| Example projects | Projects/ — 8 *described* (not vendored) projects: ARIMA+GARCH strategy, EMA+Bollinger algo, Bollinger strategy, cointegration pairs trading, Black-Scholes PDE solver, LSTM forecasting, Option Chain Analyser (KiteConnect), sentiment strategy |

Most sections are outlines/checklists; several tables have **empty Link columns** (placeholders). Many links are
LinkedIn short-links (lnkd.in), which rot over time. The Deep Learning and Reinforcement Learning dirs are generic
AI roadmaps (no finance tie-in) with only a few external links.

---

## 2. Checklist cross-map to ShettyXtreme capability areas

### Market terminal
- `Python/readme.md` — Python-for-finance checklist (returns, covariance/correlation, portfolio risk, VaR,
  Black-Scholes implementations, Vasicek) — directly reusable as a feature/calculation spec for terminal panels.
- README YouTube list #1-2 (pandas/NumPy quant analysis; Yves Hilpisch "Python for Quant Finance") — best free video
  grounding for our data layer and research workflows.
- `Econometrics/readme.md` tech-stack block (pandas, statsmodels.tsa, scikit-learn, plotly, SQLite/PostgreSQL) —
  matches our terminal stack; confirms tools of record and suggests db choices.

### Scanners
- `Technical_Indicators/readme.md` — tables of trend/momentum/volatility indicators with formulas (SMA/EMA/MACD,
  RSI, Stochastic, CCI, Williams %R, Bollinger, ATR, Chaikin, Keltner, ADX, Parabolic SAR, Ichimoku) — ready-made
  catalog for scanner definitions.
- `Projects/Bollinger Bands Trading Strategy` and `Automated Algo Trading Strategy using EMA and Bollinger Bands` —
  concrete strategy templates to reimplement with vectorbt.
- `Econometrics/readme.md` — moving-average family (SMA/WMA/EMA/HMA) and forecasting methods — useful for scanner
  signal smoothing and cross-timeframe alignment.

### Research (fundamental/statistical)
- `Econometrics/readme.md` — full outline: OLS assumptions and violations, multicollinearity, heteroskedasticity,
  ARIMA/Box-Jenkins, ARCH/GARCH, VAR, cointegration/error correction, panel data, causal inference (DiD, PSM) —
  maps directly to our research workflow and outcome studies.
- `TextBooks/readme.md` ML-in-finance list: Lopez de Prado "Advances in Financial Machine Learning" (walkforward,
  purged CV — the backbone of our learning loop!), Stefan Jansen "Machine Learning for Algorithmic Trading",
  Hilpisch "Python for Finance".
- `Financial Theory/Portfolio Theory/readme.md` — MPT/CAPM/APT/performance-measures checklist — baseline math for
  research notes and risk-adjusted return reporting.
- `Artificial Intelligence/Deep Learning/readme.md` — 50-project phased roadmap (PyTorch); only the MLOps/RAG
  phases touch our concerns; most is CV/LLM generic.

### Signals (conviction-based voters)
- `Econometrics/readme.md` — GARCH volatility forecasting, volatility clustering, regime methods — strong feature
  fodder for conviction voters (vol/regime features alongside technicals).
- `Projects/CoIntegration-Based Pairs Trading Strategy` — pairs/mean-reversion signal template (stationarity tests,
  z-score entry logic).
- `Projects/LSTM based Time-Series Forecasting for Algorithmic Trading` — ML signal template; note the repo's own
  book bias (de Prado, Jansen) favors gradient boosting/XGBoost over LSTMs for tabular signal work.
- `Artificial Intelligence/Machine Learning/readme.md` — thin (one link to tensortonic.com practice platform); low
  value beyond link.

### Options intelligence (IV/OI/PCR, strike selection)
- `Projects/Option Chain Analyser and Payoff Visualizer Using Python/readme.md` — **the single most relevant item
  in the repo**: ATM/ITM/OTM classification, live NSE option chain via KiteConnect, payoff diagrams, IV surface,
  theta/IV 3D visualization, expiry selection, backtest harness ideas — directly parallels our options-intelligence
  module (we would swap KiteConnect for Dhan's option-chain API).
- `TextBooks/readme.md` trader books: Natenberg "Option Volatility and Pricing," Sinclair "Volatility Trading,"
  Hull "Options, Futures and Other Derivatives," Taleb "Dynamic Hedging" — the canonical IV/greeks/strike-selection
  reading for our strikes and PCR logic.
- `Python/readme.md` — Black-Scholes + Greeks + binomial tree + Monte Carlo implementation checklist — specs for
  our pricing utilities and IV computation.
- `Projects/Deriving & Numerically Solving the Black-Scholes PDE using Python` — finite-difference template if we
  move beyond closed-form pricing.

### Risk
- `Risk Management/README.md` — the best-structured file in the repo: VaR/CVaR/ES, drawdown, Greeks, GARCH/EWMA,
  stochastic volatility, stress testing, scenario analysis, liquidity risk (bid-ask, slippage, Almgren-Chriss),
  model risk/validation, backtesting — a ready curriculum for our risk module.
- `Python/readme.md` — VaR historical/variance-covariance/Monte-Carlo + Kupiec test + traffic-light backtest +
  Expected Shortfall — implementation recipes.
- `Credit Risk Modeling/README.md` (+Projects/) — PD/LGD/EAD outlines, Merton model, survival analysis — only
  relevant if we ever add counterparty/credit scoring; low priority for an NSE options platform.

### Execution (Dhan broker)
- **Nothing Dhan-specific exists in the repo.** Nearest analogs: the KiteConnect (Zerodha) option-chain project
  (shows the broker-API integration pattern) and README playlists #5/#6/#7 ("How to Code a Trading Bot in Python,"
  "Algorithmic Trading Python 2023," full-course) for order-flow/execution concepts.
- `Risk Management/README.md` execution-risk section (slippage modeling, market impact, order book dynamics) —
  theory relevant to order sizing and fill assumptions on NSE.
- Verdict: treat Dhan execution as fully in-house; the repo only validates the approach, adds no Dhan/Upstox/
  5paisa/Zerodha-beyond-KiteConnect material.

### Learning loop (outcome tracking, walkforward)
- `TextBooks/readme.md` — de Prado "Advances in Financial Machine Learning": purged K-fold, combinatorial purged CV,
  walkforward, backtest-overfitting prevention — this IS our learning-loop methodology and outcome-tracking design.
- `Econometrics/readme.md` — time-series forecast evaluation (naive baselines, SMA/EMA families, forecast metrics) —
  baseline comparisons for outcome tracking.
- `Risk Management/README.md` — backtesting and model-validation sections (cross-validation, overfitting,
  bias-variance) — protocol for our outcome DB and walkforward runs.

### Backtesting (vectorbt)
- `Projects/ARIMA + GARCH Trading Strategy...` and `Projects/CoIntegration-Based Pairs Trading Strategy` — strategy
  + backtest blueprints (entry/exit rules, volatility filters) to port to vectorbt.
- `Econometrics/readme.md` — GARCH/VAR/cointegration methods that our backtest feature set should support.
- No vectorbt-specific material exists — vectorbt knowledge stays in-house (vectorbt docs are the reference).

---

## 3. Indian-market-specific resources (explicit flags)

- `Projects/Option Chain Analyser and Payoff Visualizer Using Python/` — **the only NSE-specific resource**:
  KiteConnect (Zerodha) live NSE option-chain fetch, ATM/ITM/OTM strike classification, payoff diagrams, IV surface,
  theta/IV viz — directly applicable; adapt KiteConnect calls to Dhan's option-chain endpoint.
- README section "Companies that Hire Quant Developers and Software Engineers in India" — AlgoBulls, AlphaGrep,
  Qnance, Edelweiss, Estee Advisors, SMC Global, NK Securities, etc. — useful as competitive/product intelligence
  (who builds similar Indian-market tooling), not for code.
- `QuantCompaniesList.md` — 400+ firms including many India-based (DE Shaw India, Algo Bulls, Sigtech India, Sixth
  Sense Securities, Pinsecai) — same competitive-intelligence use.
- README course list #11/#12/#16/#19 — IIT Kanpur/Bombay/Guwahati quant-finance, probability & stochastics courses —
  India-authored, free, high-quality theory training.
- `R/readme.md` — financial-econometrics stack mentions Yahoo Finance API — the only (weak) pointer to a data
  source that works for NSE tickers (yfinance).
- Absent: no NSE/BSE historical-data vendors (NSEpy, bhavcopy tooling), no Dhan/Upstox/5paisa broker API docs, no
  Indian options-data (F&O bhavcopy) resources, no SEBI regulatory material. **Indian data/API knowledge must come
  from outside this repo.**

---

## 4. NOT worth it for us (skip list)

- **US-only / career-centric**: QuantCompaniesList.md, QuantCompetition_Fellowships.md, README employer lists,
  ResumeTemplates/, BrainTeasers_Puzzles/, Poker Theory/, all "interview" book lists (Heard on the Street, Quant Job
  Interview Questions, etc.) — job-search material with zero product value.
- **Wrong stack / HFT systems**: C++/, FPGA/, CUDA/, Quantum Computing/, High Performance Computing/, Parallel
  Computing/, Computer Architecture/, Digital Logic/, Operating Systems/, Computer Networks/, Distributed Systems/,
  Matlab/ — we are a Python shop; latency-critical HFT is out of scope for a retail-NSE platform.
- **License-problematic**: `TextBooks/readme.md` hosts direct PDF links to copyrighted books (lib.ysu.am,
  knowen-production S3, tfal.in, sea-stat.com, archive.org mirrors) — do not distribute or vendor these; buy the
  books (Hull, Natenberg, Sinclair, de Prado, Jansen).
- **Stale/empty**: `Statsmodels/`, `Signal Processing/`, `PyTorch/` readmes are empty; many table Link columns are
  blank; lnkd.in links rot; the Deep Learning roadmap is a generic non-finance project list (CV/healthcare phases
  are irrelevant); QuantCompetition_Fellowships.md is mostly US prop-shop programs.
- **Low quality signals**: README Indian-companies table has missing CTC/website fields; the 21-playlist list
  mixes quality freely; AI/Deep Learning dirs contain no finance-specific content.

---

## 5. Repo license + nature

- **No license.** GitHub API reports `license: null` and the clone has no LICENSE/COPYING file — under default
  copyright law the README/outline content is all-rights-reserved. Fine for *reading and linking*; do not copy
  content wholesale into our docs.
- **Nature**: a link/outline list — there is **no code to absorb**. Even `Projects/` contains only descriptions
  (each a ~30-60-line README), not source files. The KiteConnect option-chain item is also description-only.
- Practically: treat it as a **pointer index**. Anything we adopt (Natenberg's strike-selection framework, de
  Prado's walkforward, GARCH recipes) comes from the original books/papers, which we acquire legitimately.

---

## Top-10 resources for ShettyXtreme (in priority order)

1. Option Chain Analyser project (KiteConnect NSE option chain, ATM/ITM/OTM, IV surface) — direct template for the options-intelligence module.
2. TextBooks: Natenberg "Option Volatility and Pricing" + Sinclair "Volatility Trading" — the IV/greeks/strike-selection canon.
3. TextBooks: de Prado "Advances in Financial Machine Learning" — purged CV/walkforward = our learning-loop methodology.
4. Risk Management/README.md — VaR/CVaR/ES, Greeks, GARCH, stress/backtesting curriculum for the risk module.
5. Python/readme.md — Black-Scholes, Greeks, binomial tree, VaR (3 methods + Kupiec backtest) implementation checklist.
6. Econometrics/readme.md — ARIMA/GARCH/VAR/cointegration + forecast evaluation for research and scanner features.
7. Technical_Indicators/readme.md — formula catalog (RSI, MACD, Bollinger, ATR, ADX, Keltner, Ichimoku) for scanners.
8. Projects: ARIMA+GARCH and Cointegration pairs-trading blueprints — port to vectorbt for backtesting.
9. README YouTube list: Hilpisch "Python for Quant Finance" + pandas/NumPy quant-analysis playlists — free training for the data layer.
10. IIT Kanpur/Bombay/Guwahati quant-finance courses (README list) — free India-authored theory for the research team.
