# ADR-010: Multi-Agent Research Layer

## Status
Accepted (2026-08-12).

## Context
The research layer (`research/`) is a lens-based LLM briefer harness: 3 declarative LLM lenses (`oi_iv_flow`, `directional_momentum`, `tail_risk`) run concurrently via `ResearchOrchestrator`. The ai-hedge-fund pattern calls for a multi-agent funnel (analysts → risk → portfolio) with deterministic analysts alongside LLM lenses. The current architecture has no agent abstraction, no aggregation stage, and no deterministic signal producer.

## Decision

### 1. Agent Abstraction
Introduce a pluggable `Agent` abstraction alongside `Lens` in `research/agents/`:
- `{name, agent_type, description, deterministic, compute(), build_prompt()}`
- Deterministic agents return a `ResearchBrief`-shaped signal without LLM calls
- LLM lenses keep the current prompt path
- Both write the same typed signal contract (`ResearchBrief`)
- Config-registry discovery: `AGENTS` dict mirrors `LENSES` dict

### 2. Agent Types
| Agent | Type | Deterministic | Status |
|---|---|---|---|
| TechnicalAnalyst | technical | Yes | Implemented (RSI, EMA, MACD, Bollinger) |
| OptionsAnalyst | options | Yes | Implemented (IV rank, PCR, Max Pain, OI) |
| SentimentAnalyst | sentiment | Yes | Deferred (no bulk-deals/FII-DII provider) |
| FundamentalAnalyst | fundamental | Yes | Deferred (no fundamentals provider; ADR-008) |
| RiskManager | risk | Yes | Implemented (read-only risk annotation) |
| PortfolioManager | portfolio | Yes | Implemented (weighted aggregation) |

### 3. D3 Compliance
Deterministic analysts are **more** D3-compliant than LLM lenses:
- Zero LLM calls, zero external API dependencies
- All computations are pure Python, reproducible from input data
- `intelligence/` has zero LLM usage (verified)
- `execution/` has no research imports (verified)
- D3 wall remains fully intact

### 4. Funnel Shape (ai-hedge-fund pattern)
```
[TechnicalAnalyst] [OptionsAnalyst] [SentimentAnalyst]
         ↓                ↓                ↓
         └────────┬────────┘────────────────┘
                  ↓
           [RiskManager]  ← annotates with risk rules
                  ↓
        [PortfolioManager]  ← weighted aggregation
                  ↓
          [Final Proposal]  → operator decides
```

### 5. Knowledge Store Integration
- `kind="agent_signal"` ingestion of proposed agent signals
- Mirrors `research_brief` sync but at `proposed` status
- Human activation gate preserved (proposed → activated)
- `KnowledgeDoc.kind` is free-form — no schema change needed

### 6. Scheduler
- Deterministic agents: 5-minute cadence (zero LLM cost)
- LLM lenses: operator-chosen cadence (default 60 min)
- Dual tick loops in `ResearchScheduler`
- No scheduler rewrite required

### 7. MACD + Bollinger Indicators
Added to `intelligence/features/indicators/`:
- `MACD`: fast EMA - slow EMA, signal line, histogram
- `BollingerBands`: SMA ± k*stddev via Welford's online algorithm

## Consequences
- Deterministic agents strengthen D3 compliance (no LLM surface)
- RiskManager is a research annotation, never a live order gate
- PortfolioManager aggregation is deterministic; LLM narration is optional
- 5-minute agent cadence is cheap (no API cost)
- Existing LLM lenses unchanged; agents are additive
- `SignalThesis` concept is now implemented via PortfolioManager
- Knowledge store gains `agent_signal` kind for proposed signals
