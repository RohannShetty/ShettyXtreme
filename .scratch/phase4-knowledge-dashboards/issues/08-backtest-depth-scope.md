# 08 — Backtest depth: scope decision

Type: grilling
Status:
Blocked by:

## Question

What does backtest depth beyond the Phase-3 walkforward mean for v1, and is it in scope for Phase 4?

Ground: roadmap §17 Phase 4 ("Historical walkforward harness depth beyond Phase 3; strategy comparison surfaces"), section 14 walkforward honesty (premium/cost/TP-SL-EOD evaluation, per-voter and per-regime breakdowns already exist), the 0-skipped + ≤500-line gates.

Sharpen: which of — (a) deeper walkforward parameters (more regimes, longer history, parameter sweeps), (b) a strategy-comparison surface (side-by-side reports in the terminal), (c) a separate backtest runner — is worth building now, and what the honest value is for a live-trading single operator whose edge is the deterministic engine, not backtest theater.

## Answer
DECIDED-DEFER: no new backtest surface in Phase 4; walkforward stays as-is (live edge = deterministic engine; backtest theater risk).

## Re-evaluation — 2026-08-06 (Phase 7 Wave 4, roadmap #13)

Status: DECIDED-DEFER — unchanged; trigger un-fired.

Evidence (live codebase, read-only):
- Walkforward stays as-is: `src/shettyxtreme/learning/walkforward.py` (`WalkforwardEvaluator`, `WalkforwardResult`) — honest premium-based backtest; consumed by `tests/wave4/test_walkforward.py`.
- No strategy-comparison surface or separate backtest runner exists anywhere in `src/`; Phase 4-6 built none.

Trigger ("comparison-surface need"): NOT met. Live edge remains the deterministic engine (per the answer above; backtest-theater risk).

Verdict: **KEEP DEFERRED.** Re-open only if a strategy-comparison surface becomes a concrete requirement.