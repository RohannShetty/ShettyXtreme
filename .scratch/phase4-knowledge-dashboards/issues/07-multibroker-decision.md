# 07 — Multi-broker: build or defer?

Type: grilling
Status:
Blocked by:

## Question

Do we build a second broker adapter in Phase 4, or defer?

Ground: roadmap §17 Phase 4 ("Second broker adapter only if needed"), FR-002 (Dhan is primary; others through OpenAlgo abstraction — but OpenAlgo is NOT a runtime dep per the July 12 reset; read that tension), `core/interfaces/` protocols exist (D1), FR-006 composition-over-fork, D2/D11 single-operator.

Sharpen: what would trigger "needed" (a concrete broker, a concrete capability Dhan lacks), which protocols would need second implementations, licensing/credential shape, and the honest cost of carrying a second adapter in a single-operator platform.
