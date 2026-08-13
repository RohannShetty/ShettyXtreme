# P2-3.5 Findings — Multi-Agent Research Layer (ai-hedge-fund pattern)

**Date:** 2026-08-12
**Scope:** Trace the current research architecture vs the P2-3.5 spec (pluggable analyst agents: Technical, Fundamental, Sentiment, Options, Risk, Portfolio — ai-hedge-fund pattern) and report what exists vs what's missing.
**Status:** Findings only — no code changed.

---

## 1. Current research architecture (what exists)

`src/shettyxtreme/research/` is a **lens-based LLM briefer harness**, not an agent framework. Nine files:

| File | Responsibility |
|---|---|
| `provider.py` | `BriefProvider` protocol + `DeepSeekProvider` (httpx, OpenAI-compatible, JSON mode, non-thinking) + `SimulatedProvider` test double. **The only LLM-touching module in the codebase (D3 wall).** |
| `lenses.py` | Declarative lens registry: `oi_iv_flow`, `directional_momentum`, `tail_risk` — each a `Lens` dataclass (name, description, system_prompt, brief_prompt_template). Config-registry discovery (ai-hedge-fund `ANALYST_CONFIG` analogue). |
| `digest.py` | `ContextDigest` — as-of snapshot from injectable named sources, `[SOURCE: name]` provenance, `[UNSOURCED]` when missing, max 8 sources × 2000 chars. |
| `briefs.py` | `ResearchBrief` pydantic contract. Harness-owned fields (`brief_id`, `lens`, `as_of`, `status`) vs model-authored whitelist (`MODEL_AUTHORED_FIELDS`); strict validation with reject-retry-once. |
| `orchestrator.py` | `ResearchOrchestrator.run(lenses, sources, tools)` — fan-out via `asyncio.gather`; per-lens: digest → prompt → provider (bounded tool loop, `MAX_TOOL_CALLS=3`, `MAX_RETRIES=1`, timeout 90s, 2000 token cap) → strict validate → persist. Failing lens surfaces partial + error, never crashes the run. |
| `store.py` | sqlite `data/research.db` — `briefs` table, status lifecycle `proposed → approved|rejected` (immutable decisions), `WIN|LOSS` outcomes, per-lens scoring aggregates. |
| `tools.py` | 5 read-only research tools: `chain_snapshot`, `regime_snapshot`, `scanner_alerts`, `options_posture`, `knowledge_search` — single source for both REST listing and LLM function-calling. Data injected via `DataSource` protocol (`research/` never imports `terminal/`). |
| `scheduler.py` | `ResearchScheduler` — asyncio tick loop. See §5. |
| `__init__.py` | empty |

Plus `terminal/api/research_router.py` (`/api/research/{lenses,tools,scheduler,run,briefs,approve,reject,outcome,scoring}` + WS broadcast `research` + learning-store mirror), `terminal/api/research_source.py` (`ProjectionDataSource` implements `DataSource`), wiring in `terminal/api/app.py` lifespan and `settings_router.py`. Tests: 8 files in `tests/wave8/` (research_*), plus `wave9` lifespan/knowledge/analytics integration tests. `scripts/research_smoke.py` is the env-gated manual DeepSeek run.

The orchestration shape already matches ai-hedge-fund's **fan-out → funnel**: analysts run in parallel and write to a shared context; the missing piece is the funnel (risk → portfolio stages).

## 2. Agent types needed vs what exists

| Spec agent | Status | Evidence |
|---|---|---|
| **TechnicalAnalyst** (pure Python: RSI, EMA, MACD, Bollinger) | **MISSING as agent.** Indicators partially exist as deterministic modules: `intelligence/features/indicators/{rsi,ema,sma,atr,adx,vwap}.py`, registered in `intelligence/pipeline.py` (`ema_9`, `ema_21`, `rsi`). **No MACD, no Bollinger.** No pure-Python analyst — the closest lens `directional_momentum` is LLM-driven. | `intelligence/features/indicators/__init__.py`, `pipeline.py:61-63` |
| **FundamentalAnalyst** | **MISSING** — correctly deferred. No fundamentals provider: ADR-008 moved data to Dhan/Fyers; no fundamentals API exists. Spec says defer or mock. | `docs/decisions/ADR-008-fyers-migration.md` |
| **SentimentAnalyst** (NSE bulk deals, FII/DII) | **MISSING.** Zero bulk-deals / FII-DII code in `src/`. Only `intelligence/voters/breadth_voter.py` (advancers/decliners breadth — a deterministic voter, not an agent). | grep `bulk deal|FII|DII|sentiment` → 1 hit (breadth_voter docstring) |
| **OptionsAnalyst** (IV rank, PCR, Max Pain, OI buildup) | **PARTIAL.** Deterministic building blocks exist: `options/iv_rank.py` (`IVRankCalculator`, 0-100 scale), `options/max_pain.py`, `options/oi_tracker.py` (PCR + OI-buildup alerts), `options/greeks.py`; `intelligence/options/options_intel.py` (`compute_iv_rank` 0-1 canonical, `compute_iv_percentile`, PCR-contrarian signal, `compute_signal_drift_ev`). Research tool `options_posture` already exposes IV rank/PCR/OI buildup text to the LLM (`research_source.py:134-196`). **Max Pain is not wired into the research digest/tools.** Closest lens: `oi_iv_flow`. | `options/*.py`, `research_source.py:13-74` |
| **RiskManager** (portfolio heat, correlation) | **PARTIAL.** Deterministic risk machinery exists: `intelligence/risk/risk_engine.py` (kyc-grid filter chain, rule_id + evidence audit), `intelligence/signals/voter_correlation.py` (correlation block caps). **No research-layer risk stage** — nothing shows "what would the risk gate say" inside research; no portfolio-heat concept. Closest lens: `tail_risk`. | `intelligence/risk/`, `intelligence/signals/voter_correlation.py` |
| **PortfolioManager** (aggregates signals → final proposal) | **MISSING.** Orchestrator runs lenses concurrently and returns per-lens briefs; **no synthesis stage**. `SignalThesis` (referenced in section 12 + ai-hedge-fund brief) was never implemented. ai-hedge-fund's PM was explicitly rejected as trade-generating (§9 of section 12), but the *constrained aggregation* pattern (LLM proposes within deterministically pre-validated options) is adoptable. | `docs/architecture/v2/sections/12-ai-agentic-references.md:77`, `research/orchestrator.py` |

**Net:** the existing 3 lenses map loosely as `directional_momentum → Technical`, `oi_iv_flow → Options`, `tail_risk → Risk`. There is **no agent abstraction** — `Lens` is prompt-only; nothing produces a signal without an LLM call.

## 3. D3 wall compliance — **CLEAN (verified)**

- `provider.py` docstring states it is "the ONLY module in the codebase that talks to an LLM (D3 wall): nothing outside research/ imports it, and no LLM output reaches the signal/gate/execution path."
- Grep verified: `intelligence/` has **zero** httpx/openai/anthropic/deepseek/Provider usage. `execution/` matches are only the unrelated local `_LotSizeProvider` Protocol (`signal_bridge.py:38`).
- Cross-layer import check: `research/` imports from src/ only inside `terminal/` (composition root: app.py, research_router, settings_router, analytics_router, knowledge_router, research_source) and `research/` itself. **No imports from `intelligence/`, `execution/`, `knowledge/`, `learning/`.**
- `knowledge/` imports core only (D12): `knowledge/ingest.py` uses a structural `ResearchBriefLike` Protocol so the sync wiring lives in the terminal layer without a dependency edge.
- LLM output terminates at: research.db briefs, knowledge store (decided briefs), learning store (decision/outcome mirror) — never in the signal/gate/execution path.

**Implication for P2-3.5:** pure-Python deterministic analysts (Technical/Options/Sentiment) are *more* D3-compliant than the current LLM lenses — they add no LLM surface at all.

## 4. Knowledge store integration — **PARTIAL (gap vs spec)**

- Briefs are persisted in `data/research.db` (ResearchStore), **separate** from the knowledge store (`data/knowledge.db`).
- Existing sync: `knowledge/ingest.py::ingest_decided_briefs` ingests only **decided** (approved/rejected) briefs into the knowledge store as `kind="research_brief"`, triggered by `POST /api/knowledge/sync` (`knowledge_router.py:172`). Knowledge lifecycle: `proposed → activated` (human gate) — activation makes it a research source.
- KnowledgeDoc kinds in use: `operator_note` (notes.py:27), `research_brief` (ingest.py:61).
- **Gap:** the spec's `ResearchNote (kind: agent_signal, status: proposed)` **does not exist**. `KnowledgeDoc.kind` is a free-form string, so adding `agent_signal` is trivial schema-wise, but nothing writes proposed agent signals into the knowledge store today.

## 5. Scheduler — **EXISTS, but not 5-minute, not agent-aware**

- `research/scheduler.py::ResearchScheduler` — asyncio tick loop, sleep-then-run; tick failure logged, loop continues; never crashes the app.
- **Default interval is 60 minutes** (`RESEARCH_SCHEDULE_INTERVAL_MINUTES` default `"60"` in app.py:107-109). Configurable via env or the settings store (source of truth since Phase 7 Wave 3; `settings_router.py:_apply_scheduler` restarts on interval change).
- Env-gated: runs only when `RESEARCH_SCHEDULE_ENABLED=1` **and** `DEEPSEEK_API_KEY` present (app.py:277-293).
- Each tick calls `orchestrator.run(lenses, tools)` — i.e., it schedules the **LLM lens run**, not deterministic agents.
- API: `GET /api/research/scheduler` reports enabled/interval/next_run/last_run/result.

**Note:** a 5-minute cadence for *deterministic* analysts would be cheap (no API cost); the same cadence for LLM lenses would burn DeepSeek tokens 12×/hr. The scheduler's per-run `lenses`/`tools` config already supports separating the two.

## 6. ADR — **NO ADR-010**

ADRs 001–008 exist in `docs/decisions/`; the highest is ADR-008 (Fyers migration). The research layer is governed by **ADR-004 (Research-Layer AI Only)** + ARCHITECTURE_V2 section 12 + phase3b/3c specs. **No ADR documents a multi-agent research architecture.** Creating ADR-010 for the multi-agent analyst layer would be the natural slot (next free number).

## 7. Proposed fix approach (algorithm — not code)

1. **Introduce a pluggable `Agent` abstraction alongside `Lens`** in `research/` (config-registry discovery preserved): `{name, agent_type: technical|fundamental|sentiment|options|risk|portfolio, deterministic: bool, compute() | build_prompt()}`. Deterministic agents return a `ResearchBrief`-shaped `AgentSignal` without any LLM call; LLM lenses keep the current prompt path. Both write the same typed signal contract.
2. **Deterministic analysts** (D3-clean, no API cost):
   - *TechnicalAnalyst*: reuse `intelligence/features/indicators` + add MACD and Bollinger indicators (missing today), compute RSI/EMA/MACD/Bollinger directly → direction + confidence.
   - *OptionsAnalyst*: wire existing `options/iv_rank.py`, `options/max_pain.py`, `options/oi_tracker.py`, `intelligence/options/options_intel.py` into one signal; add Max Pain to the research digest/tools (currently absent).
   - *SentimentAnalyst*: new NSE bulk-deals + FII/DII scrape (deterministic score, cite source; `[UNSOURCED]` when the scrape is unavailable). Deferred per spec.
   - *FundamentalAnalyst*: defer (no fundamentals provider; ADR-008).
3. **RiskManager stage (funnel)**: reuse `intelligence/risk/risk_engine.py` limits + `voter_correlation` as a **read-only research pass** that annotates the aggregated signal set with rule outcomes + evidence ("what would the risk gate say") — never a live order gate.
4. **PortfolioManager stage**: deterministic weighted aggregation of analyst signals into a final proposal; optionally LLM-narrated but constrained to a deterministically pre-validated action set (ai-hedge-fund v2 principle "LLM never touches the trade"; section 12 §9). This fills the missing `SignalThesis`/aggregation slot.
5. **Knowledge store integration**: add `kind="agent_signal"` ingestion of **proposed** agent signals into the knowledge store (mirroring the `research_brief` sync but at `proposed` status, keeping the human activation gate). `KnowledgeDoc.kind` is free-form — no schema change needed.
6. **Scheduler**: keep `ResearchScheduler`; run deterministic analysts every 5 min (config: `scheduler_interval_minutes=5` with `lenses=technical,options,sentiment`) while LLM lenses stay on the operator-chosen cadence. No scheduler rewrite required.
7. **ADR-010**: document the multi-agent architecture (agent types, determinism split, D3 compliance, knowledge-store note flow).

## 8. Reusable code inventory

| Need | Reuse |
|---|---|
| Technical indicators | `intelligence/features/indicators/{rsi,ema,sma,atr,adx,vwap}.py`, `feature_engine.py`, `pipeline.py:61-63` (**add MACD + Bollinger**) |
| Options intel | `options/{iv_rank,max_pain,oi_tracker,greeks}.py`; `intelligence/options/options_intel.py` (iv_rank 0-1, iv_percentile, PCR contrarian, signal_drift_ev); `research_source.py:13-74` (`render_options_posture`) + `ProjectionDataSource.options_summary` (IV rank/PCR/OI alerts already rendered for the LLM) |
| Risk / correlation | `intelligence/risk/risk_engine.py`, `intelligence/signals/voter_correlation.py` |
| Signal contract + harness | `research/{briefs,orchestrator,provider,store,tools,scheduler,digest}.py` — all reusable as-is |
| Data injection | `terminal/api/research_source.py` (`ProjectionDataSource`), `research/tools.py` `DataSource` protocol |
| Knowledge sync | `knowledge/ingest.py` (protocol-based, `ResearchBriefLike`), `knowledge/tagger.py`, `knowledge_router.py` sync endpoint |
| Sentiment-ish voter | `intelligence/voters/breadth_voter.py`, `micro_voter.py` (EMA cross) |
| Patterns doc | `docs/references/BRIEF-ai-hedge-fund.md` §2 (blackboard handoff, ANALYST_CONFIG registry, constrained PM), section 12 |

## Key gaps summary

1. No agent abstraction — `Lens` is prompt-only; no deterministic signal producer exists in research/.
2. No PortfolioManager/aggregation stage; `SignalThesis` never implemented.
3. No `agent_signal` knowledge kind; proposed agent notes not written to the knowledge store.
4. Scheduler exists but defaults to 60-min LLM passes, not 5-min deterministic agents.
5. No ADR-010.
6. MACD and Bollinger indicators missing; Max Pain not wired into research; SentimentAnalyst and FundamentalAnalyst (deferred) don't exist.
7. D3 wall is fully intact today — deterministic analysts would keep it that way (arguably strengthen it).
