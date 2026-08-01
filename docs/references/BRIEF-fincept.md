# BRIEF: Fincept Terminal — BREADTH Reference (NOT a code source)

**Status:** Research brief · **Date:** 2026-08-01 · **Owner:** ShettyXtreme platform team
**Purpose:** Catalog Fincept's product/analytics breadth to pressure-test the ShettyXtreme feature map.
**Positioning:** Fincept is a **breadth reference ONLY**. AGPL-3.0 + aggressive commercial dual-license — **no code reuse, no porting, no pattern-in-code that shadows structure**. Concepts only.
**Sources read:** `references/upstream/fincept-terminal` and `references/upstream/fincept-fork` (fork = personal mirror of upstream v4.2.0, one commit behind v4.3.0; contents identical for our purposes). Read: README.md, docs/ (GETTING_STARTED, ARCHITECTURE, ALPHA_ARENA, COMMERCIAL_LICENSE), LICENSE, `fincept-qt/scripts/Analytics/README.md`, plus directory listings of all 54 screens, 1,423 scripts, and analytics/options script headers. C++ source trees NOT read in depth (per scope).

---

## 1. What Fincept Is

Fincept Terminal v4: native C++20/Qt6 desktop financial workstation ("Bloomberg-style"), embedded Python 3.11 for analytics, modular monolith. Scale: ~342k lines C++, ~1,423 Python scripts, 54 lazy screens, ~50 services, 13 bounded contexts (Markets, News, Economics, Geopolitics, Trading, Portfolio, Crypto, Derivatives, Predictions, Agents, AI Chat, Workflow, Identity), 16 Indian+global brokers, 40+ MCP tools, in-process pub/sub data plane (DataHub) with SQLite TTL cache. As of June 2026: maintenance throttled to 1 release/month; team moved to private edition + Quantcept (SaaS quant platform).

---

## 2. Product Breadth Catalog + Verdicts

Verdict key: **[inherit]** = adopt as a product/UX pattern · **[adapt]** = useful idea to adapt · **[skip]** = not relevant to an Indian options-first platform.

### 2.1 Terminal views & workspace
| Capability | What Fincept does | Verdict |
|---|---|---|
| Dashboard | 13 widget types (quotes, watchlist, news, portfolio summary, today P&L, risk metrics, screener, sector heatmap, top movers, trade tape, economic calendar, quick trade, order-book mini) | **[inherit]** Our market terminal dashboard should mirror this widget-suite shape (esp. TodayP&L, risk metrics, sector heatmap, quick trade) |
| Docking workspace | ADS multi-window/multi-panel layouts, lazy screen router, stateful screens, F-key command bar, command palette | **[inherit]** Multi-panel docking + command palette is the right terminal UX pattern |
| Markets screen | Multi-panel quote editor (user-built panels), watchlists, sectors | **[inherit]** Scanners/market terminal feature area |
| Watchlist | Dedicated watchlist screen + dashboard widget | **[inherit]** Core terminal component |
| Launchpad/onboarding | First-run tour, onboarding screens | **[adapt]** Good for our learning pillar |
| Action Center | Pending orders badge + panel, order confirm dialogs | **[inherit]** Execution UX (pre-trade check / pending orders) |
| Notes / Docs / Forum | In-app notes, built-in docs screen, community forum | **[adapt]** Learning pillar; forum low priority |

### 2.2 Analytics categories (80+ modules, CFA-curriculum-aligned, Python)
| Capability | What Fincept does | Verdict |
|---|---|---|
| Equity investment | DCF, dividend models, multiples valuation, residual income, private valuation, fundamental analysis (DuPont), industry analysis (Porter), forecasting, index/market-efficiency/market-structure | **[adapt]** Research pillar — DCF + multiples is standard; useful as checklist of what "research" must cover for Indian equities |
| Portfolio management | Returns/risk/attribution, optimization (PyPortfolioOpt, RiskFolioLib, skfolio), VaR/CVaR/stress, alpha/tracking error, IPS/planning, ETF analytics, behavioral finance | **[inherit]** Risk + portfolio feature area — VaR/CVaR, efficient-frontier, attribution concepts directly relevant |
| Financial statement analysis | Balance sheet, income, cash flow, earnings quality/accruals, asset/inventory/tax/compensation, bank & multinational analysis | **[adapt]** Research pillar depth option; heavy for v1 |
| Quantitative methods | CFA quant modules, rate calculations | **[skip]** Academic; low product value for us |
| Technical analysis | Momentum indicators, chart patterns; separate `scripts/technicals/` with trend/volatility/volume/momentum/others indicators | **[inherit]** Signals pillar — indicator taxonomy (trend/vol/volume/momentum) is a good checklist |
| ML for trading | Factor discovery, HFT, RL trading, forecasting wrappers (gluonts, pmdarima, functime, statsmodels), QuantLib suite (18 modules) | **[skip]** Science-project breadth; SaaS QuantLab dependency; not core to options-first MVP |
| Backtesting | 4 engines (LEAN, VectorBT, Backtesting.py, FastTrade) + strategy libs | **[adapt]** Signals/learning — one solid engine beats four wrappers; VectorBT-style vectorized backtests are the right concept |

### 2.3 Research workflows
| Capability | What Fincept does | Verdict |
|---|---|---|
| Equity research screen | 9 tabs: overview, financials, valuation, technicals, peers, sentiment, news, analysis | **[inherit]** Research pillar — this tab architecture (overview → financials → valuation → technicals → peers → sentiment) is exactly the right research-desk layout to adapt |
| Report builder | Document canvas with component toolbar, properties panel | **[adapt]** Research output/export; nice-to-have |
| Alternative data | Adanos market sentiment overlay (Reddit/X/news/Polymarket cross-source snapshots), web-scraper widget | **[adapt]** Signals pillar — social/sentiment aggregation concept worth one view, low priority |
| M&A analytics screen | Merger/valuation/fairness/deals/industry/startup panels | **[skip]** Not Indian-options-relevant |
| Alt investments | Real estate, hedge funds, private capital, digital assets analytics | **[skip]** |
| Excel / Code editor screens | Spreadsheet widget, embedded code editor with library | **[skip]** Desktop-app nostalgia; web app doesn't need |

### 2.4 Data sources
| Capability | What Fincept does | Verdict |
|---|---|---|
| 100+ connectors | Yahoo, FRED, IMF, World Bank, DBnomics, OECD, ECB, Eurostat, Polygon, Kraken, AkShare, gov APIs, RSS; connector registry with connection config/test UI, import/export connections | **[adapt]** We need a **connector registry pattern** (add/test/enable data source) but only for India-relevant sources: NSE/BSE, options chains, F&O, MF, economic calendar; the registry UI concept is worth inheriting |
| Economics screen | 30+ provider panels (FRED, IMF, World Bank, ECB, OECD, CFTC, TradingEconomics, etc.) + economic calendar | **[skip]** Global-macro breadth; keep only an India economic calendar |
| Alternative data, open banking, NoSQL/relational/time-series DB connectors, cloud storage, search warehouse | Enterprise data-fanaticism | **[skip]** |

### 2.5 Trading & execution
| Capability | What Fincept does | Verdict |
|---|---|---|
| 16 broker integrations | Zerodha, Angel One, Upstox, Fyers, Dhan, Groww, Kotak, IIFL, 5paisa, AliceBlue, Shoonya, Motilal, IBKR, Alpaca, Tradier, Saxo; canonical Instrument model + SymbolResolver; BrokerEnumMap data-table mapping | **[inherit]** Execution pillar — the **canonical instrument model + typed enum maps + adapter-per-broker** pattern is exactly right; we already target Dhan (and dhanhq-py is in our references) |
| Unified trading engine | UnifiedTrading live routing, PaperTrading sim, OrderMatcher with SL/TP triggers | **[inherit]** Execution + paper-trading pattern; SL/TP trigger engine concept relevant to options strategies |
| Order UX | Basket orders, broadcast orders, account management dialogs, order confirm dialog, multi-account | **[adapt]** Basket/broadcast ordering is a good options-flow concept (multi-leg) |
| Trade viz | Trade visualization screen | **[adapt]** Post-trade review for execution pillar |
| Alpha Arena | LLM-agent tick-by-tick competition on crypto perps with replay/audit, HITL gates, risk engine, kill switches | **[adapt]** Interesting for learning/simulated competition later; crypto-perp focus not relevant — but the **HITL approval gate + replayable audit log + auto kill-switch (drawdown) concepts** are worth inheriting for our paper-trading risk |

### 2.6 News & intelligence
| Capability | What Fincept does | Verdict |
|---|---|---|
| News | Feed, RSS manager, ticker strip, clustering/dedup/deviation monitors | **[inherit]** Market terminal — news ticker + category feed is expected; RSS manager concept fine |
| Geopolitics / Maritime / Relationship map | HDX/ACLED conflict data, vessel tracking, entity relationship graphs | **[skip]** Global breadth, not Indian-options-relevant |
| Polymarket / Predictions | Prediction-market browse/activity, price widgets | **[skip]** |

### 2.7 AI & automation
| Capability | What Fincept does | Verdict |
|---|---|---|
| 37 AI agents | Trader/investor personas (Buffett, Graham, Lynch...), economic, geopolitical; multi-provider LLM; local LLM | **[adapt]** Learning pillar — persona-based research agents are a fun, differentiated learning feature; not core |
| AI Quant Lab | Factor discovery, HFT, RL, ML training UI | **[skip]** SaaS-dependent, science-project |
| Node editor | Visual DAG automation pipelines + MCP tool integration, deploy dialogs | **[adapt]** Strategy-building visual workflows could map to options strategy builder later; not v1 |
| MCP servers screen | Manage external MCP servers | **[adapt]** We already use MCP tooling; exposing it to users is optional |

---

## 3. Options / Derivatives Analytics — Pattern-Inheritance Candidates (concept-level only)

This is the highest-value section for ShettyXtreme. Fincept's FNO screen + options scripts are themselves concept-ported from OpenAlgo (which we also have in `references/upstream/openalgo` — worth cross-referencing).

### 3.1 FNO workstation (screen-level concepts)
- **Option chain table** with per-strike rows, CE/PE columns, configurable fields — our chain view baseline.
- **Multi-leg strategy builder** (BuilderSubTab): leg editor table (strike/type/side/qty/premium/IV), template picker panel, strategy templates.
- **Payoff strip + payoff chart widgets**: instant payoff curve + net position Greeks per strategy — **[inherit]** core options-intelligence UX.
- **OI analytics**: OI buildup table, multi-strike OI charts, intraday OI chart, max-pain chart, multi-straddle subtab — **[inherit]** India's OI-centric culture makes this table-stakes.
- **FII/DII flow chart** (institutional flow) — **[inherit]** uniquely-Indian signal; strong differentiator.
- **Option screener subtab** — **[inherit]** scanners feature area.
- **Order confirm dialog with margin/risk summary before placement** — **[inherit]** execution safety.

### 3.2 Options analytics scripts (concept catalog; implementation is Black-76/numpy+scipy)
- **GEX calculator** (`gex_calculator.py`): per-strike Gamma Exposure = gamma × OI × lot size, net GEX = call GEX − put GEX; Black-76 (options on forward — correct model choice for Indian F&O) — **[inherit]** dealer-hedging signal, differentiator.
- **IV surface** (`iv_surface.py`): 3D IV across strikes × expiries, OTM convention (CE IV above ATM, PE IV below) + dedicated SurfaceAnalytics screen (3D widget, line/table views, CSV import) — **[inherit]** IV-surface 3D view is a "wow" feature for options intelligence; the OTM-convention detail matters.
- **IV smile** (`iv_smile.py`): per-expiry smile curve — **[inherit]**.
- **OI tracker** (`oi_tracker.py`): OI flow over time — **[inherit]**.
- **Straddle simulator** (`straddle_simulator.py`): strategy scenarios — **[adapt]**.
- **Strategy chart** (`strategy_chart.py`): multi-leg payoff + position-weighted Greeks at spot; leg model {strike, CE/PE/FUT, buy/sell, qty, premium, IV} — **[inherit]** the leg-model vocabulary (sign-by-side, lot-size scaling, premium-driven) is the exact concept set our strategy analyzer needs.
- **Derivatives module suite**: Black-Scholes/binomial pricing + Greeks, forward commitments (forwards/futures/swaps), put-call parity & arbitrage — **[inherit]** standard math concepts; we'd implement in Python/our stack.
- **Greeks tooling**: Black-76 greeks, per-strike tables in chain — **[inherit]** greeks columns + greeks-sorted screens in our options intelligence.

### 3.3 Notes on their math conventions worth inheriting (conceptually)
- Black-76 over Black-Scholes for F&O (spot treated as forward) — correct for Indian index/futures options.
- OTM-side IV convention for surfaces (avoids noisy ATM/ITM quotes).
- Lot-size-aware payoff scaling (Indian contracts are lot-based, not per-share).
- Sign-by-side leg aggregation (buy +, sell −) for net greeks.
- GEX with OI×lot_size weighting — dealer-gamma framing.

---

## 4. What NOT to Copy

1. **Code, structure, or UX implementation — AGPL-3.0.** The LICENSE file confirms AGPL-3.0-or-later, and the README adds a **commercial dual-license with aggressive enforcement**: business use (including startups at any stage, fork-and-replace of their APIs, SaaS, consulting deliverables) requires a paid commercial license; liquidated damages start at USD 50k/year; joint-and-several liability for third-party builders; active monitoring of public repos; governing law India/Delhi. We are a commercial project → **zero code, zero file structure, zero copy-adaptation of implementation**. Also note their options scripts are themselves derived from OpenAlgo (AGPL) — do not treat Fincept as a clean-room source for those.
2. **C++20 / Qt6 stack.** Native desktop monolith, ~342k lines, ADS docking, embedded Python venvs (two numpy variants), QCoro coroutines. We are a web/cloud platform; nothing to take.
3. **SaaS QuantLab dependency.** AI Quant Lab / Quantcept / university licensing ($799/mo) — their commercial layer, not open source in spirit; the ML breadth is a science project, not an options-edge.
4. **Global-market breadth.** Economics screen (30+ provider panels), geopolitics/maritime/relationship-map, prediction markets, crypto center/trading, alt investments, forex/commodities widgets, M&A screen. We are Indian markets, options-first — this breadth is noise for us.
5. **Their async/architecture debt.** Modular-monolith bounded contexts, DataHub pub/sub, 40+ singletons, screen-unload problems — the *patterns* (contexts, pub/sub data plane, connector registry) are fine to imitate conceptually; the specific implementation is off-limits and over-engineered for our scale.

---

## 5. License Confirmation & Coupling Risk

- **License:** AGPL-3.0 (GNU Affero GPL v3, "or later") + Fincept Commercial License (dual licensing). Trademarks "Fincept"/"Fincept Terminal" reserved. Confirmed in `LICENSE` (AGPL-3.0 header) and README License section.
- **Coupling risk: ZERO.** ShettyXtreme adopts concepts only (feature lists, screen-taxonomy, math-model choices, UX patterns) — no code, no algorithms copied from their implementation, no file structure, no dependency. Our stack (web platform, Python services, Dhan execution via dhanhq-py) shares nothing with C++20/Qt6. Any math (Black-76, GEX, IV surface) is textbook/public-knowledge (and independently available via our OpenAlgo reference) — implement from formulas, not from their files.
- **Guardrail for the team:** never open a Fincept source file while writing a feature that mirrors its catalog; write from this brief + our own specs. If a reviewer suspects structural copying, it comes from this document's category table — which is a feature checklist, not an implementation.

## Appendix: Quick feature-area mapping (ShettyXtreme pillars)
- Market terminal ← Fincept: dashboard widgets, markets panels, watchlist, news ticker, sector heatmap, F-key/command palette UX.
- Scanners ← Fincept: universe scanner, option chain screener, OI buildup tables, top movers.
- Research ← Fincept: equity research tab architecture, DCF/multiples checklist, report builder, sentiment aggregation.
- Signals ← Fincept: technical indicator taxonomy, GEX, FII/DII, OI flow, max pain, IV smile.
- Options intelligence ← Fincept: chain + multi-leg builder + payoff/greeks strip + templates, IV surface 3D, straddle simulator, options math suite (Black-76 conventions).
- Execution ← Fincept: canonical instrument model, broker adapter + enum maps, SL/TP order matcher, basket/broadcast orders, order-confirm risk dialog, paper-trading engine, action center.
- Risk ← Fincept: VaR/CVaR/stress, portfolio optimization, risk metrics widget, drawdown kill-switch, HITL approval gates.
- Learning ← Fincept: launchpad onboarding, persona research agents, docs screen, paper competition w/ replay (Alpha Arena concept), forum (optional).
