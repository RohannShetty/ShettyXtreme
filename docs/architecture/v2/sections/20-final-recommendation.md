# Section 20 — Final Recommendation

## 1. Architecture stance

**Standalone modular monolith, interface-driven, event-driven, DhanHQ-py 2.2.0 as the only runtime pip dependency, OpenAlgo vendored not imported, web terminal.**

- **Standalone modular monolith** — one process, one operator; strict internal boundaries with three speeds: stable core, swappable intelligence, fast UI ([Section 18 — Repo & Codebase Strategy](18-repo-codebase-strategy.md)).
- **Interface-driven** — `core/interfaces` protocols are the seams: broker, data feed, voters. Adaptations implement protocols; nothing imports vendor code ([Section 06 — Proposed Architecture](06-proposed-architecture.md)).
- **Event-driven** — `core/event_bus` (Topic/Event) carries market data, signals, and outcomes through the pipeline; modules observe, never poll each other.
- **DhanHQ-py 2.2.0 only** (MIT, pinned — corrected fact 5; 2.3.0rc1 diffed, not adopted). No OpenAlgo runtime dependency, no OpenAlgo server, no `import openalgo` anywhere in `src/` (per D1). OpenAlgo code lives in `vendor/openalgo/` (tracked, AGPL-3.0, origin-stamped, synced monthly per D1) as **adaptation source only** ([Section 10 — OpenAlgo Utilization](10-openalgo-utilization.md)).
- **Web terminal** — Svelte+Vite served by FastAPI (per D9), governed by DESIGN.md (per D4). Not a TUI.

## 2. Product stance

**India-first options intelligence + execution workstation, private use, OBSERVER-first, semi-auto.**

- **India-first**: NSE/BSE index options (NIFTY/BANKNIFTY weekly) as the primary intelligence + execution pipeline; equities/indices as terminal breadth (per D6; [Section 04 — India-First Scope](04-india-first-scope.md)).
- **Options-first pipeline**: chain → features → regime → signal/conviction → options EV → risk → execution-awareness → operator-facing explanation ([Section 14 — Data, Decision & Intelligence](14-data-decision-intelligence.md)).
- **Private use** (per D2/D11): no SaaS, no licensing, no signal sales, no community — monetization is trading edge + prop-style scale ([Section 16 — Monetization & Business](16-monetization-business.md)).
- **OBSERVER-first** (per D10): LIVE is an explicit per-session action with confirmation. Semi-auto execution: intelligence proposes, the operator approves. Learning loop throughout.

## 3. First implementation slice — Phase 2 pipeline completion

Ordered task list; each task lands with its test gate from [Section 17 — Delivery Roadmap](17-delivery-roadmap.md). No task after a red suite.

1. **Implement `VoterRegistry`** — replace the pass-stub with the plugin registry (`core/interfaces` protocols); gates: registry discovery tests.
2. **Create `intelligence/hints/strategy_hints.py`** — real strategy-hint computation; wire `/strategy-hint` endpoint; kills the 501 (`test_get_strategy_hint`).
3. **Create `intelligence/conviction/conviction_engine.py`** — replace the docstring-only `__init__` import; conviction metrics flow into hints and signals.
4. **Wire `/options` endpoint** — serve the option chain through `DhanDataAdapter.get_option_chain`; kills the 501 (`test_get_options`).
5. **Fix feed request codes** — `DhanDataAdapter` subscribes with codes 15/17/21 (Ticker/Quote/Full), unsubscribes code+1, stops passing response codes 2/8 (corrected fact 2).
6. **Credential fallback slot + 806 surfacing** — optional `data_access_token` via PIN/TOTP `generateAccessToken` flow (per D8); 806 → "subscribe to Data APIs" entitlement message (corrected fact 1).
7. **OBSERVER default fix** — mode defaults OBSERVER, LIVE requires per-session confirmation; mode persistence fixed; `test_execution_mode_default` green (per D10).
8. **Landmine cleanup** — dead imports (`intelligence/hints`, `intelligence/conviction` `__init__`s), stale conftest fixtures (`integration.openalgo`, `dhan_adapter.DhanAdapter`), empty dirs (`execution/lifecycle/`, `execution/position_tracker/`, `tests/risk/`, `tests/integration/`), populate `core/errors/__init__.py`.
9. **Svelte+Vite terminal** — replace static HTML with the Svelte app per DESIGN.md; panel set per [Section 15 — Design System & Terminal UX](15-design-system-terminal-ux.md).
10. **Full suite green** — 495+ tests passing; resolve `test_matches_builtin_black76` (quantlib env, pinned not skipped).
11. **`run.py` operator flow** — browser-open + uvicorn, explicit `--mode` flag, LIVE confirmation prompt.

Exit validation: full session in OBSERVER with live Dhan data — chain, hints, signals, risk meters, and terminal render; every gate green.

## 4. What to intentionally NOT build first

| Not building | Until | Why |
|---|---|---|
| Multi-leg strategy constructor | Single-leg edge proven (Phase 3 data) | Margin complexity without proven thesis (per [Section 08 — Feature Map](08-feature-map.md)) |
| ML/RL models | Pipeline + data volume justify it | Overfitting risk dwarfs value ([Section 19](19-risks-failure-modes.md)) |
| Multi-broker | Phase 4, optional | Protocols exist; Dhan must be flawless first (per D1) |
| SaaS / billing / multi-tenancy | Never | D2/D11 |
| Knowledge auto-activation | Phase 4, human-gated only | D12 contamination wall |
| Telegram/email as primary interface | Never as primary | Terminal is the surface; alerts are push within it |
| Community/forum | Never | D2 + seductive distraction |

## 5. Maximizing long-term upside without drowning

1. **Composition over fork** for external libraries — DhanHQ-py as pip dep, pinned (corrected fact 5).
2. **Vendoring over import** for OpenAlgo — adapt, never import (per D1); monthly upstream diff cadence keeps the vendor zone honest (~3 releases/mo, corrected fact 3).
3. **Shadow over activate** for new intelligence — ≥20-session gates, always.
4. **Observer over live** for every new capability — watch it work before risking capital (per D10).
5. **Probabilistic over predictive** — conditions and calibrated probabilities, never predictions ([Section 14](14-data-decision-intelligence.md)).
6. **Human-gated knowledge** — D12 physical separation; ingestion can inform, never command.
7. **Cost-aware from day one** — brokerage + slippage + STT inside every EV; no marginal strategy passes as profitable ([Section 16](16-monetization-business.md)).
8. **DESIGN.md as UI guardrail** — every panel change flows through the contract (per D4).
9. **Learning loop as the moat** — immutable outcomes, consumed voter quality, calibration; edge compounds in the ledger, not in memory.
10. **Phase gates as the brake** — the roadmap ([Section 17](17-delivery-roadmap.md)) and the risk register ([Section 19](19-risks-failure-modes.md)) are followed as written; the one-operator advantage is speed, and its cost is discipline.

The recommendation in one sentence: **build the Phase 2 pipeline completion first and nothing else, keep the boundaries enforced, and let the scorecard decide everything after.**
