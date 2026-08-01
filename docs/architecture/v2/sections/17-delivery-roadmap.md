# Section 17 — Delivery Roadmap

The roadmap is re-anchored on the verified repo state in [Section 02 — Current State Re-Audit](02-current-state-reaudit.md) and the binding decisions (D1–D12). Five phases; each has objectives, deliverables, risks, dependencies, postponed items, and a success validation. Nothing moves to phase N+1 before phase N gates pass ([Section 19 — Risks & Failure Modes](19-risks-failure-modes.md)).

| Phase | Name | Status | Exit criterion |
|---|---|---|---|
| 0 | References + vendoring | **DONE (2026-08-01)** | All 8 references cloned/briefed; vendor pipeline green |
| 1 | Blueprint + design contract | **CURRENT** | Blueprint approved; DESIGN.md + ADRs committed |
| 2 | Usable MVP — pipeline completion | **DONE (2026-08-01)** | 527 tests green (0 failures); terminal renders per DESIGN.md; option chain + strategy hints live |
| 3 | Advanced intelligence | **3A DONE (2026-08-01); 3B DONE (2026-08-01); 3C DONE (2026-08-01)** | 3A: session-gated shadow graduation (≥20 sessions, direction-aware, spec semantics), calibration→sizing, correlation block caps + conviction D/P/G live, walkforward breakdowns, learning endpoints — 563 tests green. 3B: research workspace core — DeepSeek briefer harness (3 lenses), schema-validated briefs with reject-retry, human approve/reject + outcome stub, `/api/research/*` — 599 tests green. 3C: read-only data tools w/ mid-run function calling, env-config scheduler, terminal panel + WS broadcast, outcome scoring + decided_at — 655 tests green (0 skipped). Critic pass deferred until order intents exist. |
| 4 | Maturity | After Phase 3 | Knowledge flow end-to-end (human-gated); analytics dashboards; optional multi-broker |

## Phase 0 — Foundations: references + vendoring (DONE, 2026-08-01)

**Objectives**: stand up the evidence trail and the external-code contract so the v2 rewrite starts from verified ground truth.

**Deliverables**: all 8 reference repos cloned under `references/` (gitignored, per D7) and distilled into `docs/references/BRIEF-*.md` (fincept, openalgo-upstream, dhanhq-upstream, ai-hedge-fund, anthropics-financial-services, quant-developers-resources, awesome-design-md, STATUS); `vendor/openalgo/` populated per `FILES.yaml` (origin-stamped, AGPL-3.0, per D1); `scripts/sync_vendor.py` working; corrected facts recorded (806 entitlement, feed codes 15/17/21, DhanHQ-py 2.2.0 pin — corrected facts 1, 2, 5).

**Risks faced**: none material; the contaminated local OpenAlgo copy (v2.0.1.4) was correctly excluded as a sync source (corrected fact 3).

**Dependencies**: none.

**Postponed**: everything else — by design.

**Validation**: `sync_vendor.py` syncs from the fresh mirror; vendor files hash-check; all 8 briefs committed.

## Phase 1 — This blueprint (CURRENT)

**Objectives**: write the full v2 architecture (this 20-section blueprint), the design contract, and ADR-recorded decisions before further code changes.

**Deliverables**: all sections 00–20 at `docs/architecture/v2/sections/`; `DESIGN.md` (Google Stitch format, 9 sections — per D4) at repo root; ADRs capturing D1–D12; kanban/issues updated; v1 archived at `docs/architecture/v1/` (per D5).

**Risks**: blueprint drift vs the decisions pack — mitigated by the pack being binding truth; parallel writers conflicting — mitigated by per-section ownership and cross-links.

**Dependencies**: Phase 0 complete.

**Postponed**: all coding (Phase 2 scope stays untouched until approval).

**Validation**: blueprint reviewed and committed; DESIGN.md present; every section cites its decisions; no placeholders.

## Phase 2 — Usable MVP: pipeline completion

**Objectives**: turn the 495-test codebase into a coherent, green, Dhan-connected options workstation: implement the two 501 stubs (per D6), fix the latent feed-code bug, complete the credential story (per D8), fix the mode default (per D10), clear all landmines, and ship the Svelte+Vite terminal (per D9) compliant with DESIGN.md.

**Deliverables** (each with its test gate):

| Deliverable | Work | Gate |
|---|---|---|
| Option chain + strategy hint endpoints | Wire `/options` and `/strategy-hint`; create `intelligence/hints/strategy_hints.py` and `intelligence/conviction/conviction_engine.py` (replacing the dead-import `__init__`s); implement `VoterRegistry` (currently a pass-stub) | `test_get_options`, `test_get_strategy_hint` pass (kills the 2 501s) |
| Feed request-code fix | `DhanDataAdapter` subscribes with codes 15/17/21 (Ticker/Quote/Full) and unsubscribes with code+1; stop passing v1 response codes 2/8 (corrected fact 2) | WS subscribe/unsubscribe mock tests; live smoke |
| Credential fallback + 806 surfacing | Optional `data_access_token` slot provisioned via PIN/TOTP `generateAccessToken` (per D8); 806 disconnect surfaced as "subscribe to Data APIs" entitlement message, not a credential error (corrected fact 1) | `test_dhan_data_adapter` 806 handling |
| OBSERVER default fix | Runtime mode default OBSERVER, LIVE is explicit per-session confirmation; mode persistence fixed | `test_execution_mode_default` passes |
| Landmine cleanup | Remove dead imports (`intelligence/hints`, `intelligence/conviction`), stale conftest fixtures (`integration.openalgo`, `dhan_adapter.DhanAdapter`), empty dirs (`execution/lifecycle/`, `execution/position_tracker/`, `tests/risk/`, `tests/integration/`), populate `core/errors/__init__.py` | Full suite green, no import errors at collection |
| Svelte+Vite terminal | FastAPI-served Svelte+Vite app replacing static HTML; panels per [Section 15 — Design System & Terminal UX](15-design-system-terminal-ux.md); DESIGN.md compliance pass | Terminal renders all panels; WS echo works; DESIGN.md checklist green |
| Full-suite green | Resolve `test_matches_builtin_black76` (quantlib env issue, unrelated to pipeline) and reach 495+ passing | `pytest` all green |
| `run.py` | Browser-open + uvicorn with explicit mode CLI flag; confirmation prompt for LIVE | Manual smoke |

**Risks**: WS binary protocol subtleties; DESIGN.md compliance scope creep in the terminal; quantlib environment issue persisting on some machines (keep the test env-pinned, not skipped silently).

**Dependencies**: Phase 1; DhanHQ-py pinned 2.2.0 (corrected fact 5); a live Dhan account with the Data API subscription (806 entitlement) for the fallback path.

**Postponed**: shadow-model activation gates, calibration curve, live execution beyond semi-auto, multi-leg constructor, knowledge layer, backtesting depth, multi-broker.

**Validation**: `pytest` green (495+); option chain + strategy hint served from live Dhan data in OBSERVER; terminal renders per DESIGN.md; a full simulated session runs end-to-end with zero import errors.

## Phase 3 — Advanced intelligence

**Objectives**: graduate the intelligence from display to validated edge: shadow-model activation gates, calibration, voter correlation, the research workspace and AI research layer (per D3), and deeper walkforward honesty.

**Deliverables**:

| Deliverable | Detail |
|---|---|
| Shadow-model activation gates | Shadow voters (per [Section 06](06-proposed-architecture.md)) graduate only after ≥20 sessions of tracked shadow data |
| Calibration curve | Confidence → win-rate mapping (isotonic/Platt) from real outcomes; consumed by sizing |
| Voter correlation | Pairwise agreement measurement; block caps where voters are redundant (per [Section 14](14-data-decision-intelligence.md)) |
| Research workspace | 5-stage research → gate → critic → approve → execute loop (per [Section 12 — AI & Agentic References](12-ai-agentic-references.md)); MCP tool exposure, human-approval gates, output schemas, token budgets |
| AI research layer | LLM agents draft briefs/summaries only — never gate or place orders (per D3, informed by `docs/references/BRIEF-ai-hedge-fund.md` and `docs/references/BRIEF-anthropics-financial-services.md`) |
| Walkforward depth | Honest evaluation with option premium + exit policy; per-regime and per-voter breakdowns |

**Risks**: calibration data sufficiency (needs enough sessions — do not rush the ≥20 gate); learning loop metrics consumed incorrectly; AI layer scope creep into decision-making (D3 is a hard wall).

**Dependencies**: Phase 2 complete; 20+ tracked sessions of DRY_RUN/OBSERVER data.

**Postponed**: knowledge ingestion, multi-broker, backtest depth, analytics dashboards.

**Validation**: at least one shadow voter activated through the gate; calibration curve plotted from real data; research workspace produces human-approved draft briefs; walkforward honest metrics reported per voter and regime.

## Phase 4 — Maturity

**Objectives**: round out the platform without opening the scope doors: optional multi-broker, backtest depth, the knowledge layer (per D12), and analytics dashboards.

**Deliverables**:

| Deliverable | Detail |
|---|---|
| Multi-broker (optional) | Second broker adapter only if needed; `core/interfaces` protocols already exist (per D1); Dhan remains first |
| Backtest depth | Historical walkforward harness depth beyond Phase 3; strategy comparison surfaces |
| Knowledge layer | Document store + tagger + human-gated activation, **imports core only**, physically separated from intelligence (per D12) |
| Analytics dashboards | Risk-adjusted performance, portfolio heatmap, cost analysis (from [Section 16](16-monetization-business.md) scorecard) |

**Risks**: scope expansion (feature-map discipline per [Section 08 — Feature Map](08-feature-map.md)); knowledge-layer contamination — mitigated by D12's physical separation and human gate.

**Dependencies**: Phase 3 complete; sufficient calibration data.

**Postponed**: SaaS, multi-tenancy, external users (never — per D2/D11).

**Validation**: knowledge ingestion → extraction → shadow validation → human approval → activation flow works end-to-end; analytics dashboards render from real ledger data.

## Cross-phase discipline

- **Phase gates**: no phase N+1 work until phase N exit criteria pass.
- **Regression gates**: every phase re-runs all prior test gates (495+ grows, never shrinks).
- **Review gates**: architecture/ADR changes reviewed before merge ([Section 18 — Repo & Codebase Strategy](18-repo-codebase-strategy.md)).
- **Postponement is recorded, not forgotten**: each phase names its postponed items so the next phase picks them up deliberately.
