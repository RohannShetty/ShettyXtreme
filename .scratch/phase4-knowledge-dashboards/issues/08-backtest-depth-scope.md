# 08 — Backtest depth: scope decision

Type: grilling
Status:
Blocked by:

## Question

What does backtest depth beyond the Phase-3 walkforward mean for v1, and is it in scope for Phase 4?

Ground: roadmap §17 Phase 4 ("Historical walkforward harness depth beyond Phase 3; strategy comparison surfaces"), section 14 walkforward honesty (premium/cost/TP-SL-EOD evaluation, per-voter and per-regime breakdowns already exist), the 0-skipped + ≤500-line gates.

Sharpen: which of — (a) deeper walkforward parameters (more regimes, longer history, parameter sweeps), (b) a strategy-comparison surface (side-by-side reports in the terminal), (c) a separate backtest runner — is worth building now, and what the honest value is for a live-trading single operator whose edge is the deterministic engine, not backtest theater.
