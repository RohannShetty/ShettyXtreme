# Section 06 — Proposed Architecture

> The v2 architecture: layered modular monolith, event-driven pipeline from Dhan feed to execution, plugin voters, OBSERVER-default runtime modes (per D10), and a research workspace (Phase 3, per D3). Implements the boundary contracts of [Section 05](05-system-boundaries.md).

## Layer diagram

```
┌──────────────────────────────────────────────────────────────────┐
│ F. TERMINAL (FAST)   FastAPI REST+WS ──► Svelte SPA (D9/D4)      │
│     watchlist · intelligence · execution · scanner · settings     │
├──────────────────────────────────────────────────────────────────┤
│ E. LEARNING     OutcomeTracker · VoterQuality · MFE/MAE ·         │
│                 Walkforward · Calibration · Analytics             │
├──────────────────────────────────────────────────────────────────┤
│ D. EXECUTION    ExecutionEngine (semi-auto) · PaperTrading ·      │
│                 PositionManager (TP/TSL/EOD) · mode gate (D10)    │
├──────────────────────────────────────────────────────────────────┤
│ C. INTELLIGENCE (RAPID)  features O(1)/tick │ regime │ signals/   │
│     voters │ options (IV rank, PCR, strike EV) │ risk │ scanners  │
├──────────────────────────────────────────────────────────────────┤
│ A. CORE (STABLE)  domain models │ event bus (Topic/Event) │       │
│     interfaces (Protocols) │ config │ storage (KV+TS) │ session   │
├──────────────────────────────────────────────────────────────────┤
│ B. INTEGRATION (SWAPPABLE)  DhanTradingAdapter │ DhanDataAdapter  │
│     instrument master │ order validator │ credential/feed health  │
├──────────────────────────────────────────────────────────────────┤
│ EXTERNAL   DhanHQ-py 2.2.0 │ Dhan REST + api-feed WS (15/17/21)  │
└──────────────────────────────────────────────────────────────────┘
   G. KNOWLEDGE (Phase-4, imports core only, physically separated — D12)
   H. OBSERVABILITY (logs · metrics · health · audit — imports core)
```

Stable vs rapid: **A is stable** (ADR-gated), **B swappable**, **C rapid**, **D/E medium**, **F fast** (per Section 05).

## Services and modules

| Module | Layer | Responsibility |
|---|---|---|
| EventBus | core | asyncio pub/sub; `Topic` enum + `Event`; sole coupling point between pipeline stages |
| Storage | core | SQLite KV (state, config, instrument master) + DuckDB TS (bars, ticks, OI, feature history) |
| Session | core | market status state machine, runtime mode, calendar |
| DhanTradingAdapter | integration | orders, positions, holdings, margin, EDIS, auth refresh (per D8) |
| DhanDataAdapter | integration | feed WS (codes 15/17/21), historical, option chain, session health |
| FeatureEngine | intelligence | O(1)/tick streaming features |
| RegimeClassifier | intelligence | coarser-bar regime state |
| SignalEngine | intelligence | voter orchestration → conviction → D/P/G/NEUTRAL |
| OptionsIntel | intelligence | IV rank, PCR (time-of-day normalized), strike EV, strategy hints (per D6) |
| RiskEngine | intelligence | entries-only, cost-aware filter chain |
| Scanners | intelligence | gap detection, opportunity clusters |
| ExecutionEngine | execution | semi-auto approval, order lifecycle, mode gate (OBSERVER default per D10) |
| PositionManager | execution | TP1/TP2/TP3, TSL, EOD close 15:15 |
| PaperTradingEngine | execution | paper fills for simulation/paper modes |
| Learning | learning | outcome/voter-quality/calibration loops |
| Terminal | terminal | FastAPI REST + WS, Svelte SPA |
| Research workspace | (Phase 3, per D3) | agent roles, MCP exposure, brief drafting — human-gated, never orders |
| Knowledge | (Phase 4, per D12) | ingested content, physically separated |

## Core data flow

```
Dhan Data WS (codes 15/17/21)                          [integration]
   → DhanDataAdapter → EventBus MARKET_DATA_TICK
   → FeatureEngine (O(1)/tick) → FEATURES_COMPUTED
   → RegimeClassifier (coarser bars) → REGIME_CHANGED
   → SignalEngine: voters → conviction → D/P/G | NEUTRAL → SIGNAL_GENERATED
   → OptionsIntel: IV rank, PCR, strike EV → strategy hint (per D6)
   → RiskEngine (entries-only, cost-aware) → RISK_DECISION
   → [OBSERVER] display-only path → terminal panels
   → [LIVE, explicit per-session action] ExecutionEngine (semi-auto approve)
        → DhanTradingAdapter → ORDER_PLACED/FILLED/REJECTED → POSITION_CHANGED
   → Learning loop: outcome labels → voter quality → weight adjustments
```

Data is push-driven (bus events) from feed to risk; pull-driven (REST polling on cadence) for positions/holdings/multiquote LTP reconciliation.

## Event flow (Topic enum)

All inter-module communication is events on `core/event_bus/event_bus.py`:

| Topic | Producer → Consumer | Payload essence |
|---|---|---|
| `MARKET_DATA_TICK` | adapter → features, terminal | normalized tick |
| `MARKET_DATA_BAR` | features → regime, learning | 1m bar |
| `FEATURES_COMPUTED` | features → voters, terminal | `FeatureSet` dict |
| `REGIME_CHANGED` | regime → signal engine, terminal | regime state |
| `CONVICTION_CHANGED` | signal engine → terminal | conviction value |
| `SIGNAL_GENERATED` (SIGNAL_V2 exists as a legacy enum member) | signal engine → risk, execution, terminal | D/P/G + voters |
| `RISK_DECISION` | risk → execution, terminal | approve/block + reason |
| `RISK_ALERT` | risk → terminal, observability | breach alerts |
| `ORDER_PLACED/FILLED/REJECTED/UPDATED` | execution → portfolio, terminal | order lifecycle |
| `POSITION_CHANGED` | execution → portfolio/risk, terminal | position delta |
| `SCANNER_GAP` / `SCANNER_CLUSTER` / `SCANNER_LOG` | scanners → terminal | scan findings |
| `CONFIG_CHANGED` | config → all | hot-reload notice |
| `SYSTEM_STATUS` | session → terminal, observability | mode/session changes |
| `CREDENTIAL_HEALTH_CHANGED` / `CREDENTIAL_WARNING` | auth → terminal, observability | pre-open token health (per D8) |

New topics are added to the enum; the bus stays topic-typed (no stringly-typed routing).

## Market data ingestion (corrected facts)

- Feed request codes v2: **15 (Ticker) / 17 (Quote) / 21 (Full)**; unsubscribe = code + 1; disconnect = RequestCode 12; server error packets 805–809.
- **Latent bug (Phase-2 fix):** `DhanDataAdapter` currently sends codes 2/8 (response codes); the fix keeps codes and subscription bookkeeping in `integration/dhan/` only.
- 806 = Data-API subscription entitlement error, not credential mixing (per D8); the data-fallback slot (`data_access_token` via PIN/TOTP `generateAccessToken`) is used only if the consent token is rejected by the feed.
- Tokens expire ~03:00 IST daily; pre-open health check + refresh runs before 09:15 (per Section 04).
- Positions carry no LTP → portfolio/risk reconciles via `multiquote` polling (verified: src/shettyxtreme/integration/dhan/trading_adapter.py get_positions_with_ltp).
- Captured live data is persisted to DuckDB TS from day one so backtest/simulation have real data.

## Signal engine + voter plugin system

`intelligence/signals/` orchestrates `intelligence/voters/` plugins (breadth, micro, options_flow, orb, iv_rank, plus shadow voters in Phase 3):

- Each voter implements a Protocol (`voter_name`, `vote(features) → (direction, confidence)`), registered in `VoterRegistry` (Phase-2 stub today).
- SignalEngine aggregates votes → **conviction** (weighted, with correlation awareness added in Phase 3) → one of **D/P/G (Direction/Participation/Grouping) or NEUTRAL** (per pack conventions; `conviction/` landmine is Phase-2 scope).
- Shadow voters run alongside without affecting output until their `VoterQualityTracker` record justifies activation (learning-fed, per Phase 3).
- The engine is deterministic/statistical: LLMs never generate live signals (per D3).

## Feature engine

`intelligence/features/` computes streaming O(1)/tick features: bars, MA/EMA, ATR, ADX, VWAP, PCR, OI, IV — emitted as `FEATURES_COMPUTED`. O(1) per tick keeps 09:15–15:30 ingestion at full feed rate without queue buildup; regime classification consumes coarser bars to avoid noise overfitting.

## Options intelligence

`intelligence/options/` (per D6): IV rank, OI flow, PCR time-of-day normalized, strike selection via EV (strategy analyzer, quantlib pricer with Black-76), and the Phase-2 `get_option_chain` / `get_strategy_hint` implementations (replacing the 501 stubs). Outputs feed strategy hints to the terminal and strike bounds to the risk engine.

## Execution engine (semi-auto)

`execution/ExecutionEngine` implements the human-in-the-loop contract:

- **OBSERVER is the default mode** (per D10); LIVE is an explicit per-session user action with confirmation.
- Approved signals → order proposals → terminal approval panel → `DhanTradingAdapter` → order lifecycle events.
- `PositionManager` enforces TP1/TP2/TP3 (fixed ordering), TSL, EOD close (default 15:15); one canonical stop-loss definition (premium-relative, vol-aware).
- `PaperTradingEngine` fills orders in paper/simulation modes without touching the broker.

## Broker abstraction

`core/interfaces/` defines the ports; `integration/dhan/` provides the adapters (per D1, D8):

| Protocol | Capability | Adapter |
|---|---|---|
| `OrderExecutor` | place/modify/cancel orders | DhanTradingAdapter |
| `MarketDataStream` | subscribe, ticks, bars | DhanDataAdapter |
| `AccountInfo` | positions, holdings, funds, margin | DhanTradingAdapter |
| `BrokerGateway` | composed facade (OrderExecutor + MarketDataStream + AccountInfo) | DhanTradingAdapter |
| `DataProvider` | historical data | DhanDataAdapter |

Every layer above integration depends on these Protocols, never on DhanHQ-py. A second broker is a new adapter implementing the same Protocols (per Section 11); Dhan-first is preserved (per pack).

## Portfolio/risk state

`execution/` + `intelligence/risk/` maintain the live portfolio: positions reconciled from broker snapshots + multiquote LTP, exposure vs margin estimates (SPAN/VAR/ELM per Section 04), entries-only risk filter chain (no stop-loss mutation — canonical SL lives in execution). Risk state is persisted to SQLite KV so a restart restores the session view.

## Research workspace (Phase 3, per D3)

Agent roles (research, gate, critic, approve) exposed via MCP with human-approval loops; LLMs draft briefs/summaries only; live signal generation remains deterministic; the 5-stage research → gate → critic → approve → execute loop is Phase-3 scope (per Section 12). Outputs land in the Phase-4 knowledge layer, physically separated (per D12).

## Observability

`observability/` (imports core only): structured logging, per-stage latency metrics (tick → feature → signal), health checks, session audit log, credential health events (`CREDENTIAL_HEALTH_CHANGED`). Terminal renders logs/alerts panels from these read models.

## Plugin/adapter mechanism

- Voters, scanners, and strategies register via Protocols + `VoterRegistry`-style registries (no hardcoded imports).
- Adapters (broker, data) are selected via config `broker: dhan`, `data_provider` — `configs/default.yaml` today: `broker: dhan`, `dry_run: true`, `mode: observer`.
- Vendored OpenAlgo code is **never importable** (per D1); adaptations implement the same Protocols (per Section 07).

## Configuration and secrets

- **YAML + env:** `configs/default.yaml` (broker, mode, dirs, log level) overlaid by environment variables; pydantic-validated in core.
- **Fernet credential store:** `auth/CredentialStore` encrypts Dhan client_id + tokens at rest; `DhanOAuthHelper` runs the consent and PIN/TOTP flows; `TokenHealthMonitor` + `CredentialValidator` gate pre-open readiness (per D8).
- Secrets never enter config YAML or the event bus; credential events carry health status only.

## Storage model

| Store | Engine | Contents |
|---|---|---|
| KV | SQLite (`data/shetty_kv.db`) | instrument master, config, session state, signal log, trade log, credential metadata |
| TS | DuckDB (`data/shetty_ts.db`) | bars, ticks, OI history, option chain snapshots, feature history, outcome metrics |

Migrations live in `core/storage/`; instrument is a key, never a schema dimension (per Section 04 genericity).

## Runtime modes

| Mode | Data | Execution | Default | Use |
|---|---|---|---|---|
| Backtest | Historical | Simulated | — | Evaluation (walkforward, calibration) |
| Simulation | Live/Delayed | Simulated (PaperTradingEngine) | — | Tuning against live tape |
| Observer | Live | **Read-only display** | **YES (per D10)** | Monitoring; fixes `test_execution_mode_default` |
| Live | Live | Real, semi-auto, explicit per-session confirmation | — | Production (Phase 3+) |
| Paper | Live | Paper fills | — | Rehearsal |

Mode is session state in `core/`; LIVE requires a per-session explicit action (per D10).

## UI/backend boundary

FastAPI serves REST (state reads, commands) + WS (event push: ticks, signals, orders, logs); the Svelte SPA (per D9) renders per DESIGN.md (per D4). The backend is the only event-bus client; the SPA never touches the bus directly. REST commands (e.g., approve order, switch mode) are validated by the same layer rules as internal callers.

## Stable vs rapid summary

| Layer | Velocity | Gate |
|---|---|---|
| Core (A) | slow | ADR-only changes |
| Integration (B) | medium-high | adapter contract + validation suite |
| Intelligence (C) | rapid | boundary tests; no core leaks |
| Execution/Learning (D/E) | medium | contract tests |
| Terminal (F) | fast | DESIGN.md compliance (per D4) |

Cross-references: [Section 04 — India-First Scope](04-india-first-scope.md) (market realities feeding the pipeline), [Section 05 — System Boundaries](05-system-boundaries.md) (contracts), [Section 07 — Update-Resilient Design](07-update-resilient-design.md) (ACLs), [Section 11 — Dhan Integration](11-dhan-integration.md), [Section 14 — Data Decision Intelligence](14-data-decision-intelligence.md), [Section 17 — Delivery Roadmap](17-delivery-roadmap.md) (phasing), [Section 18 — Repo Codebase Strategy](18-repo-codebase-strategy.md).
