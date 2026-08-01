# BRIEF — virattt/ai-hedge-fund (reference review)

- **Repo reviewed:** `D:\ShettyXtreme\references\ai-hedge-fund` (shallow clone, commit `6c41ae8`)
- **Upstream:** https://github.com/virattt/ai-hedge-fund
- **License:** MIT (Copyright 2024 Virat Singh) — see section 4
- **Date:** 2026-08-01
- **Purpose:** decide what to inherit (patterns only) for ShettyXtreme Phase-3 research workspace.
- **Stance (fixed):** AI/LLM agents are RESEARCH-LAYER ONLY. They draft briefs and research in a
  research workspace. Live signal generation stays deterministic/statistical. Agents NEVER place
  or gate orders.

---

## 1. Agent architecture

### 1.1 Two generations in the repo

The repo contains two architectures:

- **v1 (`src/`)** — the shipped LangGraph "hedge fund": ~19 LLM/rule agents, CLI + FastAPI web app.
- **v2 (`v2/`)** — a ground-up rebuild (WIP): a persistent "fund" object, `AlphaModel` interface,
  point-in-time data, one `run_cycle` pipeline shared by backtest/paper/live. This is the more
  relevant half for us; its stated principles are almost exactly our stance (see 1.6).

### 1.2 Agent roles (v1)

**Investor persona agents (13)** — LLM-judgment agents, each a system prompt + deterministic
feature extraction (metrics/line items) fed to the LLM: Aswath Damodaran, Ben Graham, Bill
Ackman, Cathie Wood, Charlie Munger, Michael Burry, Mohnish Pabrai, Nassim Taleb, Peter Lynch,
Phil Fisher, Rakesh Jhunjhunwala (India-flavored persona), Stanley Druckenmiller, Warren Buffett.
Each emits a per-ticker `{signal: bullish|bearish|neutral, confidence: 0-100, reasoning}`.

**Quantitative analyst agents (6)** — mostly deterministic rule engines, not LLMs:

- `technicals_analyst` — indicator-based signals (RSI, MACD, Bollinger, etc.)
- `fundamentals_analyst` — threshold scoring of ROE/margins/growth/health/valuation ratios
- `growth_analyst` — growth-trend scoring
- `news_sentiment_analyst` — scores recent news headlines
- `sentiment_analyst` — market-level sentiment gauges
- `valuation_analyst` — four deterministic valuation models (owner earnings, scenario DCF with
  WACC, EV/EBITDA multiple, residual income), weighted blend, then gap-to-market-cap signal

**Control agents (2):**

- `risk_manager` — deterministic (no LLM): fetches prices, computes daily/annualized volatility,
  volatility percentile, cross-ticker correlation matrix; derives a per-ticker
  `remaining_position_limit` (volatility-adjusted % of portfolio value x correlation multiplier,
  capped by cash). Output is a hard, machine-readable constraint for the next stage.
- `portfolio_manager` — the ONLY agent that emits order-like decisions. LLM picks an action
  (`buy|sell|short|cover|hold`) + quantity, but ONLY from a deterministically pre-validated
  allowed-action set (`compute_allowed_actions`: cash, margin, position limits all checked in
  code first). No-cash/no-margin math is left to the LLM. Holds are prefilled to cut tokens.

### 1.3 Orchestration (v1): LangGraph StateGraph, fan-out -> funnel

`src/main.py::create_workflow` builds a `StateGraph(AgentState)`:

```
start_node
   ├── analyst_1 ──┐
   ├── analyst_2 ──┤   (all selected analysts run in PARALLEL, config-driven
   ├── ...         ─┤    subset selectable per run)
   └── analyst_N ──┘
          ↓
   risk_management_agent   (funnel: sees ALL analyst signals + portfolio)
          ↓
   portfolio_manager       (LLM constrained by deterministic limits)
          ↓
   END
```

- Analysts fan out from a single `start_node`; LangGraph executes independent branches in parallel.
- The `risk_management_agent` node funnels every analyst's output, then the `portfolio_manager`
  terminal node produces the final decisions JSON, which is parsed from the last message.
- The whole graph is compiled once per run; analyst selection is a CLI/API input.

### 1.4 Shared state (the "state handoff")

`src/graph/state.py::AgentState` is a TypedDict with three keys and custom reducers:

- `messages` — accumulating `Sequence[BaseMessage]` (`operator.add`); every agent appends a
  `HumanMessage(name=agent_id, content=json.dumps(...))`.
- `data` — merged dict (`merge_dicts`): `tickers`, `portfolio`, `start_date/end_date`, and the key
  handoff artifact **`analyst_signals`**: a dict keyed by `agent_id`; each analyst writes
  `state["data"]["analyst_signals"][agent_id] = {ticker: {signal, confidence, reasoning}}`.
- `metadata` — model name/provider, `show_reasoning` flag, per-agent model overrides.

This is a simple, inspectable "shared blackboard": no agent-to-agent message passing, no tool
calls between agents — each reads the shared dict and writes its own key. Deterministic and
debuggable; `show_agent_reasoning` pretty-prints each agent's JSON for human review.

### 1.5 Tools (v1)

One tool module, `src/tools/api.py`, wrapping the `financialdatasets.ai` REST API:

- `get_prices`, `get_financial_metrics`, `search_line_items` (statement line items),
  `get_insider_trades`, `get_company_news`, `get_market_cap`
- All return Pydantic-validated models (`PriceResponse`, `FinancialMetricsResponse`, ...)
- Disk cache (`src/data/cache.py`, keyed by ticker+dates) — reruns are free and offline
- 429 rate-limit handling with linear backoff (60s, 90s, ...)
- Note: agents do NOT discover or call tools themselves — tool use is hard-coded per agent. The
  "tool" concept is just the data-access layer. (The app/ backend has FastAPI + SQLite flow
  persistence, irrelevant to us.)

### 1.6 The "council/team" decision flow and v2's principle that matches our stance

- v1's flow is: independent analyst views (the "council") -> deterministic risk funnel -> a single
  constrained PM. No voting/weighting among analysts happens in code; the LLM PM does the
  synthesis.
- v2's non-negotiable principles (from `v2/README.md`) are worth quoting:
  - **"The LLM never touches the trade. Agents form views and narrate; deterministic code sizes
    and places orders; risk limits are hard gates."**
  - "Conviction requests, risk disposes": `v2/risk/limits.py::apply_limits` clamps target weights
    against hard caps (`max_position_pct`, `max_gross_exposure`) with an audit trail
    (`ClampEvent`); clamped exposure stays in cash (never redistributed).
  - Point-in-time by construction: the data layer filters on filing date, not report period —
    no lookahead in backtests.
  - One `run_cycle` pipeline: data -> alpha models -> portfolio -> risk -> execution -> ledger,
    used identically for backtest/paper/live.
  - `AlphaModel.predict(ticker, date, data_client) -> Signal` — one interface for quant models
    (PEAD) and LLM agents; `Signal` carries conviction in [-1, +1] + `reasoning` + components.

This is the architecture we should mirror: LLM agents produce *views* (research artifacts);
deterministic code does everything downstream.

---

## 2. What to INHERIT (patterns for our research workspace)

1. **Config-registry agent discovery.** `src/utils/analysts.py::ANALYST_CONFIG` is a single
   source of truth (key, display name, description, style, agent func, order). `get_analyst_nodes`
   derives graph nodes from it; subsets are selectable per run. -> Our research workspace should
   register research briefers the same way (e.g., YAML/TOML + import hook), so adding a briefer is
   declarative, and the human can pick a subset per task.
2. **Structured agent outputs via Pydantic.** Every LLM agent declares a Pydantic output model
   (`WarrenBuffettSignal`, `PortfolioDecision`, `PortfolioManagerOutput`) and calls
   `call_llm(prompt, pydantic_model, ...)` (`src/utils/llm.py`) which uses
   `with_structured_output(method="json_mode")`, retries (3x), JSON extraction fallback for
   models without JSON mode, and a `default_factory` so a failed LLM call degrades to a safe
   default instead of crashing the pipeline. -> Adopt wholesale: typed briefs are the contract
   between the research layer and the review UI.
3. **Shared blackboard state handoff.** `AgentState` + `analyst_signals[agent_id]` pattern:
   agents read the shared context and write only their own key. Simple, serializable, replayable.
   -> Our research workspace: each briefer writes to its own key in a shared run context; the
   human-approval loop reads the assembled brief.
4. **Risk/PM agent concept (mirrors our risk engine).** Two distinct ideas, both useful:
   - A *deterministic risk gate* that converts raw conviction into hard, auditable constraints
     (v1 `risk_manager` volatility/correlation limits; v2 `RiskLimits`/`apply_limits` clamps with
     `ClampEvent` audit trail). This is a great template for our deterministic risk engine's
     "limits" stage.
   - A *PM stage that can only choose from pre-validated actions* — the LLM's freedom is bounded
     by code (cash, margin, limits computed deterministically; holds prefilled). Even in our
     research layer this is the right posture: an LLM can only *recommend* within constraints our
     deterministic code already validated.
5. **Backtest/eval harness for agent performance.** v1 `BacktestEngine` replays the whole graph
   over history; v2 `backtest_fund` loops `run_cycle` at rebalance cadence producing an equity
   curve vs benchmark and a full `CycleRecord` per tick; plus event-study (CARs) and planned
   CPCV/PBO validation. The key idea: **the backtest runs the exact same code path as a live
   cycle** — "honest by construction." -> For us: backtest/evaluate briefers (research quality
   vs. subsequent realized moves) via the same pipeline that will run them live, so eval is not a
   separate simulator.
6. **Point-in-time data discipline.** As-of/filing-date filtering to prevent lookahead — a
   correctness pattern worth copying into our data layer regardless of provider.
7. **Fail-loud data layer.** "Infrastructure failures raise; only genuine 'no data' returns
   empty" — avoids silent empties poisoning a backtest as fake "no signal".
8. **Multi-provider LLM factory.** `v2/llm` routes one client factory across Anthropic/OpenAI/
   DeepSeek/Google/xAI/Kimi (plus v1 `--ollama` local path). We already need provider abstraction.

## 3. What to REJECT or ADAPT

1. **REJECT: US-market data provider coupling.** `src/tools/api.py` targets
   `api.financialdatasets.ai` — US-ticker REST API, USD financials, US filing semantics. No NSE/BSE
   coverage, no ISIN/Indian corporate actions. The tool layer itself (cache, retry, Pydantic
   parsing) is a good template; the provider is not. We wire our own Indian data sources behind
   the same shaped interface.
2. **REJECT: any code path that generates trades from agent votes.** v1 `portfolio_manager`
   emits `buy/sell/short/cover/hold` decisions that `backtester.py` turns into portfolio
   mutations, and `src/backtesting/engine.py` executes them as simulated trades. For us the LLM
   output must terminate at *recommendation/brief*; order creation is exclusively deterministic
   and human-approved. Even the v2 "LLM never touches the trade" pattern is research-layer
   inspiration, not a license to auto-execute.
3. **REJECT (or demote): the celebrity-persona gimmick.** 13 named investor personas are
   educational flavor; the persona names add no predictive structure over the underlying
   features/prompts. What's worth keeping is the *separation* of briefer styles (value, growth,
   contrarian, tail-risk) as configurable research lenses — not the celebrity branding.
4. **REJECT: US-market assumptions baked into risk/portfolio math.** 252 trading days, short
   selling + margin model, USD cash accounting, ticker-centric universe logic, `long/short`
   position schema. Indian market constraints differ (e.g., intraday/derivatives segments, F&O
   lot sizes, STT/charges, T+1 settlement, no naked shorts on cash equities). We adapt the
   *shape* (limits, audit trail) and rebuild the arithmetic.
5. **REJECT: the FastAPI+SQLite app/ web layer** — we have our own app architecture.
6. **ADAPT: v1's news-sentiment and insider-trades agents** as research *lenses* over Indian news
   and SEBI disclosures — same pattern, new sources.
7. **ADAPT: `ANALYST_CONFIG` registry but as "research briefer" registry**, with a
   `type: research` field instead of `type: analyst`.

## 4. License and coupling risk

- **License: MIT** (LICENSE file, Copyright (c) 2024 Virat Singh). Permissive: we may read,
  copy, and adapt code and patterns, with attribution in derivative distributions. No copyleft
  obligations. Note the repo's own README says educational/research use only — which matches our
  research-layer-only stance; do not use their code in the live signal/execution path regardless.
- **Coupling risk: none.** We inherit *patterns* (state shape, Pydantic contracts, registry,
  risk-gate design), not code dependencies. No imports from the reference repo, no shared
  schema, no license contamination into the live engine. The only artifacts are this brief and
  the design patterns it documents.

## 5. Mapping to ShettyXtreme Phase-3 research modules

| ai-hedge-fund concept | ShettyXtreme Phase-3 mapping |
|---|---|
| `AgentState` blackboard + `analyst_signals[agent_id]` | Research workspace run-context: each briefer writes `briefs[agent_id]`; human review reads the assembled context |
| `ANALYST_CONFIG` registry + per-run analyst subset | Research-briefer registry (YAML-driven); user picks briefers per research request |
| Pydantic structured outputs + `call_llm` (retries, default_factory, JSON fallback) | Typed `ResearchBrief`/`SignalThesis` Pydantic contracts; shared LLM-call helper with safe degradation |
| `src/tools/api.py` shape (Pydantic models, disk cache, 429 backoff) | MCP tool exposure: Indian data providers behind the same shaped interface (NSE/BSE EOD, fundamentals, news/insider disclosures) |
| Risk manager limits + `apply_limits` clamps with `ClampEvent` audit trail | Our deterministic risk engine's limit/audit stage (already planned) — used in the *research workspace* to show "what would the risk gate say", never as a live order gate |
| Portfolio manager constrained action set | Human-approval loop (per Anthropic financial-services guidance): LLM proposes *within* pre-validated option sets; a human approves each recommendation before it can reach any downstream deterministic signal pipeline |
| v1/v2 backtest on the same code path as live runs | Research-briefer eval harness: replay briefers over history, score brief quality vs realized outcomes, same pipeline as production research runs |
| Point-in-time data discipline | Data-layer as-of/filing-date correctness for all Indian sources |
| `AlphaModel` -> `Signal` (conviction [-1,1] + reasoning) | Research briefer -> `ResearchOpinion` (direction + confidence + thesis); deterministic signal engine consumes *its own* statistical signals, not LLM output |

## 6. Honest evaluation — what this repo does NOT solve

1. **No Indian market data.** The entire tool layer is wired to a US provider. NSE/BSE data,
   SEBI filings, Indian fundamentals, corporate actions, F&O data — all absent. We must build or
   procure our own data stack; only the interface shape is reusable.
2. **No options intelligence.** Despite a `short` action, there is no options modeling — no
   implied vol surfaces, no option chains, no greeks, no Indian F&O lot/expiry semantics. Options
   research must be built independently.
3. **No execution.** v1 only simulates (backtester); v2's `SimBroker` is paper-only. There is no
   order routing, no broker connectivity, no Indian broker integration, no slippage/impact
   modeling beyond the simulator. Execution is entirely ours.
4. **No agent-quality evidence.** The repo ships no empirical evaluation of whether the persona
   agents add predictive value (v2's CPCV/PBO are planned, not shipped). We should treat LLM
   research briefs as *hypotheses*, not alpha; our deterministic engine is the measured edge.
5. **No live-operations discipline.** Nothing about operational risk of running LLMs near
   markets (prompt drift, data poisoning, cost spikes, output non-determinism, auditability).
   Anthropic financial-services guidance (human approval, guardrails, logging) must be layered on
   by us — the repo predates/none of it.
6. **No Indian market microstructure.** 252-day annualization, margin/short model, settlement
   cycles, and ticker-centric universe logic are US-shaped. We must stay independent on all
   Indian-specific quant decisions.

**Bottom line:** inherit the *state-and-contract patterns* (Pydantic outputs, blackboard handoff,
registry, risk-gate audit trails, same-path backtesting) and the v2 principle that the LLM forms
views while deterministic code disposes. Reject everything touching US data, simulated order
generation, or persona-as-edge. Our independence lies in the Indian data stack, the deterministic
signal engine, options intelligence, and the human-approval loop.
