# ADR-002: OpenAlgo Standalone + Vendoring

## Status
Accepted (2026-08-01) — supersedes ADR-001 §1 ("composition" stance) and the July-12 reset's "absorb-only" stance.

## Context
The July-12 directive made ShettyXtreme standalone (no OpenAlgo runtime dependency). The Aug-01 brief demanded heavy OpenAlgo reuse. These are reconciled: OpenAlgo's execution plumbing is absorbed as origin-stamped, AGPL-3.0-licensed vendored files, synced by `scripts/sync_vendor.py` from a fresh upstream mirror — never imported, never run as a service.

## Decision
1. No runtime dependency on OpenAlgo — no server, no `import openalgo` anywhere in `src/` (CI grep gate).
2. `vendor/openalgo/` holds a curated subset (10 files: order constants, Dhan auth/order-mapping, shared utils, token_db) as ADAPTATION SOURCE implementing `core/interfaces` protocols in Phase 2.
3. `scripts/sync_vendor.py` syncs from `references/upstream/openalgo` (the only legal source; `D:\OpenAlgo` is a contaminated working copy and is never a source) with origin markers, ORIGIN.md manifest, byte-idempotent re-sync.
4. Monthly diff-review cadence, release-notes-driven, human-reviewed (never auto-merge).
5. `vendor/openalgo/LICENSE` ships the AGPL-3.0 text.

## Consequences
- Upstream updates flow in without touching core.
- Vendored files are license-bound: if the platform is ever distributed, the vendored subtree must stay AGPL-3.0 (D2: private use only, so not triggered today).
- The vendor contract (Section 10) must be enforced by review gates — the no-import grep gate is the tripwire.
