# P2-3.3 — Risk Heat Map: Findings

**Date:** 2026-08-12
**Ticket:** P2-3.3 — Risk Heat Map (sectoral exposure, greeks concentration, max-loss scenario, margin utilization)
**Layer:** `intelligence/risk/` (backend aggregation) + `terminal/api/execution_router.py` + `terminal/web/src/components/` (frontend)
**Doc status:** Findings only — algorithm direction, not code. Spec/plan to follow.

---

## Executive summary

There is a **working risk pipeline** (filter-chain `RiskEngine`, `RiskBusBridge` →
`RISK_DECISION` events, `RiskProjection`, `/api/execution/risk`, and a frontend
margin bar), but it is **entry-gating only and position-agnostic**. None of the four
heat-map dimensions exist today:

| Dimension | Exists? | Where |
|---|---|---|
| Sectoral exposure | ❌ No | Zero sector/industry classification anywhere in the codebase |
| Greeks concentration | ⚠️ Primitives only | `options/greeks.py` computes per-option greeks; no portfolio aggregation; `Position` carries no option metadata |
| Max-loss scenario | ⚠️ Per-strategy only | `options/strategy_analyzer.py` has payoff math; no scenario engine (±5%/±10% spot) |
| Margin utilization | ⚠️ UI bar exists, data path broken | `PositionsRiskStrip.svelte` renders a bar; but `margin_used` is never populated live (poller drops Fyers `utilized`) |

The single biggest blocker: **the `Position` dataclass and `PositionProjection` strip
all option metadata** (strike/expiry/option_type) and carry no greeks, no lot size,
and no underlying spot. Every heat-map dimension must be re-derived from the
instrument master + Black-76 rather than read from position state.

---

## 1. Current risk architecture (what exists)

### 1.1 Backend risk layer — `src/shettyxtreme/intelligence/risk/`

- **`risk_engine.py`** — `RiskEngine` (line 196) runs a composable filter chain:
  `LossLimitFilter`, `MarginFilter`, `MaxPositionFilter`, `RegimeFilter` (stub —
  `is_stub = True`, always ALLOW, line 157-190). `Portfolio` is a minimal dataclass
  (positions, daily_pnl, total_margin_used, available_margin — line 21-27).
  `RiskDecision` carries allowed/reason/filter_name for audit. **Entry-gating only**;
  `check_position_management` always ALLOWs (by design, D10).
- **`cost_model.py`** — `compute_cost` (slippage/brokerage/STT/exchange), `adjust_ev`,
  `check_marginal`. Not heat-map relevant.
- **`bus_bridge.py`** — `RiskBusBridge` subscribes `POSITION_CHANGED` + `MARKET_DATA_TICK`
  and publishes `RISK_DECISION` with `{daily_pnl, margin_used, margin_available,
  loss_limit, loss_limit_hit, max_positions}`. This is the natural **extension point**
  to publish enriched risk/heat-map payloads.

### 1.2 Projections — `src/shettyxtreme/terminal/projections.py`

- **`PositionProjection`** (line 143) — subscribes `POSITION_CHANGED`; stores per symbol
  only: `{symbol, exchange, quantity, buy_avg, net_quantity, m2m, pnl, product}`.
  **Drops strike/expiry/option_type/lot_size — nothing option-specific survives.**
- **`RiskProjection`** (line 185) — subscribes `RISK_DECISION`/`RISK_ALERT`; state is
  `{daily_pnl, margin_used, margin_available(None=unknown), loss_limit,
  loss_limit_hit, max_positions}`.

### 1.3 API — `src/shettyxtreme/terminal/api/execution_router.py`

- `GET /api/execution/positions` (line 188) → `PositionResponse`
  (`models.py:138` — no greeks/sector/option fields).
- `GET /api/execution/risk` (line 207) → `RiskResponse` (`models.py:149` —
  daily_pnl, margin_used, margin_available, loss_limit, loss_limit_hit,
  max_positions, active_positions).

### 1.4 Margin plumbing — `src/shettyxtreme/terminal/api/app.py`

- `_margin_poll_loop` (line 115) polls `trading_adapter.get_margin()` every 30s and
  publishes **only `margin_available`** via `RISK_DECISION`.
- **Bug (relevant to this ticket):** Fyers `get_margin()` (`trading_adapter.py:426`)
  already returns `{available, utilized, total}` — but the poller's
  `_MARGIN_AVAILABLE_KEYS = ("availabelBalance", "availableMargin", "available", "balance")`
  (line 96) only extracts *available*. `utilized`/`total` are **discarded**, so
  `margin_used` in the projection stays `0.0` in the live path (only paper mode
  publishes non-zero values via `paper_trading.py:225`, and even that event
  `{symbol, side, quantity, price}` carries no `margin_used`).
  → The frontend margin bar's numerator is effectively always 0 outside paper mode.

### 1.5 Frontend

- **`PositionsRiskStrip.svelte`** (`terminal/web/src/components/`, mounted in `App.svelte:312`)
  — bottom strip: positions table + risk block with **margin bar**
  (`marginRatio = margin_used / (margin_used + margin_available)`, lines 75-86),
  breach chip (`margin_used > margin_available`), warn chip (>80%), LOSS LIMIT HIT
  chip, `active/max POSITIONS` chip.
- **No `RiskHeatmap.svelte` exists** (glob confirmed). `AnalyticsPanel.svelte` renders
  scorecard metrics + calibration curve + regime chips — not risk.
- DESIGN.md §15/`docs/architecture/v2/...08-feature-map.md:16` lists **"sector heatmap"**
  as an MVP-essential *market internals* widget — so a heatmap is a planned surface,
  just never built. DESIGN.md color contract: red `#f6525c` = up/positive,
  green `#2ebd85` = down/negative, `warning` `#ffb020`, `danger` `#e5484d` — heat
  intensity should follow this (never "fix" the red/green convention).

---

## 2. Gap analysis per dimension

### 2.1 Sectoral exposure — ❌ completely missing

- `grep -r "sector\|industry"` in `src/` → **zero matches** in Python source
  (only test fixtures/lexicons mention "IT sector" as tagger *text*).
- Instrument master (`integration/fyers/instrument_master.py`) schema has
  `internal_symbol, exchange, instrument_type, expiry, strike, option_type,
  lot_size, tick_size, isin, raw_json` — **no sector/industry column**.
  `raw_json` may hold more master fields but nothing sector-like is parsed.
- No symbol→sector map exists anywhere.

**Reusable seed:** `isin` (or `internal_symbol`) + a **static curated sector map**
(mirroring the `core/knowledge/lexicons.py` pattern — pure data, no imports) is the
pragmatic v1. Fyers master itself does not carry sector membership.

### 2.2 Greeks concentration — ⚠️ primitives exist, aggregation doesn't

- `options/greeks.py` — `GreeksCalculator.calculate_all(spot, strike, tte, iv,
  option_type)` → Black-76 `{delta, gamma, theta, vega, rho}` (per unit).
- `options/quantlib_pricer.py` — optional QuantLib backend (default off).
- `intelligence_router.py:_enrich_chain` (line 278) already computes per-contract
  greeks from chain rows — **the pattern to reuse** for positions.
- **Blockers for portfolio aggregation:**
  1. `Position`/`PositionResponse` carry **no strike/expiry/option_type** — the
     chain fields ride `Tick` (P6-W2, `market_data.py:24-25`) and `ProposalResponse`
     (`models.py:197-199`), but not `Position`. Instrument master lookup
     (`from_fyers`/`search`) can recover this from the fyers ticker.
  2. **IV is REST-only** (HSM feed has no IV — comment at `projections.py:63`), so
     per-position IV must come from the primed chain (REST) or be approximated.
  3. **Lot size** needed to scale unit-greeks → portfolio greeks; available from
     instrument master (`lot_size` column) or `WatchlistProjection` (`lot_size` field).
- No existing `sum(delta*net_qty*lot_size)` aggregation anywhere.

### 2.3 Max-loss scenario — ⚠️ per-strategy payoff exists, no scenario engine

- `options/strategy_analyzer.py` — `StrategyAnalyzer.analyze()` returns
  `max_profit/max_loss/breakevens/payoff_at_expiry` for 9 named strategies
  (long/short call/put, spreads, iron condor, straddle/strangle). **Expiry payoff
  only** — single-position math, not a portfolio stress test.
- **No ±5%/±10% spot-move scenario engine exists.** No code shifts spot and
  re-prices the book.

### 2.4 Margin utilization — ⚠️ UI exists, backend data path broken

- UI: yes — `PositionsRiskStrip.svelte` margin bar + chips (see §1.5).
- Backend: `margin_used` never populated in the live path (§1.4 bug). `get_margin()`
  already returns `utilized` — wiring it through the poller fixes the numerator.
- No explicit "margin limit" config — ratio is computed vs `used+available`.
  `MarginFilter.margin_threshold_ratio=0.1` is a per-entry safety ratio, not a limit
  meter. DESIGN.md asks for "margin-used vs limit"; the limit source of truth is
  Fyers `fund_limit` total.

---

## 3. Proposed fix approach (algorithm direction, not code)

### 3.1 New backend aggregator — `intelligence/risk/portfolio_risk.py` (new module)

A pure, EventBus-agnostic **`PortfolioRiskAggregator`** computing all four dimensions
from inputs `{positions, instrument_master, spot_map, iv_map, margin}`:

1. **Enrichment pass** — for each position, resolve option metadata via instrument
   master (strike/expiry/option_type/lot_size/instrument_type) + underlying spot
   (watchlist tick LTP) + IV (primed chain). Positions without resolution degrade to
   "unknown" buckets — never fake zeros (honesty rule already used for margin).
2. **Sectoral exposure** — group `net_quantity × buy_avg` notional (or `m2m`) by
   sector via the curated symbol→sector map; output per-sector `{sector, notional,
   pnl, share_pct}` sorted descending.
3. **Greeks concentration** — per position, `unit_greek × net_quantity × lot_size`
   (delta scaled by lot size for index options); sum across the book →
   `{delta, gamma, theta, vega}` with long/short breakdown; flag lopsided
   profiles (e.g. `|theta| >> |vega|` = all theta, no vega).
4. **Max-loss scenario** — for shifts in `{-10%, -5%, +5%, +10%}`:
   option legs repriced via Black-76 (`GreeksCalculator`) at shifted spot;
   futures/equity legs via `(Δspot × net_quantity)`. Report worst case + per-scenario
   P&L. (StrategyAnalyzer payoff math is an alternative for expiry scenarios only.)
5. **Margin utilization** — `margin_used` from `get_margin()["utilized"]`,
   `margin_available` as today; emit `utilization_pct` + breach state.

### 3.2 Data-flow changes

- **Fix the poller** (`app.py:_margin_poll_loop`): also publish `margin_used`
  (`utilized`) and optionally `total` — this alone repairs the existing UI bar.
- **Publish enriched payloads**: `RiskBusBridge` (or a sibling bridge) emits a new
  `RISK_DECISION`-style event (or a new `Topic` in `core/event_bus/event_bus.py`) with
  `{sector_exposure, greeks, stress, margin}`; `RiskProjection` stores + broadcasts.
- **New endpoint**: `GET /api/execution/risk/heatmap` → new response models in
  `terminal/api/models.py` (reuse the `RiskResponse`-style degraded-to-empty contract:
  missing data → empty lists / `None`, never 500).
- **Extend `PositionResponse`** with `instrument_type` (+ optional strike/expiry)
  so the frontend can render per-position context without extra lookups.

### 3.3 Frontend — new `RiskHeatmap.svelte`

- Mount in the positions/risk row (`App.svelte` bottom strip) alongside
  `PositionsRiskStrip`, or as a tab — follow DESIGN.md panel taxonomy (bottom strip,
  min 240px tall).
- Render four blocks, plain CSS/SVG (no chart lib — repo convention per
  `.scratch/phase4...issues/05`):
  1. **Sector grid** — heat cells (sector × notional share), intensity scaled by
     `share_pct`; color by P&L sign per DESIGN.md red/green convention.
  2. **Greeks bar** — delta/gamma/theta/vega magnitudes, long vs short split.
  3. **Stress table** — rows `-10% / -5% / +5% / +10%`, worst-case highlighted
     with `danger`.
  4. **Margin gauge** — reuses the existing bar/chip pattern from
     `PositionsRiskStrip.svelte` (now with a working `margin_used`).
- Reuse existing UI primitives: `ScrollArea`, `Table`, chips, `EmptyState`,
  `LoadingState`, `ErrorState` (all already in the strip).

---

## 4. Reusable existing code (do not reinvent)

| Need | Reuse |
|---|---|
| Per-option greeks | `options/greeks.py` `GreeksCalculator` (Black-76, pure Python; quantlib optional) |
| Chain greeks enrichment pattern | `terminal/api/intelligence_router.py:_enrich_chain` (line 278) |
| Per-strategy payoff / max loss | `options/strategy_analyzer.py` `StrategyAnalyzer` (payoff_at_expiry, max_loss) |
| Symbol→metadata (strike/expiry/type/lot_size/isin) | `integration/fyers/instrument_master.py` (`lookup`/`search`/`from_fyers`) |
| Underlying spot | `WatchlistProjection` ticks (`projections.py:44`), `Tick` carries strike/option_type for option ticks |
| IV source | primed chain (`intelligence_router.py:prime_options_chain`) — REST-only |
| Margin used/available | `trading_adapter.get_margin()` already returns `{available, utilized, total}` (fix poller to use `utilized`) |
| Risk event plumbing | `RiskBusBridge` + `RISK_DECISION` topic; `RiskProjection` state/broadcast pattern |
| API contract style | `execution_router.get_risk` + `RiskResponse` (degrade to empty, never 500) |
| Curated static-map pattern | `core/knowledge/lexicons.py` (pure-data vocab maps — template for symbol→sector) |
| Frontend strip/panel shell | `PositionsRiskStrip.svelte` (margin bar, chips, table) |
| Design tokens | DESIGN.md §2 palette (red=up `#f6525c`, green=down `#2ebd85`, warning `#ffb020`, danger `#e5484d`), spacing scale, panel taxonomy §15 |

---

## 5. Constraints & gotchas

- **Layered architecture:** new aggregator lives in `intelligence/risk/` (imports
  `core/` + `options/` only — `options/` is fine, it's the pricing module; **must not**
  import `integration/` directly). Master lookups must come in via dependency
  injection (like `_portfolio_provider` in `app.py:370`) or a `core/interfaces`
  Protocol — the risk layer cannot reach into `integration/fyers/` itself.
- **Honesty rule (fix #2):** unknown margin/sector/greeks → `None`/empty, never
  fabricated zeros in the UI (already enforced for margin; extend to heat-map cells).
- **OBSERVER-first (D10):** heat map is read-only analytics — no interaction with
  execution paths needed.
- **No new deps:** greeks/stress math is pure Python + stdlib (repo norm).
- **Test gates:** full suite is 1012 tests; new aggregator needs tests under
  `tests/intelligence/` (existing `test_risk_engine.py` / `test_risk_settings_backend.py`
  are the home). No `import openalgo` anywhere. `npm run check` must stay 0 errors.
- **Sector map maintenance:** static map is fine for v1 (NIFTY/BANKNIFTY + watched
  equities); note in the plan that Fyers master has no sector field, so a curated
  `symbol→sector` dict is the source of truth.
