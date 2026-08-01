# Phase 1: Blueprint v2 + DESIGN.md Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the v2 blueprint (docs/architecture/v2, 20 sections), the DESIGN.md design contract at repo root, and ADR-002…007 — the single source of truth for all later phases.

**Architecture:** Five parallel section-group agents write coherent section groups from a shared decisions pack (.superpowers/sdd/phase1-decisions-pack.md); one agent authors DESIGN.md from the awesome-design-md format spec; an integration pass writes the master ARCHITECTURE_V2.md, cross-checks consistency, and records the ADRs.

**Tech Stack:** Markdown only. No code changes to src/ in this phase.

## Global Constraints

- Zero changes under `src/` (blueprint phase is documentation-only)
- Every section MUST reflect the decisions in the decisions pack (D1-D12) — no reintroducing superseded stances (OpenAlgo runtime dependency, dual-credential, TUI, prediction-style AI)
- Corrected facts are binding: 806 = Data-API subscription entitlement (not credential-mixing); single-primary + data-fallback credentials; feed request codes 15/17/21; OpenAlgo mirror v2.0.1.7; AGPL-3.0 (OpenAlgo/Fincept), MIT (DhanHQ-py, awesome-design-md, ai-hedge-fund), Apache-2.0 (anthropics/financial-services)
- Sections land in `docs/architecture/v2/sections/` as `NN-title.md`; plain markdown, no placeholders/TBD, 4-10 KB each
- DESIGN.md lands at repo root `D:\ShettyXtreme\DESIGN.md`, 9 sections per the Stitch spec, dark data-dense trading-terminal language

---

### Task 1: Decisions pack (controller writes)

**Files:** Create `.superpowers/sdd/phase1-decisions-pack.md` (all 12 decisions + repo state + corrected facts + section conventions). Written by the controller before any agent dispatch.

- [ ] **Step 1:** Write the pack (see controller memory; content assembled from the Phase 0 interview log)
- [ ] **Step 2:** Write this plan file
- [ ] **Step 3:** Commit: `git add docs/superpowers/plans/2026-08-01-phase1-blueprint-v2.md && git commit -m "docs: phase1 blueprint plan"`

### Task 2: Parallel section-group agents (5 agents) + DESIGN.md agent (1 agent)

**Files:** Create `docs/architecture/v2/sections/00-research-method.md` … `20-final-recommendation.md`; create `DESIGN.md`

**Interfaces:**
- Consumes: `.superpowers/sdd/phase1-decisions-pack.md` (mandatory first read), `docs/references/BRIEF-*.md` (evidence), `docs/architecture/v1/` (prior work, superseded)
- Produces: 20 section files; 1 DESIGN.md — consumed by Task 3

- [ ] **Step 1:** Dispatch 6 agents in ONE parallel batch (subagent_type general). Agent → sections:
  - Agent A: 00-research-method, 01-reverse-engineering-lens, 02-current-state-reaudit, 03-product-vision
  - Agent B: 04-india-first-scope, 05-system-boundaries, 06-proposed-architecture, 07-update-resilient-design
  - Agent C: 08-feature-map, 13-systematic-trading-breadth, 14-data-decision-intelligence, 15-design-system-terminal-ux
  - Agent D: 09-shettybot-evolution, 10-openalgo-utilization, 11-dhan-integration, 12-ai-agentic-references
  - Agent E: 16-monetization-business, 17-delivery-roadmap, 18-repo-codebase-strategy, 19-risks-failure-modes, 20-final-recommendation
  - Agent F: DESIGN.md (repo root), using BRIEF-awesome-design-md.md + BRIEF-fincept.md + BRIEF-ai-hedge-fund.md (terminal vision) + taste-skill/ui-ux-pro-max-skill principles
- [ ] **Step 2:** Verify: 20 section files + DESIGN.md exist; each section 4-10 KB; grep pack decision tokens (D1-D12 wording) across sections
- [ ] **Step 3:** Commit: `git add docs/architecture/v2 DESIGN.md && git commit -m "docs: blueprint v2 sections + DESIGN.md (parallel agents)"`

### Task 3: Integration pass (controller + 1 reviewer agent)

**Files:** Create `docs/architecture/v2/ARCHITECTURE_V2.md` (master: 5-8 KB, summarizes + indexes all sections, records the phase-0→v2 provenance), `docs/decisions/ADR-002.md` … `ADR-007.md`

- [ ] **Step 1:** Controller writes ARCHITECTURE_V2.md master (structure, decisions table, layer diagram, reading order, link table to sections)
- [ ] **Step 2:** Controller writes ADR-002 (OpenAlgo standalone+vendoring), ADR-003 (private-use licensing), ADR-004 (research-layer AI), ADR-005 (DESIGN.md contract + Svelte terminal), ADR-006 (options-first focus), ADR-007 (single-primary+data-fallback credentials) — each: Status/Context/Decision/Consequences, ADR-001 style
- [ ] **Step 3:** Dispatch 1 reviewer agent: reads pack + master + all sections; reports any section that contradicts a decision, contradicts a corrected fact, contains TBD/placeholder, or is < 4 KB (thin). No edits — findings only
- [ ] **Step 4:** Controller fixes findings inline (or dispatches one fix agent for section edits)
- [ ] **Step 5:** Verify suite still green: `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-phase1` → same 4 pre-existing failures only
- [ ] **Step 6:** Commit: `git add docs/architecture/v2 docs/decisions && git commit -m "docs: blueprint v2 master + ADRs"`

### Task 4: User review gate

- [ ] **Step 1:** Present summary (sections, decisions table, DESIGN.md highlights) to the user; ask for review of `docs/architecture/v2/ARCHITECTURE_V2.md` + DESIGN.md
- [ ] **Step 2:** On approval: update ledger, mark Phase 1 complete, proceed to Phase 2 planning. On changes: fix, re-run Task 3 step 4-6, re-present.

---

## Self-Review Checklist (controller)

1. **Spec coverage** — all 17 user brief sections present (as 00-20 with merged learnings sections); all 12 decisions reflected; corrected facts everywhere; DESIGN.md 9-section spec compliant.
2. **Placeholder scan** — reviewer agent explicitly checks for TBD/TODO/vague.
3. **Consistency** — reviewer agent cross-checks sections against pack; integration pass fixes before commit.
