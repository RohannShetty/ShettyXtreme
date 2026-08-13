# P2-3.2 Findings — Greeks Dashboard (Real-Time)

**Date:** 2026-08-12 · **Status:** Investigation complete — no code changed

## TL;DR

Greeks are **computed but almost invisible**. A full Black-76 engine
(`GreeksCalculator`) plus a QuantLib path (`QuantLibPricer`, QuantLib 1.43
installed) exist, and per-strike greeks are computed server-side on every
`GET /api/intelligence/options` request — but:

- **Per-strike:** the greeks are in the API payload (`OptionsChainItem.delta/
  gamma/theta/vega`) and in `ChainGrid.svelte`'s `Contract` TS type, yet the
  grid **renders only Strike | LTP | IV | OI** — greeks never appear.
- **Per-position:** nothing. `PositionsRiskStrip.svelte` shows Symbol/Qty/Avg/
  M2M/P&L + margin. `PositionResponse` has no greeks (and no option identity).
- **Portfolio-level:** nothing. No `GreeksPanel.svelte`, no aggregation
  endpoint, no aggregation logic anywhere.
- **Real-time:** greeks are **not recomputed on tick** and never broadcast.
  The WS `tick` payload carries `ltp/oi/strike/option_type` but no greeks (IV
  is absent from the HSM feed by design). Greeks refresh only via the chain's
  quiet 15 s REST poll — and only while ChainGrid is mounted.

---

## 1. Greeks computation — WHAT EXISTS (complete)

### `src/shettyxtreme/options/greeks.py` — `GreeksCalculator` (Black-76)

Pure-Python Black-76 (futures/indices convention, right for Indian index
options). No I/O, pure parameter→dict.

| API | Line | Notes |
|-----|------|-------|
| `calculate_all(spot, strike, tte, iv, option_type, rate=0.0)` | 73 | Returns `{delta, gamma, theta, vega, rho}` |
| `calculate_delta` | 151 | delegates to `calculate_all` |
| `calculate_gamma` | 163 | own impl (same for call/put) |
| `calculate_theta` | 181 | delegates |
| `calculate_vega` | 193 | own impl |
| `calculate_option_price` | 209 | Black-76 premium |
| `_zero_greeks()` | 233 | guard: all-zero dict |

Conventions: theta per calendar day (`/365`), vega per 1% IV change (`/100`),
rho per 1% rate change (`/100`). Zero-guards on `tte <= 0`, `iv <= 0`,
`spot <= 0`, `strike <= 0` — never NaN/crash. `use_quantlib=True` delegates to
`QuantLibPricer.compute_greeks`, falling back to pure Python on ImportError.

### `src/shettyxtreme/options/quantlib_pricer.py` — `QuantLibPricer`

Wraps QuantLib with `ql.India(ql.India.NSE)` calendar + Actual/365 fixed:
- `compute_greeks()` (166) via `AnalyticEuropeanEngine` — returns the same
  five greeks **plus `price`**; theta `/365`, vega `/100`, rho `/100`.
- Also `price_european` (106), `price_american` (136, BaroneAdesiWhaley),
  `build_vol_surface` (204), `calibrate_sabr` (238), business-day helpers.

**Environment facts:**
- QuantLib **1.43 is installed** in `.venv` (`import QuantLib` works — module is
  capital-Q; the file imports `import QuantLib as ql` at line 28).
- QuantLib is **NOT declared in `pyproject.toml`** (no match for `QuantLib`/
  `quantlib`) — an undeclared venv dependency. Any plan that enables the
  QuantLib path must declare it first.
- The only production call site hardcodes `use_quantlib=False`
  (`intelligence_router.py:287`) — **production never uses QuantLib**, even
  though it's installed. There is no config flag for it.

Tests: `tests/options/test_greeks.py` (`TestGreeksCalculator`, `TestHelpers`),
`tests/options/test_quantlib_pricer.py`.

---

## 2. Current greeks usage — ONE call site only

| Consumer | Where | What it does with greeks |
|----------|-------|--------------------------|
| `GET /api/intelligence/options` → `_enrich_chain()` | `terminal/api/intelligence_router.py:278-329` | Computes per-strike greeks for every contract row; fills `OptionsChainItem.delta/gamma/theta/vega` (rho is **not** carried by the response model). Fresh `GreeksCalculator(use_quantlib=False)` per request. |
| Upstream Fyers `greeks=1` | `integration/fyers/data_adapter.py:457` | `get_option_chain` requests greeks from Fyers but **the raw rows are never parsed for greeks** — `_enrich_chain` recomputes its own and discards upstream values. Dead upstream data. |
| `options/__init__.py` | exports `GreeksCalculator` | only the re-export |

**Not used anywhere:** StrategyHints (`strategy_hints.py` — EV-based strike
selection via `options_intel.select_strike_by_ev`; no greeks), `StrategyAnalyzer`,
scanners, risk engine, analytics, research, knowledge. `GreeksCalculator` has
13 callers per codegraph, but all are the router + tests.

---

## 3. Portfolio-level greeks — MISSING (nothing)

- **No `GreeksPanel.svelte`** (glob for `*Greeks*.svelte` → no files).
- No aggregation endpoint (`/api/.../greeks` → no route anywhere).
- No aggregation logic (no sum of `qty × delta` anywhere).
- `AnalyticsPanel.svelte` = signal scorecard + calibration + regime — no greeks.
- `RightDockTabs.svelte` = Proposals / Research / Logs — no greeks.
- The "portfolio" that exists is P&L/margin only: `execution/paper_trading.py`
  `get_portfolio()`, `intelligence/risk/risk_engine.py` `Portfolio` — zero
  greeks fields.

## 4. Per-position greeks — MISSING (nothing)

- `PositionsRiskStrip.svelte`: positions table = Symbol, Qty, Avg, M2M, P&L;
  risk block = Daily P&L, margin bar, chips. **No greeks columns.**
- Backend: `PositionResponse` (`terminal/api/models.py:138`) = symbol/exchange/
  quantity/buy_avg/net_quantity/m2m/pnl/product. Core `Position` dataclass
  (`core/data_models/orders.py:104`) likewise. **Neither has greeks nor even
  strike/option_type/expiry** — option identity must be derived from the Fyers
  symbol string (see §Reuse — `from_fyers()`).
- `PositionProjection` (`terminal/projections.py:143`) broadcasts `position`
  events; PositionsRiskStrip reloads `/api/execution/positions` on them.

## 5. Per-strike greeks — COMPUTED but NOT RENDERED

- Backend **has** them: `OptionsChainItem` (`models.py:72`) has
  `delta/gamma/theta/vega`; `_enrich_chain` fills them per request.
- Frontend type **has** them: `ChainGrid.svelte:27-30` `Contract` includes
  delta/gamma/theta/vega; test fixture `ChainGrid.test.ts:56-58` includes
  values — but **no test asserts greeks render** and **no column renders them**.
- Rendered columns (`ChainGrid.svelte:414-474`): Strike | LTP | IV | OI (×CE/PE).
  The grid even has `bid/ask` in the type but shows neither those nor greeks.
- The core `OptionContract` dataclass (`core/data_models/market_data.py:33`)
  **has** `ltp/iv/delta/gamma/theta/vega` — but it is dead code: only
  re-exported through `core/data_models/__init__.py` and `core/interfaces/__init__.py`,
  never instantiated (the Fyers adapter returns raw dicts, `_enrich_chain`
  maps to the Pydantic model instead).

## 6. EventBus / real-time wiring — greeks NOT tick-driven

- **Topics** (`core/event_bus/event_bus.py:24-45`): `MARKET_DATA_TICK`,
  `MARKET_DATA_BAR`, `POSITION_CHANGED`, … **No greeks topic.**
- **Tick flow:** Fyers HSM feed → `Tick` (`market_data.py:13`) carries
  `strike/option_type/oi` (populated by `from_fyers()` in the adapter) but **no
  iv** (documented at `market_data.py:21-24`: "the HSM symbol-update feed has
  no IV field") → `WatchlistProjection.on_market_data`
  (`projections.py:50-95`) → WS broadcast `"tick"` with
  `symbol/ltp/change_pct/volume/oi/strike/option_type` — **no greeks, no iv**.
- **Frontend:** `TickPayload` (`web/src/lib/ws.ts:25-33`) matches — no greeks.
  `ChainGrid.applyTick` (178-209) mutates only ltp/iv/oi/bid/ask in place.
- **Recompute cadence:** greeks are computed only inside `_enrich_chain` per
  REST request — the chain's initial load + its **15 s quiet poll**
  (`REFRESH_MS`, `ChainGrid.svelte:59, 123-125, 257-269`). A tick that moves
  spot leaves the displayed greeks stale until the next poll. With a 50-strike
  × 2 row chain, pure-Python compute is cheap (no perf blocker to enabling it
  more often).
- `PositionProjection` → WS `"position"` → `PositionsRiskStrip` reloads REST —
  positions are also poll-driven, no greeks.

---

## 7. What's missing (summary)

1. **Per-strike visibility:** ChainGrid doesn't render the greeks it already
   receives (delta/gamma/theta/vega). Cheapest win.
2. **Per-position greeks:** no fields, no columns, no computation.
3. **Portfolio-level:** no panel, no endpoint, no aggregation.
4. **Real-time:** no tick-driven recompute, no greeks on the WS wire, 15 s
   staleness window (and greeks freeze entirely when ChainGrid isn't mounted,
   since the poll lives in that component).
5. **Config/parity:** `use_quantlib` hardcoded `False`; QuantLib undeclared in
   pyproject.toml; upstream Fyers greeks (`greeks=1`) fetched but discarded.
6. **rho:** computed by both engines but **dropped at the API layer** —
   `OptionsChainItem` has no `rho` field.

---

## 8. Proposed fix approach (algorithm, not code)

**Phase 1 — Per-strike rendering (data already flowing):**
- Add Δ/Γ/Θ/V columns to `ChainGrid.svelte` (or a per-strike detail row / an
  expandable "GREEKS" sub-grid, respecting DESIGN §8 table contract — no
  mid-row reflow, mono tabular numerals). Delta as signed (PE negative), theta
  shown with its decay sign; color with existing `price-up`/`price-down`
  tokens only where meaningful (Indian convention — never invent new colors).
- Extend `ChainGrid.test.ts` to assert greeks cells render (fixture already has
  values). Decide on rho: add `rho` to `OptionsChainItem` or leave out (state
  the choice).

**Phase 2 — Per-position greeks:**
- Derive option identity per position via `from_fyers(symbol)` (already
  returns `strike/option_type/expiry` — see §Reuse).
- Extend `PositionResponse` (and/or core `Position`) with optional
  `strike/option_type/expiry` + a greeks block.
- Compute per position: `position_greek = net_quantity × contract_greek`
  (sign: net_quantity sign gives long/short; delta flips sign for short puts).
  Inputs: spot from the live tick/chain spot, tte from `expiry - now`,
  **iv from the chain snapshot for that strike/side** (HSM tick has no IV —
  either reuse the last `/api/intelligence/options` response per symbol or
  maintain a thin per-strike IV snapshot refreshed on the chain poll).
- Add columns to `PositionsRiskStrip.svelte` (Δ, Γ, Θ/row, V) — the strip is
  the natural home.

**Phase 3 — Portfolio-level panel:**
- New aggregation module (e.g. `options/portfolio_greeks.py`, pure functions
  over position dicts) — net Δ/Γ/Θ/V = Σ position greeks; optionally broken
  down per expiry or per underlying.
- New endpoint, e.g. `GET /api/execution/portfolio-greeks` (positions already
  live under execution) returning the aggregate + per-position rows.
- New `GreeksPanel.svelte`: summary tiles (Net Δ, Γ, Θ, V, dollar/rupee delta
  optional) + per-position or per-strike table. Slot into `App.svelte` either
  as a new center tab (`activeTab.ts` `CenterTabId` — add `"greeks"`) or inside
  `PositionsRiskStrip`'s risk block. Follow `HintsPanel`/`AnalyticsPanel`
  staleness-chip pattern.

**Phase 4 — Real-time cadence (keep it cheap):**
- Recommended: keep server-side pure-Python compute (fast, consistent with
  today), refresh via (a) the existing 15 s chain poll, and (b) a new
  `portfolio-greeks` poll at the same cadence on the panel's own timer — no
  tick-path change needed for v1.
- Optional upgrade: extend the WS `tick` broadcast with greeks **only if** an
  IV source rides the tick; otherwise add a dedicated slow `greeks` WS topic
  (e.g. 5 s throttle) rather than per-tick storm. Do **not** compute greeks in
  the browser (engine parity + IV sourcing belong server-side).

**Phase 5 — Housekeeping:**
- Declare `QuantLib` in `pyproject.toml` if the QuantLib path is to be
  exercisable; add a config flag (`configs/default.yaml`) or env knob for
  `use_quantlib` instead of the hardcode at `intelligence_router.py:287`.
- Either parse upstream Fyers greeks (saves compute, vendor-supplied) or drop
  `greeks=1` — document the choice.
- Delete/rewire the dead `OptionContract` dataclass if unused after Phase 1-3.

---

## 9. Reusable code inventory

| Asset | Location | Reuse for |
|-------|----------|-----------|
| `GreeksCalculator.calculate_all()` | `options/greeks.py:73` | Every per-strike/per-position greeks computation (guards included) |
| `QuantLibPricer.compute_greeks()` | `options/quantlib_pricer.py:166` | Optional advanced path (installed, currently unused) |
| `_enrich_chain()` enrichment pattern | `intelligence_router.py:278-329` | Reference for mapping raw rows → greeks-bearing items |
| `OptionsChainItem` (delta/gamma/theta/vega) | `terminal/api/models.py:72` | Already in the `/options` payload — feed ChainGrid columns with zero backend change |
| `ChainGrid.svelte` `Contract` type + test fixture | `ChainGrid.svelte:22-35`, `ChainGrid.test.ts:32-60` | Test/data ready for greeks columns |
| `from_fyers()` symbol parser | `integration/fyers/symbols.py:373` | Derive `strike/option_type/expiry` from position symbols (per-position greeks) |
| `PositionsRiskStrip.svelte` layout | `components/PositionsRiskStrip.svelte` | Home for per-position greeks columns + portfolio risk-block pattern (chips/bars) |
| WS broadcast pattern (`ws_bridge.broadcast`) | `terminal/projections.py:87`, `api/ws_bridge.py` | Template for an optional `greeks` WS topic |
| Staleness-chip + tile patterns | `HintsPanel.svelte`, `AnalyticsPanel.svelte` | GreeksPanel UX (STALE chip, mono numerals, en-IN formatting) |
| Center-tab wiring | `App.svelte:236-268`, `lib/activeTab.ts` | Add a `"greeks"` center tab |
| Tests | `tests/options/test_greeks.py`, `test_quantlib_pricer.py`, `ChainGrid.test.ts` | Extend for per-position/portfolio aggregation |

---

## Appendix — key file:line index

| Concern | Location |
|---------|----------|
| Black-76 engine | `options/greeks.py:43-235` |
| QuantLib engine | `options/quantlib_pricer.py:51-292` |
| QuantLib installed (venv, undeclared) | `pyproject.toml` (absent); `.venv` has QuantLib 1.43 |
| Only greeks call site | `terminal/api/intelligence_router.py:287, 301` |
| Upstream greeks fetched, discarded | `integration/fyers/data_adapter.py:457` (`&greeks=1`) |
| API model carries greeks (no rho) | `terminal/api/models.py:72-84` |
| Dead OptionContract (with greeks) | `core/data_models/market_data.py:33-36` |
| WS tick payload (no greeks/iv) | `terminal/projections.py:87-95`; `web/src/lib/ws.ts:25-33` |
| ChainGrid renders LTP/IV/OI only | `web/src/components/ChainGrid.svelte:414-474` |
| ChainGrid 15 s poll (greeks staleness) | `ChainGrid.svelte:59, 123-125, 257-269` |
| Positions (no greeks, no identity) | `terminal/api/models.py:138`; `core/data_models/orders.py:104` |
| PositionsRiskStrip (no greeks columns) | `web/src/components/PositionsRiskStrip.svelte:98-119` |
| No GreeksPanel | glob `**/*Greeks*.svelte` → 0 files |
| No portfolio-greeks endpoint | grep routers → none |
| EventBus topics (no greeks) | `core/event_bus/event_bus.py:24-45` |
| Option identity parser (reusable) | `integration/fyers/symbols.py:373-434` |
| Center tabs (where a Greeks tab would go) | `web/src/lib/activeTab.ts:3`; `App.svelte:236-268` |
