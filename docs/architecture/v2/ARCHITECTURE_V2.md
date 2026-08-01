# ShettyXtreme — Architecture Blueprint v2

> **Status:** Approved blueprint (2026-08-01) — replaces `v1/` (July-12 archive).
> **Superseded v1 stances:** OpenAlgo absorb-only → **standalone + vendoring**; dual Dhan credentials → **single-primary + data fallback**; Textual TUI → **Svelte web terminal**; AI-skeptical → **research-layer AI only**; product-for-others → **private use only**.
> **Evidence base:** 7 reference briefs in `docs/references/` (from Phase 0 parallel exploration), 12 decisions (D1-D12) in the Phase-0 interview log, vendoring pipeline in `vendor/`.

---

## Decisions at a Glance (D1-D12)

| # | Decision | Stance |
|---|----------|--------|
| D1 | OpenAlgo relationship | Standalone + vendoring — no runtime dependency, no `import openalgo`; curated AGPL code vendored at `vendor/openalgo/`, synced monthly |
| D2 | Distribution | Private use only — never distributed; AGPL absorption legal; monetization = trading edge |
| D3 | AI stance | Research-layer only — LLM drafts research, never gates or places orders |
| D4 | Design system | Custom `DESIGN.md` contract (repo root) — 9 Stitch sections, dark data-dense terminal language |
| D5 | Blueprint | Full v2 rewrite (this doc) |
| D6 | Market focus | Options-first (NIFTY/BANKNIFTY weekly); equities as terminal breadth |
| D7 | Repo layout | `references/` gitignored clones + `vendor/` tracked + `scripts/sync_vendor.py` |
| D8 | Dhan credentials | Single-primary (one consent token) + optional data fallback (PIN/TOTP); 806 = entitlement |
| D9 | Frontend | Svelte + Vite served by FastAPI, governed by DESIGN.md |
| D10 | Runtime mode | OBSERVER default; LIVE explicit per-session |
| D11 | Prop-style | Own capital/accounts only |
| D12 | Knowledge layer | Phase-4, human-gated, imports core only |

---

## Layer Diagram

```
  TERMINAL LAYER  (FastAPI REST+WS  →  Svelte+Vite frontend, DESIGN.md-governed)      [FAST]
        │
  EXECUTION LAYER (Order lifecycle | Position mgmt TP/TSL/EOD | semi-auto approval)
        │
  INTELLIGENCE LAYER (Features O(1)/tick | Regime | Signals+Conviction | Options EV | Risk | Scanners)  [RAPID]
        │
  LEARNING LAYER  (Outcome tracking | Voter quality CONSUMED | MFE/MAE | Walkforward | Calibration)
        │
  CORE PLATFORM   (Domain models | Event bus | Interfaces/Protocols | Config | Storage | Session)  [STABLE]
        │
  INTEGRATION LAYER (Dhan Trading Adapter | Dhan Data Adapter | instrument master | order validation)  [SWAPPABLE]
        │
  EXTERNAL DEPS   (DhanHQ-py 2.2.0 pinned | Dhan APIs | DuckDB | sqlite) — OpenAlgo NEVER at runtime
```

Knowledge layer (Phase-4) sits parallel to intelligence — imports core only, human-gated (D12).

## Core Data Flow

```
Dhan Data WS (feed codes 15/17/21) → DhanDataAdapter → EventBus (MarketDataReceived)
  → FeatureEngine (streaming, O(1)/tick) → (FeaturesComputed)
  → RegimeClassifier → (RegimeUpdated)
  → SignalEngine (voters → conviction, D/P/G, NEUTRAL) → (SignalGenerated)
  → OptionsIntel (IV rank, PCR, signal-drift EV strike selection) → Strategy Hint
  → RiskEngine (entries-only, cost-aware) → (RiskAssessed)
  → [OBSERVER: display in terminal]  |  [LIVE: ExecutionEngine → Dhan Trading API → (OrderPlaced)]
  → LearningLoop (outcome → voter quality → weight adjustment)
```

## Reading Order

| Section | Topic | Best for |
|---------|-------|----------|
| [00](sections/00-research-method.md) | Research method & evidence trail | Auditors, new contributors |
| [01](sections/01-reverse-engineering-lens.md) | 8 references reverse-engineered | What to inherit / avoid |
| [02](sections/02-current-state-reaudit.md) | v1 delivery state + corrected facts | Where we stand |
| [03](sections/03-product-vision.md) | Product vision | Why it exists |
| [04](sections/04-india-first-scope.md) | India market reality | Domain rules |
| [05](sections/05-system-boundaries.md) | 8 layers + import rules | Architecture discipline |
| [06](sections/06-proposed-architecture.md) | Full architecture | The core reference |
| [07](sections/07-update-resilient-design.md) | Upstream-sync + ACL strategy | Future-proofing |
| [08](sections/08-feature-map.md) | Feature map phased | What to build when |
| [09](sections/09-shettybot-evolution.md) | ShettyBot DNA mapping | Lineage |
| [10](sections/10-openalgo-utilization.md) | Vendor contract | OpenAlgo reuse rules |
| [11](sections/11-dhan-integration.md) | Dhan strategy | Broker reality |
| [12](sections/12-ai-agentic-references.md) | Research-layer AI design | Phase-3 AI |
| [13](sections/13-systematic-trading-breadth.md) | Quant resources checklist | Breadth gaps |
| [14](sections/14-data-decision-intelligence.md) | Decision intelligence chain | How signals work |
| [15](sections/15-design-system-terminal-ux.md) | DESIGN.md + terminal vision | UI |
| [16](sections/16-monetization-business.md) | Private-use economics | Business framing |
| [17](sections/17-delivery-roadmap.md) | Phases 0-4 | Sequencing |
| [18](sections/18-repo-codebase-strategy.md) | Repo layout & test targeting | Code organization |
| [19](sections/19-risks-failure-modes.md) | Failure register | Risk awareness |
| [20](sections/20-final-recommendation.md) | Final recommendation | TL;DR + first slice |

## ADRs

- ADR-001 (accepted) — initial architecture; superseded parts corrected by v2
- ADR-002 — OpenAlgo standalone + vendoring (D1)
- ADR-003 — private-use licensing posture (D2)
- ADR-004 — research-layer AI only (D3)
- ADR-005 — DESIGN.md contract + Svelte terminal (D4, D9)
- ADR-006 — options-first market focus (D6)
- ADR-007 — Dhan single-primary + data-fallback credentials (D8)

## Phase Map (detail in Section 17)

| Phase | Name | Status |
|-------|------|--------|
| 0 | References + vendoring pipeline | ✅ DONE (2026-08-01, branch phase0-references-vendoring) |
| 1 | Blueprint v2 + DESIGN.md + ADRs | ✅ THIS DOCUMENT |
| 2 | Pipeline completion + Svelte terminal (usable MVP) | NEXT |
| 3 | Advanced intelligence + research workspace | Planned |
| 4 | Maturity: multi-broker optional, knowledge layer | Optional |
