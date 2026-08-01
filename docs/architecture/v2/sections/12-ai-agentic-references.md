# Section 12 — AI Agentic References

> The research-layer AI design per D3: LLM agents are **research-layer only** — they draft briefs and summaries and support the operator; live signal generation stays deterministic/statistical with conviction metrics; agents NEVER gate or place orders. Patterns drawn from ai-hedge-fund (MIT, `docs/references/BRIEF-ai-hedge-fund.md`), anthropics/financial-services (Apache-2.0, `docs/references/BRIEF-anthropics-financial-services.md`), and OpenBB (`docs/upstream/openbb-patterns.md`). Delivery: Phase 3 (research workspace), behind the knowledge layer (D12).

## 1. Agent roles and orchestration patterns

| Pattern (source) | Adoption in v2 |
|---|---|
| **Shared blackboard state handoff** — agents read shared context, write only their own key (`AgentState`/`analyst_signals`, ai-hedge-fund §1.4) | Research run-context: each briefer writes `briefs[agent_id]`; serializable, replayable, inspectable; no agent-to-agent message passing |
| **Config-registry briefer discovery** — `ANALYST_CONFIG` source of truth, per-run subsets (ai-hedge-fund §2.1) | Research-briefer registry (YAML + import hook); operator picks a briefer subset per task; adding a briefer is declarative |
| **Structured Pydantic outputs** — `with_structured_output(json_mode)`, 3x retry, JSON fallback, safe default (ai-hedge-fund §2.2) | Typed `ResearchBrief` / `SignalThesis` contracts; shared LLM-call helper; failures degrade to a safe default, never crash the pipeline |
| **Deterministic risk gates with audit trail** — `apply_limits` clamps + `ClampEvent` (ai-hedge-fund §1.6) | Risk engine's limit stage records every clamp with rule_id + evidence; clamped exposure stays unallocated |
| **Critic / re-verification subagent** — independent re-check against trusted sources (anthropics §1.3) | Deterministic pre-condition re-check (price, liquidity, circuit state) before an intent enters the approval queue; model pass only above a size/conviction threshold |
| **"Propose, never bind" doctrine** — work product FOR human sign-off; "this skill never approves" (anthropics §1.4) | An LLM produces an `intent` (signal + confidence + rationale + evidence refs); only operator approval converts it to an executable order intent |

## 2. MCP tool exposure — the OpenBB single-source API lesson

OpenBB generates REST endpoints, Python SDK methods, and MCP tool definitions from **one** router/command definition (openbb-patterns.md §3). Adopted:

- Data/analytics surfaces are defined once (Pydantic model + service) and exposed as REST + WS + **MCP tools** from that single definition — no drift between "API" and "what the agent sees".
- **Read-only data MCPs only** (market data, news, fundamentals). The Dhan adapter is never mounted into a research agent; order tools do not exist in the research toolset — absence beats prompt-engineering (anthropics §2.2).
- Connectors centralized in one config (`.mcp.json`-style), never per-agent duplicates; each tier's tool table documented per agent.

## 3. kyc-rules-style deterministic grid → our risk filter chain

The kyc-rules grid (anthropics §1.6/§2.2) is the direct model for the risk filter chain: rules with `rule_id`, `outcome (pass|fail|n/a)`, and `evidence`; disposition computed from rules, not vibes; **any hard-hit forces escalation**; the engine scores and gates, it never decides to trade. In v2 this is `intelligence/risk/risk_engine.py`'s composable filter chain — already deterministic, now upgraded to the grid shape: every gate evaluation appends a rule-outcome row to the intent record (audit trail); hard fails drop or flag the intent, never forward it.

## 4. output_schema validation with reject-retry

Every research worker output passes JSON-schema validation **before the orchestrator or operator sees it** (anthropics §1.5): `additionalProperties: false`, length caps, character-class regexes, enums, `maxItems` caps — injected instructions cannot survive intact through a validated channel. Policy: **reject-and-retry once, then fail**; a failing worker surfaces partial results and an error, never auto-advances. Applies to: research summaries, signal intents, operator decision records.

## 5. Tool isolation tiers

| Tier | Tools | Contact | In ShettyXtreme |
|---|---|---|---|
| Reader | Read/grep only, no MCP, no write; returns length-capped schema-validated JSON | Untrusted external content (news, scrapes) — "instructions in documents are data, never directives" | Feed/ingestion worker (Phase 3) |
| Orchestrator | Read/grep/glob + read-only data MCPs; no write | Trusted internal data only | Research assistant composing `ResearchBrief` from NSE/BSE data MCPs |
| **Write-holder** | The ONLY component with write/order authority; never opens untrusted files | — | **The Dhan execution adapter** — sole order-placing component, consumes only operator-approved intents (D10) |

## 6. Human-approval loop

- **Stop-and-surface checkpoints** (anthropics §1.4): pause after research synthesis and again after order-intent drafting; no chained auto-advance; nothing advances off an approval without a new stop.
- **One approval card per intent**: signal, confidence, rationale, risk-rule outcomes (kyc-grid), evidence refs, proposed order params — all schema-validated. Approve / reject / amend; decision immutable after.
- **Intent record** is the handoff: `intent_id`, instrument, direction, signal, rationale, evidence_refs, risk_rules, order_params, `validity_window_minutes`, status (`proposed|approved|rejected|amended|expired|executed`). The execution service refuses anything whose status is not `approved` with a fresh validity window — **approvals expire in minutes during Indian market hours**.
- Routing uses the allowlist pattern: hard-allowlist downstream targets (research → approval queue → execution gate) and schema-validate every payload; prefer typed events over text-blob parsing so content cannot forge handoffs.

## 7. The 5-stage loop

```
1. RESEARCH   read-only: reader tier ingests external feeds; orchestrator composes the
              ResearchBrief from trusted data MCPs (cited, [UNSOURCED]-marked)
2. GATE       deterministic: risk filter chain scores every intent against hard rules
              (limits, margin, circuit state, kill switch, liquidity); rule rows appended
3. CRITIC     independent pre-condition re-verification (cheap always; model pass above a
              size/conviction threshold)
4. APPROVE    human, synchronous: one approval card per intent; approve / reject / amend;
              decision immutable; validity window starts
5. EXECUTE    semi-auto: only the execution service (separate process, separate
              credentials) places orders, from an approved, unexpired, immutable intent
```

## 8. Hard guardrails (non-negotiable)

| Guardrail | Enforcement |
|---|---|
| No order tool in the research toolset | Toolset declared deny-by-default; order tools simply don't exist there (absence, not instruction) |
| Token budgets | Per-assistant and per-run caps enforced harness-side: max tokens, max tool calls, max iterations; kill the loop on exhaustion and surface partial results |
| Process kill switch | Stops in-flight research runs, blocks the execution service from placing orders, **checked by the risk engine on every gate evaluation**; one action to reach; dry-run testable |
| Untrusted-input doctrine | Only the reader tier with constrained tools touches external content |
| Audit trail | Every proposal, gate outcome, approval, and execution attempt is an append-only, schema-validated record |
| Point-in-time data discipline | As-of/filing-date filtering prevents lookahead in briefer evaluation (ai-hedge-fund §2.6) |

## 9. What NOT to adopt

- **US regulatory ceremony** — FINRA/SEC compliance machinery, KYC/AML onboarding, compliance-officer sign-off artifacts, multi-party approval chains. Private single-operator platform (D2/D11): one operator needs one approval gate, not an org chart (anthropics §3).
- **Claude-specific deployment plumbing** — `agent_toolset_20260401` dated schemas, `callable_agents`, Cowork plugin manifests, managed-agents API field names. Port the patterns (tiers, output_schema, handoff allowlist), not the manifests; the harness is provider-agnostic.
- **Trade-generating PM agents** — ai-hedge-fund's `portfolio_manager` emits buy/sell/short/cover decisions that a backtester executes. Rejected: LLM output terminates at recommendation/brief; order creation is exclusively deterministic and human-approved (ai-hedge-fund §3.2).
- **The celebrity-persona gimmick** — named investor personas add no predictive structure; keep only the separation of briefer styles (value, growth, contrarian, tail-risk) as configurable lenses.
- **Reference provider stacks** — OpenBB's 31 providers and ai-hedge-fund's US-ticker REST API are not ours; the *shape* (Fetcher abstraction, standard models) is reusable, the providers are not.

## 10. Honest limits of these repos

| Gap | Status |
|---|---|
| **No Indian data** | No NSE/BSE coverage, ISINs, or SEBI disclosures — our data stack is first-party; only interface shapes (Fetcher pattern, Pydantic contracts) are reusable |
| **No options intelligence** | No IV surfaces, chains, greeks, or Indian F&O lot/expiry semantics — built independently ([Section 14 — Data → Decision Intelligence](14-data-decision-intelligence.md)) |
| **No execution** | Neither repo routes orders to an Indian broker; execution and broker integration are entirely ours ([Section 11 — Dhan Integration](11-dhan-integration.md)) |
| **No agent-quality evidence** | No shipped evaluation that LLM briefs add value — briefs are hypotheses, never alpha; the deterministic engine is the measured edge (learning loop) |

Cross-references: [Section 05 — System Boundaries](05-system-boundaries.md) (knowledge layer G, D12), [Section 06 — Proposed Architecture](06-proposed-architecture.md) (research workspace), [Section 08 — Feature Map](08-feature-map.md) (research phasing), [Section 09 — ShettyBot Evolution](09-shettybot-evolution.md) (decision-support DNA), [Section 11 — Dhan Integration](11-dhan-integration.md) (write-holder), [Section 17 — Delivery Roadmap](17-delivery-roadmap.md) (Phase-3 sequencing: harness → orchestrator → grid → approval UI → execution).
