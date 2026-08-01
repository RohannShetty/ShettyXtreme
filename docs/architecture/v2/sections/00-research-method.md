# Section 00 — Research Method

How the 8 reference repositories were selected, evaluated, and converted into durable evidence during **Phase 0** (per [Section 17 — Delivery Roadmap](17-delivery-roadmap.md)), and how every later section consumes that evidence. The binding source for all claims in this blueprint is `phase1-decisions-pack.md` (decisions D1–D12); the evidence behind those decisions lives in the briefs listed below.

## 1. Phase 0 setup: three parallel research agents

Phase 0 ran three research agents in parallel, each with a scoped brief and a fixed output format. Each agent read its assigned clones (shallow clones under `references/`, mirrors under `references/upstream/`, per `docs/references/STATUS.md`), verified licenses, and wrote one `docs/references/BRIEF-*.md` file. The brief, not the clone, is the durable knowledge artifact: raw clones are gitignored and disposable, briefs are reviewed, corrected, and committed.

| Agent cluster | Assignment | Repos read | Briefs produced |
|---|---|---|---|
| **A — Execution & terminal breadth** | Brokers, order plumbing, product breadth, prior code | FinceptTerminal, OpenAlgo, DhanHQ-py, ShettyBot V1 | `BRIEF-fincept.md`, `BRIEF-openalgo-upstream.md`, `BRIEF-dhanhq-upstream.md` (ShettyBot V1 evidence comes from the pack's verified module inventory + `STATUS.md`, not a brief — it is our own code) |
| **B — Agentic & AI research patterns** | LLM-agent architecture, human-in-the-loop controls | ai-hedge-fund, anthropics/financial-services | `BRIEF-ai-hedge-fund.md`, `BRIEF-anthropics-financial-services.md` |
| **C — Resources & design** | Systematic-trading curriculum, terminal design format | Quant-Developers-Resources, awesome-design-md | `BRIEF-quant-developers-resources.md`, `BRIEF-awesome-design-md.md` |

Each brief ends with an explicit verdict set per candidate (inherit / adapt / skip / vendor / pattern-only), a license confirmation, a coupling-risk assessment, and an upstream-velocity note where the repo is active.

## 2. Separation: ideas vs implementation vs repo noise

Every reference was read through three filters, in order:

1. **License gate first** (corrected facts, pack §33-38): AGPL-3.0 (OpenAlgo, FinceptTerminal) → ideas only, code never importable; MIT (DhanHQ-py, ai-hedge-fund, awesome-design-md) → safe to use, attribute; Apache-2.0 (anthropics/financial-services) → safe to adapt with rewrite; **no license** (Quant-Developers-Resources) → read and link only, never copy wholesale.
2. **Implementation vs ideas**: for AGPL sources, the *idea* (e.g., "SL-M orders need a protective limit price under Dhan's MPP regime") is kept; the *implementation* is only ever consulted as a vendored adaptation source (OpenAlgo) or not at all (Fincept — see guardrail in §4).
3. **Repo noise**: stack mismatch (C++/Qt vs our Python/Svelte), domain mismatch (US-market math, career-interview content, global-macro breadth) and stale/empty material (empty `readme.md` dirs, rotting lnkd.in links) are explicitly discarded and recorded in the briefs' skip lists so the discard is auditable, not silent.

## 3. Blind-spot checks: awesome systematic-trading categories

To ensure the reference set did not merely confirm our priors, agent C ran a category-coverage check: the systematic-trading taxonomy of Quant-Developers-Resources (math foundations, programming, finance theory/portfolio, econometrics, risk management, technical indicators, AI/ML, execution, backtesting, projects) was mapped against ShettyXtreme's pillar list (terminal, scanners, research, signals, options intelligence, risk, execution, learning loop, backtesting). Results:

- **Covered well** by the reference set: options math, IV/OI analytics, risk curriculum, indicator catalogs, learning-loop methodology (de Prado walkforward/purged CV), agent governance.
- **Blind spots flagged** (kept as explicit gaps, not silently absorbed): cost modeling (brokerage/STT/tax-aware EV), streaming technical analysis, execution profiling (fill quality, slippage), pre-trade risk gates. These gaps are owned by [Section 13 — Systematic Trading Breadth](13-systematic-trading-breadth.md) and the feature map ([Section 08 — Feature Map](08-feature-map.md)).
- **India-specific blind spot**: the resources repo contains no NSE/BSE data tooling, no Dhan/Upstox broker docs, no F&O bhavcopy references — Indian data/execution knowledge had to come from the OpenAlgo and DhanHQ-py briefs plus in-house knowledge, not from the curriculum repo.

## 4. Guardrails that shaped this blueprint

- **Fincept cleanliness rule** (from `BRIEF-fincept.md` §5): no source file of Fincept may be opened while implementing a feature that mirrors its catalog; feature checklists are written from the brief, never from its code. Fincept is breadth inspiration, zero coupling.
- **OpenAlgo sync-source rule** (from `BRIEF-openalgo-upstream.md` §4 + D1): only the fresh mirror `references/upstream/openalgo` may feed `vendor/openalgo/` via `scripts/sync_vendor.py`. The user's local copy `D:\OpenAlgo` (v2.0.1.4, contaminated with personal strategy scripts) is never a sync source.
- **DhanHQ version-gating** (from `BRIEF-dhanhq-upstream.md` §5): stay pinned `>=2.2.0,<2.3.0`; diff the five contract files before any bump.
- **Patterns, not packages**: for every MIT/Apache reference, the blueprint inherits shapes (state handoffs, output schemas, approval gates, design tokens) and re-implements them in our stack; no reference repo is imported into `src/`.

## 5. Evidence trail: repo → brief → verdict

| # | Repo (clone/mirror path) | Brief file | Verdict in brief |
|---|---|---|---|
| 1 | FinceptTerminal (`references/upstream/fincept-terminal`) | `docs/references/BRIEF-fincept.md` | Breadth reference, concepts only; zero code coupling; AGPL + aggressive dual license |
| 2 | OpenAlgo (`references/upstream/openalgo`, v2.0.1.7) | `docs/references/BRIEF-openalgo-upstream.md` | Vendoring reference; 10-file A-tier set defined, synced monthly (D1) |
| 3 | ShettyBot V1 (`references/upstream/shettybot-v1`; `D:\ShettyBot_V1_Core`) | pack module inventory + `docs/references/STATUS.md` | Prior-version DNA; keep intelligence/learning seams, fix landmines (Phase 2) |
| 4 | DhanHQ-py (`references/upstream/dhanhq-py`; `D:\DhanHQ-py-2.2.0`) | `docs/references/BRIEF-dhanhq-upstream.md` | SDK dependency pinned 2.2.0; adapter-side fixes required (feed codes, 806) |
| 5 | Quant-Developers-Resources (`references/quant-developers-resources`) | `docs/references/BRIEF-quant-developers-resources.md` | Pointer index, no code; top-10 curriculum mapped to pillars |
| 6 | ai-hedge-fund (`references/ai-hedge-fund`) | `docs/references/BRIEF-ai-hedge-fund.md` | Pattern-only for Phase-3 research workspace; MIT; research-layer stance (D3) |
| 7 | anthropics/financial-services (`references/anthropics-financial-services`) | `docs/references/BRIEF-anthropics-financial-services.md` | Pattern library for approval gates + risk-grid shapes; Apache-2.0; rewrite, don't vendor |
| 8 | awesome-design-md (`references/awesome-design-md`) | `docs/references/BRIEF-awesome-design-md.md` | DESIGN.md format + style picks (Binance/VoltAgent/ClickHouse) → our DESIGN.md (D4) |

## 6. How later sections consume this

- [Section 01 — Reverse-Engineering Lens](01-reverse-engineering-lens.md) is the master per-reference table (inherit / NOT copy / coupling / external-vs-internal / upstream harvest) built on these briefs.
- [Section 02 — Current-State Reaudit](02-current-state-reaudit.md) applies the same lens to our own v1 codebase.
- Sections 09-15 operationalize per-reference inherit lists into module design; Section 13 carries the blind-spot gaps forward.
- Any claim about a reference repo in this blueprint traces to a brief path; where a fact could not be verified (e.g., live Dhan API behavior beyond the SDK), it is marked an open question per the pack's conventions.
