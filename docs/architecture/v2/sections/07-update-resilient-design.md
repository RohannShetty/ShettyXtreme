# Section 07 — Update-Resilient Design

> How v2 survives upstream churn: anti-corruption layers at every boundary, port/interface contracts, vendoring with origin markers, sync workflows for OpenAlgo and DhanHQ-py, and the fork-vs-composition discipline that keeps the system an adapter farm instead of a brittle monster.

## Anti-corruption layers (per boundary)

| Boundary | ACL | Mechanism | Failure mode prevented |
|---|---|---|---|
| DhanHQ-py → core | `integration/dhan/` adapters only | The only code that imports `dhanhq`; core sees `OrderExecutor`/`MarketDataStream`/`AccountInfo`/`BrokerGateway`/`DataProvider` Protocols (`core/interfaces/`) | DhanHQ API drift forcing core changes |
| OpenAlgo upstream → ours | `vendor/openalgo/` (never importable) + adaptations | Vendored files are origin-stamped (AGPL-3.0, per D1/D2); adaptations in `integration/` implement core Protocols; `scripts/sync_vendor.py` pipeline (below) | Upstream refactors contaminating our logic |
| Dhan raw WS protocol → pipeline | `DhanDataAdapter` only | Request codes 15/17/21, unsubscribe = code+1, RequestCode 12, error packets 805–809 handled inside the adapter (Phase-2 request-code fix) | Protocol changes leaking into intelligence |
| Dhan auth/session → pipeline | `auth/` (CredentialStore, DhanOAuthHelper, TokenHealthMonitor, CredentialValidator) | Token expiry ~03:00 IST handled pre-open; 806 treated as entitlement, not credentials (per D8) | Session failures breaking the whole app |
| Broker positions payload → portfolio | position snapshot + `multiquote` LTP reconciliation | Broker-agnostic `Position` domain model; LTP merged from multiquote (per Section 04) | Broker payload quirks leaking into risk math |
| Terminal Svelte → backend | FastAPI REST + WS | SPA consumes DTOs, never core models directly | UI churn forcing core changes |
| Knowledge content → decisions | physical separation (per D12) | Knowledge layer imports core only; never intelligence/execution | Ingested content contaminating live logic |

**Contract normalization rule:** every external surface is normalized at the ACL boundary into core domain types (`Instrument`, `Order`, `Position`, `Signal`, `Event`). Downstream code never sees raw Dhan JSON, raw feed packets, or vendored types.

## Ports/interfaces

The five Protocols in `core/interfaces/` are the stable seams: `OrderExecutor`, `MarketDataStream`, `AccountInfo`, `BrokerGateway` (composition facade), `DataProvider`. Everything above integration codes to these. Protocol changes are ADR-gated (per Section 05). Adapters are selected by config (`broker: dhan`, `data_provider`), so swapping a broker is config + new adapter, zero core change.

## Vendor wrappers

Vendored OpenAlgo files are **adaptation source, never importable** (per D1). Two wrapper shapes exist:

1. **Direct adaptation** — vendored logic reimplemented against core Protocols inside `integration/` (e.g., order validation absorbed from vendored `utils/constants.py`; transform logic from `broker/dhan/mapping/transform_data.py`).
2. **Shim with substance elsewhere** — `vendor/openalgo/database/token_db.py` is a backward-compat re-export shim; the substance lives in non-vendored `token_db_enhanced.py`. **Phase 2 must vendor or reimplement that substance** — a shim pointing outside `vendor/` violates the "vendored set is self-contained" invariant and is a known caveat in `FILES.yaml`.

Every vendored file carries an origin header (commit, license, sync date) except where a `#` comment would corrupt the format (`plugin.json` — `marker: false` in `FILES.yaml`).

## Upstream sync workflow — OpenAlgo (monthly)

1. **Mirror refresh:** pull `references/upstream/openalgo` (fresh mirror, commit `3542a6e` baseline; mirror v2.0.1.7, 2026-07-28 — user's local v2.0.1.4 copy is contaminated and NOT a sync source, per corrected fact 3).
2. **Release-notes scan:** OpenAlgo ships ~3 releases/month; read release notes, classify: auth/feed changes (high interest), execution plumbing (medium), app features (skip).
3. **Diff review:** diff each vendored file against the mirror; decide absorb / skip / adapt.
4. **Sync:** `scripts/sync_vendor.py` re-copies selected files from the mirror, re-stamps origin headers, and updates `vendor/openalgo/FILES.yaml`.
5. **Adaptation pass:** update `integration/` adaptations where the vendored source changed; implement core Protocols.
6. **Validate:** full test suite (~495 tests) + adapter contract tests; no auto-merge, human review always (per pack conventions).
7. **Record:** outcome logged; unabsorbed diffs are tracked as open items for next month.

## Upstream sync workflow — DhanHQ-py (version-gated)

1. **Pinned at 2.2.0** (per D8; `pyproject.toml` exact pin).
2. **Changelog-gated bump:** any bump requires reading the changelog first. Known: 2.3.0rc1 is additive (conditional orders, global stocks, PnL exit), auth/feed/historical byte-identical to 2.2.0, and its only breaking change (`place_forever` losing `symbol`) is unused by us — but we stay pinned until a release we need (per corrected fact 5).
3. **Adapter validation:** before adopting, run the Dhan adapter contract suite (auth consent flow, order lifecycle, feed codes 15/17/21) against the new version.
4. **Staged rollout:** dev → observer session → live; rollback = unpin + lockfile revert.

## Fork vs composition strategy

| Strategy | When | Our use |
|---|---|---|
| **Composition** (pip dependency) | External library with a stable API and sane release cadence | DhanHQ-py (pinned), DuckDB, httpx, pydantic, cryptography |
| **Absorption** (copy + adapt, origin-stamped) | External project with useful patterns but entangled runtime (server, DB) we must not adopt | OpenAlgo execution plumbing (per D1); FinceptTerminal patterns only (AGPL, USD 50k clause — no code enters, per corrected fact 4) |
| **Fork** | **Never** — except upstream unmaintained 12+ months, and even then only after an ADR | Not used; fork drifts become a second upstream to track |

Rule: **composition for libraries, absorption for patterns, fork never.** Absorption always keeps the origin header + sync link so the copy's provenance is auditable.

## Compatibility testing

- **Adapter contract suite** (Phase 2 deliverable): each Protocol exercised against a recorded Dhan session (fixtures + live smoke in observer mode) — order lifecycle, positions/held positions, multiquote LTP, feed subscribe/unsubscribe codes, historical fetch.
- **Boundary import tests:** CI walks `src/` and fails on forbidden imports (core ← external; intelligence ← integration; src ← openalgo; per D1).
- **Version matrix:** DhanHQ-py bump runs the full suite, not just integration tests.
- **Vendor diff gate:** `scripts/sync_vendor.py` in dry-run mode reports unapplied upstream diffs so drift accumulates nowhere silently.

## Version pinning

| Surface | Policy |
|---|---|
| DhanHQ-py | Exact pin (2.2.0); bump only via changelog-gated review |
| OpenAlgo vendored files | Commit-pinned in `FILES.yaml` + origin headers; refreshed only by the monthly workflow |
| Runtime deps (duckdb, httpx, pydantic, cryptography) | Lock file; minor bumps reviewed, majors ADR-gated |
| Node/Svelte toolchain | Lock file; DESIGN.md compliance gate on UI changes |

## Changelog-driven review

No upstream upgrade happens without reading its changelog/release notes first. The review output is a one-line ADR-style entry (bump, why, what we skipped, validation run). Skipped-but-relevant upstream changes accumulate in a tracked open-items list — visibility beats silent staleness.

## Absorbing upstream improvements without contaminating core

The vendor contract (per D1) restated as rules:

1. Upstream code lives only in `vendor/openalgo/` (tracked, origin-stamped) and `references/upstream/` (gitignored mirror).
2. `src/` never imports `vendor/` or `openalgo` — adapters reimplement against Protocols.
3. Adaptations carry an origin marker naming the vendored source file.
4. When upstream improves, the improvement enters via the sync workflow → adaptation diff, reviewed like any other change. Core never sees the diff.
5. The token_db shim caveat is tracked to Phase 2 (substance must be vendored or reimplemented so `vendor/` is self-contained).
6. Knowledge-layer ingestion (Phase 4) is the only "content in" channel, and it is physically separated (per D12).

## How to avoid a brittle monster

- **Boundaries over breadth:** 8 layers, downward-only imports, CI-enforced (Section 05). A boundary test failing is a design error caught in review, not in prod.
- **One seam per external system:** DhanHQ, Dhan WS, OpenAlgo each have exactly one ACL; everything above depends on Protocols.
- **Small vendored set:** 10 files, listed in `FILES.yaml`, each justified; absorption is a decision, not a habit (per Section 10).
- **No import-time side effects in core:** core is pure models + bus + config; instantiation of adapters happens in composition root (Phase 2).
- **Monthly upstream rhythm:** drift is bounded to one month for OpenAlgo, one changelog for DhanHQ-py.
- **Test the contracts, not the vendors:** contract suites pin behavior; vendor internals may change freely under them.
- **Every dependency is a table row:** the external deps table (Section 05) is the admission gate; new deps require an ADR.

Cross-references: [Section 05 — System Boundaries](05-system-boundaries.md) (contracts enforced here), [Section 06 — Proposed Architecture](06-proposed-architecture.md) (Protocols in use), [Section 10 — OpenAlgo Utilization](10-openalgo-utilization.md) (exact vendored set), [Section 11 — Dhan Integration](11-dhan-integration.md), [Section 18 — Repo Codebase Strategy](18-repo-codebase-strategy.md), [Section 19 — Risks & Failure Modes](19-risks-failure-modes.md) (upstream coupling, boundary drift).
