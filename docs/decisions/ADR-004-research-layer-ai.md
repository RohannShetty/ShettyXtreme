# ADR-004: Research-Layer AI Only

## Status
Accepted (2026-08-01).

## Context
The Aug-01 brief added ai-hedge-fund (LLM-agent hedge fund) and anthropics/financial-services as references, while the v1 blueprint removed the ML voter (AUC 0.518) and demanded "no magical AI claims."

## Decision
1. LLM agents serve the research workspace and operator support only: research briefs, summaries, regime commentary, option-structure explainability drafts.
2. Live signal generation stays deterministic/statistical (voters, conviction, D/P/G, NEUTRAL).
3. Agents NEVER place, gate, or modify orders; no order tool exists in the research toolset (3-tier tool isolation; Dhan adapter is the single write-holder).
4. Approval doctrine: propose-never-bind; stop-and-surface checkpoints; output schema validation with reject-retry; token budgets; kill switch checked at every gate.
5. MCP exposure is read-only (OpenBB lesson).
6. The 5-stage loop (research → gate → critic → approve → execute) is Phase-3 scope (Section 12).

## Consequences
- No nondeterminism in the decision path; the learning loop measures deterministic signals honestly.
- Phase-3 AI work is additive (research workspace), never a refactor of the signal engine.
