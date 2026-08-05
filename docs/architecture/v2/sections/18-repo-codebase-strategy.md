# Section 18 — Repo & Codebase Strategy

## Verdict: modular monolith

ShettyXtreme is a **modular monolith**: one process, one operator, one machine (per [Section 06 — Proposed Architecture](06-proposed-architecture.md)). Microservices would add operational overhead for a single user. A flat monolith would repeat ShettyBot V1's god-module failure (2,702- and 3,381-line files, per [Section 09 — ShettyBot Evolution](09-shettybot-evolution.md)). The answer is strict internal boundaries — enforced by CI — with three explicit speed layers:

| Layer | Speed | Gate |
|---|---|---|
| **Core domain** (`core/`) | Stable | Changes are ADR-gated; zero external imports |
| **Strategy modules** (`intelligence/`, voters) | Swappable | Voter plugins via `VoterRegistry`; no hardcoded wiring |
| **UI** (`terminal/`, Svelte) | Fast | DESIGN.md contract (per D4); independent of backend |

## Repository map

```
ShettyXtreme/
├── src/shettyxtreme/          # all first-party code (layout below)
├── vendor/openalgo/           # TRACKED: curated upstream code, never importable (per D1)
├── references/                # GITIGNORED: raw clones + upstream mirrors (per D7)
├── scripts/sync_vendor.py     # vendor sync from references/upstream/openalgo
├── configs/default.yaml       # broker=dhan, dry_run=true, mode=observer
├── data/                      # shetty_kv.db + shetty_ts.db (gitignored)
├── docs/architecture/v1/      # archived blueprint (per D5)
├── docs/architecture/v2/      # this blueprint
├── docs/references/BRIEF-*.md # 7 evidence briefs (+ STATUS.md)
├── docs/superpowers/          # sdd plans (phase1-decisions-pack.md et al.)
└── DESIGN.md                  # terminal design contract, repo root (per D4)
```

`src/shettyxtreme/` (verified current state): `core/` (data_models, event_bus, interfaces, config, storage, errors), `auth/` (Fernet CredentialStore, DhanOAuthHelper, TokenHealthMonitor), `integration/dhan/` (DhanTradingAdapter, DhanDataAdapter, SessionHealth, instrument_master, order_validator), `intelligence/` (features, regime, signals, voters + shadow, hints, conviction, options, risk, scanners), `execution/` (ExecutionEngine, PaperTradingEngine, PositionManager), `learning/` (OutcomeTracker, VoterQualityTracker, WalkforwardEvaluator, CalibrationCurve, AnalyticsEngine), `options/` (greeks, iv_rank, oi_tracker, quantlib_pricer, strategy_analyzer), `terminal/` (FastAPI + routers + static), `observability/`, `research/` (verify in Phase 2), `plugins/` (verify in Phase 2), `data/` (historical, pipeline; verify in Phase 2).

## The two external zones (per D1/D7)

External code is quarantined in exactly two places, with a hard rule between them:

| Zone | Status | Contents | Role |
|---|---|---|---|
| `references/` | Gitignored | Raw clones of all 8 refs + `references/upstream/openalgo` fresh mirror | Evidence + sync source; never read at runtime |
| `vendor/openalgo/` | Tracked | `FILES.yaml`-listed curated files, origin-stamped, AGPL-3.0 (private-use absorption per D2) | **Adaptation source only — never imported** |

`scripts/sync_vendor.py` refreshes `vendor/openalgo/` from the mirror (monthly, per release notes, per D1); the gitignore anchors keep `references/` out of the repo while `vendor/` stays in (per D7). No `import openalgo` anywhere in `src/` — CI-enforced. Adaptations implement `core/interfaces` protocols; the vendor zone is a reference library, not a dependency ([Section 10 — OpenAlgo Utilization](10-openalgo-utilization.md)).

## Package boundaries + import rules

| Layer | Imports | Never imports | Rationale |
|---|---|---|---|
| `core/` | stdlib + own subpackages | anything external (no dhanhq, httpx, duckdb, quantlib) | Stable domain, frozen contracts |
| `auth/` | `core/` + DhanHQ-py | intelligence, execution | Credentials are infrastructure |
| `integration/dhan/` | `core/interfaces` + DhanHQ-py + httpx | intelligence, execution, terminal | Swappable adapter (D1) |
| `intelligence/` | `core/` only | integration, execution, knowledge | Pure decision logic |
| `execution/` | `core/` + `integration/` contracts | intelligence internals | Orders, position mgmt |
| `learning/` | `core/` only | intelligence internals (works on logged data) | Feedback loop |
| `options/` | `core/` + quantlib (pricer) | integration, execution | Pricing math |
| `terminal/` | `core/` + intelligence (read models) + execution (commands) | nothing below interfaces | Fastest-moving layer (D9) |
| `research/` | `core/` + intelligence read models | execution | Read-only workspace (D3) |
| `knowledge/` | `core/` only | intelligence, execution — **cannot import intelligence** | D12 physical separation |
| `observability/` | `core/` only | everything else | Sees events, not internals |
| `plugins/` | `core/interfaces` | concrete layers | Discovery registry |

CI gates (extend the v1 checks):

```bash
# core has zero external imports
! grep -rE "import dhanhq|import httpx|import duckdb|import quantlib|import openalgo" src/shettyxtreme/core/
# intelligence / knowledge never touch integration or execution
! grep -rE "from (integration|execution)|import (integration|execution)" src/shettyxtreme/intelligence/ src/shettyxtreme/knowledge/
# knowledge never touches intelligence
! grep -rE "from intelligence|import intelligence" src/shettyxtreme/knowledge/
# no-import gate on the vendor zone
! grep -rE "import openalgo|from openalgo" src/
# no god modules
! find src -name "*.py" | ForEach-Object { (Get-Content $_).Count } | Where-Object { $_ -gt 500 }
```

## Test targeting

- **Per-module test dirs** mirror the layout: `tests/core/`, `tests/intelligence/`, `tests/options/`, `tests/risk/`, `tests/execution/`, `tests/terminal/`, `tests/learning/`, `tests/integration/` — targeted runs, wave 1–7 gates per [Section 17 — Delivery Roadmap](17-delivery-roadmap.md).
- **Wave suites** are the phase exit criteria (e.g. `test_get_options`, `test_get_strategy_hint`, `test_execution_mode_default` in Phase 2).
- **Vendor tests**: `FILES.yaml` hash integrity + the no-import gate; the vendored set is validated, never executed.
- **Cross gates** (every change): full suite green (495+), import-rule greps, 1000-line rule.

## Branch / worktree workflow

- **Phase branches** (`phase-2-pipeline`, `phase-3-intelligence`, …) isolate work; one phase at a time per the roadmap.
- **Worktrees** for parallel research spikes so the working tree stays green.
- **Review gates**: every merge to main passes (a) full suite, (b) import-rule + line-count greps, (c) DESIGN.md compliance for terminal changes, (d) ADR note for core-interface changes.
- **Ledger discipline**: outcome/journals are data files, committed; config stays out of the ledger.

## What the strategy buys

Boundary enforcement turns the three speeds into a property: intelligence modules can be rewritten without touching core or terminal (voter plugins swap via `VoterRegistry`); Dhan can be swapped without touching intelligence (protocols); the UI can iterate daily against DESIGN.md without destabilizing the pipeline. The repo stays small enough for one operator to hold entirely in memory — which is the maintainability ceiling of the whole project ([Section 19 — Risks & Failure Modes](19-risks-failure-modes.md)).
