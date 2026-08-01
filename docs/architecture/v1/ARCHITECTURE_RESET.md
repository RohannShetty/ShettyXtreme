# ShettyXtreme Architecture Reset — July 12, 2026

## Decision: ShettyXtreme is STANDALONE Software

**User directive (2026-07-12):** ShettyXtreme must be independent software with NO runtime dependency on OpenAlgo or any third-party service. Patterns and code are absorbed/copied/modified from reference repos, but ShettyXtreme runs as standalone individual software.

## What Changed

### Prior approach (COMPOSITION with OpenAlgo):
- ShettyXtreme calls OpenAlgo's REST API at runtime
- OpenAlgo runs as a separate process
- ShettyXtreme is a client of OpenAlgo

### Corrected approach (ABSORB from OpenAlgo):
- ShettyXtreme is self-contained — no external services needed at runtime
- OpenAlgo's best patterns (broker adapter pattern, WebSocket architecture, order validation) are absorbed as FIRST-PARTY code
- DhanHQ-py remains a pip dependency (library, not service — acceptable)
- Upstream OpenAlgo changes are tracked and selectively absorbed via human review

## Impact on Existing Code

The existing Phase 1+2 code in the repo has:
- `integration/openalgo/` adapter — **MUST BE REMOVED**
- `integration/dhan/dhan_adapter.py` — **MUST BE REFACTORED** to be fully standalone (currently delegates to OpenAlgo patterns)
- `terminal/` — Textual TUI — **MUST BE REPLACED** with web-based UI
- No cost model — **MUST BE ADDED**
- No conviction metric — **MUST BE ADDED**
- No regime classifier — **MUST BE FIXED** (no Markov on 1m noise)

## New Architecture Summary

- **Core**: Domain models, event bus, contracts, config, storage — ZERO external imports
- **Integration**: Dhan Trading + Dhan Data adapters (first-party, DhanHQ-py pip dep only)
- **Intelligence**: Feature engine, regime classifier, signal engine (conviction, D/P/G, voter plugins), options intelligence, risk engine, scanners — imports core only
- **Execution**: Order lifecycle, position management (TP3 FIXED), semi-auto approval
- **Learning**: Outcome tracking, MFE/MAE, walkforward (honest evaluation), calibration
- **Terminal**: FastAPI backend + web frontend (using taste-skill + ui-ux-pro-max-skill)
- **Knowledge**: Phase 3+ — document store, tagger, heuristic extractor (physically separated from intelligence)
- **Observability**: Structured logging, metrics, health checks

## Test Gates

Every wave must pass:
1. All previous wave test gates still pass (no regressions)
2. `grep -r "import openalgo\|from openalgo" src/` → ZERO matches
3. No file > 500 lines (no god modules)
4. `core/` has zero external imports
5. `PYTHONPATH="" python -m pytest tests/ -v --tb=short` → ALL PASS

## UI/UX Skills

Terminal UI will use:
- https://github.com/leonxlnx/taste-skill (design taste/quality)
- https://github.com/nextlevelbuilder/ui-ux-pro-max-skill (UI/UX excellence)

Both are being studied for integration into the web-based terminal interface.