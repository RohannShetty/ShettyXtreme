# 07 — Multi-broker: build or defer?

Type: grilling
Status:
Blocked by:

## Question

Do we build a second broker adapter in Phase 4, or defer?

Ground: roadmap §17 Phase 4 ("Second broker adapter only if needed"), FR-002 (Dhan is primary; others through OpenAlgo abstraction — but OpenAlgo is NOT a runtime dep per the July 12 reset; read that tension), `core/interfaces/` protocols exist (D1), FR-006 composition-over-fork, D2/D11 single-operator.

Sharpen: what would trigger "needed" (a concrete broker, a concrete capability Dhan lacks), which protocols would need second implementations, licensing/credential shape, and the honest cost of carrying a second adapter in a single-operator platform.

## Answer
DECIDED-DEFER: no concrete second broker need; Dhan stays primary (FR-002); protocols isolate the seam. Trigger for reopening: a concrete broker or missing Dhan capability.

## Re-evaluation — 2026-08-06 (Phase 7 Wave 4, roadmap #13)

Status: DECIDED-DEFER — unchanged; trigger un-fired.

Evidence (live codebase, read-only):
- Fyers migration complete: `src/shettyxtreme/integration/` contains only `integration/fyers/` (11 modules). Dhan survives as legacy comments (`order_validator.py:7-26`), credential migration (`auth/credential_store.py:89-103`), and the legacy `/api/postback/dhan` webhook (`terminal/api/postback_router.py:137-141`).
- Config default is Fyers (`core/config/config_manager.py:47` — `broker: str = "fyers"`); no second-broker adapter code exists anywhere in `src/`.

Trigger ("concrete broker need or missing Fyers capability"): NOT met. Fyers covers the Dhan-era capability set (data socket, order WS, option chain, entitlement surfacing via `FyersDataEntitlementError`).

Verdict: **KEEP DEFERRED.** Re-open only on a concrete second-broker requirement or a missing Fyers capability.