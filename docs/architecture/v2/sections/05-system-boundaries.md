# Section 05 — System Boundaries

> The eight-layer decomposition: what lives where, what each layer may import, what must never enter each layer, and the complete external dependency list. Import rules below are the binding architecture contract (CI-enforced per Section 07).

## Layer map

```
  H. OBSERVABILITY          (logs, metrics, health, audit)
  G. KNOWLEDGE      Phase-4 │ imports core ONLY, physically separated (D12)
  F. TERMINAL        FAST    │ FastAPI REST+WS → Svelte (D9)
  E. LEARNING        stable-ish│ imports core + intelligence/execution read models
  D. EXECUTION               │ imports core + integration/contracts
  C. INTELLIGENCE    RAPID   │ imports core ONLY
  B. INTEGRATION     SWAPPABLE│ imports core/interfaces + external APIs
  A. CORE            STABLE  │ zero external imports
```

Dependencies point **down only**. No layer may import a sibling or a layer above it. Enforcement: CI grep rules (per Section 07) + a dedicated test that walks `src/` imports.

## A) Core — STABLE

**Purpose:** the slow-moving foundation everything depends on; changes only through ADRs (per pack conventions).

**What belongs:**
- Domain models (`Instrument`, `Order`, `Position`, `Signal` — frozen dataclasses)
- Event bus: `Topic` enum + `Event` dataclass + asyncio pub/sub (`core/event_bus/event_bus.py`)
- Contracts/interfaces: `OrderExecutor`, `MarketDataStream`, `AccountInfo`, `BrokerGateway`, `DataProvider` Protocols (`core/interfaces/`)
- Config system: YAML + env loading with pydantic validation (`configs/default.yaml`)
- Storage abstraction: SQLite KV (`data/shetty_kv.db`) + DuckDB TS (`data/shetty_ts.db`) + migrations
- Session state: market calendar, session lifecycle, runtime mode (OBSERVER default per D10)
- Health check interfaces

**What does NOT belong:** any broker-specific code, any DhanHQ import, any `httpx`/`duckdb` import, any signal/strategy/UI/research logic, any vendored code.

**Import rule (verbatim, pack conventions):** zero external imports — only stdlib + own subpackages. **No `import openalgo` anywhere in `src/` (per D1).**

**Stability:** HIGH.

## B) Integration — SWAPPABLE

**Purpose:** the anti-corruption layer between core and external systems; every external touchpoint lives here and only here.

**What belongs:**
- `DhanTradingAdapter` — order placement, positions, holdings, EDIS, margin, auth with pre-open token refresh (DhanHQ-py 2.2.0, single `DhanContext` per D8)
- `DhanDataAdapter` — live feed WS (codes 15/17/21, Phase-2 request-code fix), historical OHLC, OI/PCR; includes `get_option_chain` and `SessionHealth`
- Order validation — absorbed from OpenAlgo constants + logic, adapted to core contracts
- Instrument master — first-party, seeded from Dhan API, cached in SQLite KV
- Credential store accessors (Fernet `CredentialStore`, `DhanOAuthHelper` consent flow, `TokenHealthMonitor`, `CredentialValidator`)
- Vendored/absorbed OpenAlgo code — only ever at `vendor/openalgo/` (origin-stamped, AGPL-3.0, per D1/D2); adaptations in `integration/` implement core protocols and are marked with origin markers (per Section 07)

**What does NOT belong:** core business logic, signal intelligence, UI rendering, storage implementations, learning logic.

**Import rule:** imports `core/interfaces` + external APIs (DhanHQ-py, httpx). Never imports `intelligence/`, `execution/`, `terminal/`.

**Stability:** MEDIUM-HIGH; swappable without touching any other layer.

## C) Intelligence — RAPID

**Purpose:** the unique value — trading intelligence; expected to change fastest.

**What belongs:**
- `features/` — streaming O(1)/tick feature computation (bars, MA, ATR, ADX, VWAP, PCR, OI, IV)
- `regime/` — regime classifier on coarser bars (no Markov on 1m noise)
- `signals/` — signal engine, conviction computation, D/P/G, NEUTRAL state
- `voters/` — voter plugin system (breadth, micro, options_flow, orb, iv_rank + shadow voters); `VoterRegistry` is a Phase-2 stub
- `options/` — IV rank, OI analysis, PCR context, expiry/strike selection, strategy analyzer
- `risk/` — position sizing, loss limits (entries-only), margin guardrails, composable filter chain, cost model
- `scanners/` — gap detection, opportunity clusters

**What does NOT belong:** order execution, data storage, UI, broker-specific logic, any `integration/` import.

**Import rule:** imports core only.

**Stability:** RAPID — this is where the platform's edge lives; boundary tests protect core from its churn.

## D) Execution

**Purpose:** order lifecycle and position management.

**What belongs:** semi-auto approval flow, order lifecycle, `PositionManager` (TP1/TP2/TP3 fixed ordering, TSL, EOD close 15:15), `PaperTradingEngine`, one canonical stop-loss definition (premium-relative, vol-aware), mode gating (LIVE is explicit per-session action, per D10).

**Import rule:** imports core + integration/contracts (interfaces only, never DhanHQ directly).

**What does NOT belong:** signal generation, strategy logic, UI.

## E) Learning

**Purpose:** honest outcome measurement feeding back into intelligence.

**What belongs:** `OutcomeTracker` (immutable `signal_decisions` + `execution_attempts` + `outcome_labels`), `VoterQualityTracker` (CONSUMED → weight adjustments), `MfeMaeCalculator`, `WalkforwardEvaluator`, `CalibrationCurve`, `AnalyticsEngine`.

**Import rule:** imports core only (reads events; writes metrics). Never imports `integration/`.

## F) Terminal — FAST

**Purpose:** human surface; FastAPI backend + Svelte frontend (per D9), governed by DESIGN.md (per D4).

**What belongs:** FastAPI REST + WS endpoints (routers: watchlist, intelligence, execution, scanner, health, auth, postback, settings), Svelte SPA, static dashboard/setup/settings pages, WS echo, session controls.

**Import rule:** imports core + intelligence (read models) + execution (commands) + observability (read models). It is the only layer allowed to touch all others — as a read-mostly consumer.

**Stability:** FAST — UI churn must never leak into intelligence or core.

## G) Knowledge — Phase-4, HUMAN-GATED

**Purpose:** document store, tagger, heuristic extractor, knowledge linker; AI research-layer outputs land here (per D3/D12).

**What belongs:** ingested research briefs, operator notes, LLM-drafted summaries (never orders — per D3), knowledge graph.

**Import rule:** imports core ONLY; **physically separated** from intelligence and execution so ingested content can never contaminate live decision logic (per D12).

**Stability:** N/A until Phase 4.

## H) Observability

**Purpose:** structured logging, latency metrics, health checks, session audit log, credential health events.

**Import rule:** imports core only; consumed by terminal for display and by ops tooling.

## External dependencies (complete table)

| Dependency | Version | Used by | Purpose | Strategy |
|---|---|---|---|---|
| DhanHQ-py | **2.2.0 pinned** (per D8, corrected fact 5) | `integration/dhan/` only | Trading REST, feed WS, historical | Exact pin; changelog-gated bump; adapter validation suite (per Section 07) |
| DuckDB | stable semver | `core/storage/` | Time-series analytics | Semver range in lock file |
| httpx | current | `integration/` only | Async HTTP beyond DhanHQ-py | Lock file |
| pydantic | >=2.0 | `core/config/` | Config/validation | Semver range |
| cryptography (Fernet) | current | `auth/` | Credential store encryption | Lock file |
| OpenAlgo | **zero runtime deps** (per D1) | `vendor/openalgo/` (never importable) | Adaptation source for execution plumbing | Vendored + origin-stamped + synced via `scripts/sync_vendor.py` (per Section 07) |
| Svelte + Vite | current | `terminal/` frontend | Web terminal (per D9) | Lock file |

**Constraint:** DhanHQ-py, httpx, duckdb may be imported **only** by their owning layer (see table). Any new dependency must be added to this table and justified in the ADR that introduces it.

## Layer ownership test

A change is mislayered if it:
- touches DhanHQ outside `integration/dhan/` → violates B's boundary
- imports `integration/` from `intelligence/` → violates C's rule
- imports `duckdb` in `core/` → violates A's zero-external rule
- imports `openalgo` in `src/` → violates D1 outright (fails CI)
- reads the feed directly in `terminal/` → UI is a consumer of bus events, never a producer

Cross-references: [Section 06 — Proposed Architecture](06-proposed-architecture.md) (how the layers connect), [Section 07 — Update-Resilient Design](07-update-resilient-design.md) (boundary enforcement, ACLs), [Section 18 — Repo Codebase Strategy](18-repo-codebase-strategy.md) (physical layout), [Section 19 — Risks & Failure Modes](19-risks-failure-modes.md) (boundary drift).
