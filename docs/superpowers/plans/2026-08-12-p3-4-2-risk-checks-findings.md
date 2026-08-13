# P3-4.2 — Pre-Execution Risk Check Enhancement: Findings

**Date:** 2026-08-12
**Ticket:** P3-4.2 — Comprehensive pre-execution risk validation (max loss, portfolio heat, correlated exposure, cooldown)
**Layer:** `intelligence/risk/` (filter chain) + `execution/execution_engine.py` (flow) + `core/settings.py` (caps) + `terminal/api/` (alerts)
**Doc status:** Findings only — algorithm direction, not code. Spec/plan to follow.

---

## Executive summary

The current risk layer is **entry-gating only, order-agnostic, and thin**: a
composable filter chain (`LossLimitFilter`, `MarginFilter`, `MaxPositionFilter`,
`RegimeFilter`-stub) runs **once, at operator-approve time**, against a
**`Portfolio` snapshot that carries no equity and no proposed-order context**.
None of the four requested risk classes exist:

| Risk class (ticket) | Exists? | Where / gap |
|---|---|---|
| Margin check | ⚠️ Partial | `MarginFilter` = per-entry floor (10% of margin-used or ₹5k), **not** a utilization cap |
| Position limits | ✅ Yes | `MaxPositionFilter` (settings-backed, default 5) |
| Loss limits | ✅ Yes (daily only) | `LossLimitFilter` — daily PnL cap, entries-only (V1 fix) |
| **Max loss per trade** | ❌ No | No stop-loss on `OrderRequest`; no portfolio-equity source; no RR check |
| **Max portfolio heat** | ❌ No | `PortfolioRiskAggregator` computes `utilization_pct`+`breach` (P2-3.3) but it is **display-only**, never gates |
| **Max correlated exposure** | ❌ No | `sector_map.py` + aggregator exist (reusable); no underlying/sector/direction caps in the chain |
| **Cooldown after stop-loss** | ❌ No | `simple_generator` has a 300s signal-re-fire cooldown (unrelated); IAF `CooldownRule` is backtest-only; no stop-hit tracking in the live path |
| Concentration (all) | ❌ No | nothing |

The single biggest structural blocker: **`RiskFilter.check(signal, portfolio)`
never sees the proposed order** — no quantity, price, stop-loss, or target — so
a filter physically cannot compute potential loss, RR, or post-trade margin
heat. The stop-loss the system *generates* (`StrategyHints`: SL = 50% of
premium, target = 200%) is displayed on the proposal card (`ProposalResponse.stop_loss`)
but **never placed on the broker order** (`_build_order` ignores it;
`OrderRequest` has no SL field).

Secondary gaps: `RISK_ALERT` topic has subscribers (`RiskProjection`,
`scanner_data`) but **no publisher anywhere** — risk rejections never emit a
live alert; and the P2-3.3-known `margin_used` plumbing bug means portfolio-heat
data is unreliable in the live path.

---

## 1. Current risk-check architecture (what exists)

### 1.1 Filter chain — `src/shettyxtreme/intelligence/risk/risk_engine.py` (229 lines)

- **`RiskFilter` protocol** (line 57): `check(signal: Signal, portfolio: Portfolio) -> RiskDecision`.
  **No order/proposal context** — the structural blocker for P3-4.2.
- **`Portfolio`** (line 21): `{positions: list[Position], daily_pnl, total_margin_used, available_margin}`.
  **No equity / portfolio value** — max-loss-% has no denominator.
- **`RiskDecision`** (line 33): `{allowed, reason, filter_name}` — audit-friendly, carries the rejecting filter.
- **`RiskEngine`** (line 196): default chain `[LossLimitFilter, MarginFilter, MaxPositionFilter, RegimeFilter]`;
  `check_entry` short-circuits on first reject; `check_position_management` **always ALLOWs** (D10/V1 fix — position mgmt never frozen).
- **`LossLimitFilter`** (line 69): rejects entry when `portfolio.daily_pnl < loss_limit`; settings-backed (re-reads `get_settings_store().loss_limit()` every check). Default `-5000.0`.
- **`MarginFilter`** (line 105): rejects when `available_margin < max(total_margin_used × 0.10, 5000.0)` — a per-entry **floor**, not a utilization cap.
- **`MaxPositionFilter`** (line 125): rejects when active positions ≥ `max_positions` (settings-backed, default 5).
- **`RegimeFilter`** (line 157): **honest stub** — `is_stub = True`, always neutral ALLOW (no regime source in the chain; regime arrives via `regime.changed` bus event instead).
- **`cost_model.py`**: `compute_cost` (slippage/brokerage/STT/exchange), `adjust_ev` — reusable for net-of-cost loss math.

### 1.2 Where the check runs — `src/shettyxtreme/execution/execution_engine.py` (432 lines)

Single gated flow (`submit_signal → approve → risk check → validate → place order`):

1. `submit_signal()` (line 296) — creates a PENDING approval from `SIGNAL_V2` (via `ExecutionSignalBridge`). **No risk pre-screen at submission.**
2. `approve()` (line 319):
   - `_build_order(signal, strategy_hint)` — **order created here** (line 327);
   - `check_entry(signal, portfolio)` — **risk gate #1** (line 330); on reject → approval marked REJECTED, `failure_reason` persisted to `data/proposals.db`, `RuntimeError` raised (no order placed);
   - `OrderValidator.validate(order)` — format validation only (exchange/side/price-type/product/validity/qty, line 337);
   - `executor.place_order(order)` → `ModeRoutingExecutor` — **gate #2** (mode + kill switch).
3. The only order path is `ModeRoutingExecutor` (`execution/mode_router.py`): OBSERVER never places, PAPER → paper engine, LIVE → Fyers adapter with session-validity + **double kill-gate** (entry + immediately pre-wire). **No bypass exists in the live path** — the IAF adapter (`integration/external/iaf_adapter.py`) is backtest-only; `postback_router` only converts broker frames into `ORDER_UPDATED` events, never places.

So: the check runs **after** order creation and **after** human approval, **before** submission/placement. It cannot be bypassed via normal flows, but it is the *last* line — bad proposals reach the human first.

### 1.3 Composition root — `src/shettyxtreme/terminal/api/app.py` (lines 435-476)

- `_portfolio_provider()` builds the `Portfolio` from `PositionProjection` (symbol/exchange/quantity/buy_avg/net_quantity/m2m/pnl/product — **strike/expiry/option_type/lot_size stripped**, per P2-3.3) + `RiskProjection` (`daily_pnl`, `margin_used`, `margin_available`). **Unknown margin → 0.0** (conservative: MarginFilter then rejects what it can't verify).
- `RiskEngine()` wired with **default filters only** (line 473) — no custom caps injected.
- `_margin_poll_loop` (line 115): polls `get_margin()` every 30s but extracts **only `available`** — `utilized`/`total` discarded (P2-3.3 known bug) → `margin_used` ≈ 0 in live mode.

### 1.4 Settings store — `src/shettyxtreme/core/settings.py` (310 lines)

Typed SQLite KV (`data/settings.db`) with per-key validators. **Only two risk keys exist**: `loss_limit` (≤ 0, default −5000) and `max_positions` (1–100, default 5) + theme/scheduler keys. New caps (max-loss %, heat %, cooldown, concentration) need new `_SPECS` entries + validators for the `/api/settings` form to work.

### 1.5 Events & observability

- `RiskBusBridge` (`intelligence/risk/bus_bridge.py`) publishes `RISK_DECISION` `{daily_pnl, margin_used, margin_available, loss_limit, loss_limit_hit, max_positions}` on POSITION_CHANGED/MARKET_DATA_TICK → `RiskProjection` → `GET /api/execution/risk` + frontend strip.
- `Topic.RISK_ALERT` **exists** (`core/event_bus/event_bus.py:32`) with subscribers (`RiskProjection`, `scanner_data` on_risk_alert) but **zero publishers** — grep confirms no `publish(Event(Topic.RISK_ALERT…))` anywhere. Risk rejections surface only as proposal `status=REJECTED` + `reason` in the queue.
- `PositionManager` (`execution/position_manager.py`) exits via `Action` (EXIT_TP1/2/3, EXIT_TSL, EXIT_EOD) — **EXIT_TSL is the stop-hit signal** a cooldown tracker would consume, but no component records these exits today.

---

## 2. What's missing (per ticket)

### 2.1 Max loss per trade — ❌
- No filter computes `(entry − stop) × qty` vs portfolio. Denominator missing (`Portfolio.equity`), numerator un-plumbable (no stop/price on the filter input).
- `StrategyHints.generate()` (`intelligence/hints/strategy_hints.py:141`) already computes `stop_loss = premium × 0.5`, `target = premium × 2.0` (RR = 2:1 by construction) — but only the **chain hint builder** carries it; the **default hint builder** (`execution/signal_bridge.py:59`, used in production wiring per app.py:479-483) returns **no stop_loss/target at all**. And `_build_order` never forwards either field to `OrderRequest` (which has no SL field) — **no stop is ever placed at the broker**.
- No risk-reward / stop-too-wide check anywhere.

### 2.2 Max portfolio heat — ❌
- `PortfolioRiskAggregator._compute_margin_utilization` (`intelligence/risk/portfolio_risk.py:552`) computes `utilization_pct` + `breach` — but it's an **analytics endpoint** (`GET /api/execution/risk/heatmap`), never wired into the filter chain. No "max % of portfolio as margin" cap.
- Live data quality blocked by the poller bug (§1.3).

### 2.3 Max correlated exposure — ❌
- Building blocks exist: `core/knowledge/sector_map.py` (`SYMBOL_SECTOR`, ~140 symbols, `get_sector()`), `portfolio_risk._resolve_position_metadata` (extracts `underlying` from Fyers tickers), `Position.net_quantity` (direction), greeks aggregation (`_compute_greeks_concentration`). **None are consulted at entry.**
- No underlying-count cap (e.g. ≤3 NIFTY legs), no sector-notional cap (e.g. ≤20% IT), no direction cap (e.g. ≤80% long).

### 2.4 Cooldown after stop-loss — ❌
- No stop-hit ledger. `simple_generator.py:56` has a 300s per-symbol+direction signal cooldown (dedupe for re-firing signals — unrelated to SL hits). IAF `CooldownRule`/`cooldown_bars` (`iaf_adapter.py:183`, `core/interfaces/backtest_engine.py:87`) is **backtest-only**. `OutcomeTracker` records WIN/LOSS at decision level, not symbol-exit-granularity for blocking re-entry.
- No revenge-trading guard; no SL-hit counter per symbol.

### 2.5 Flow gaps
- Risk check is **approve-time only** — no pre-screen when the proposal is created, so low-quality proposals occupy the human's queue.
- Rejections are **not logged to the bus** (`RISK_ALERT` unpublisher) and not aggregated for review — audit trail = `proposals.db` `failure_reason` string only.
- `RiskEngine` default construction means new filters must be added to the default list (app.py doesn't inject a custom chain).

---

## 3. Proposed fix approach (algorithm direction, not code)

### 3.1 Give the chain order context — the pivotal change
Extend the `RiskFilter` protocol so filters evaluate the **proposed order**, not just the current book:

```
check(signal, portfolio, proposal: ProposalRiskContext | None = None) -> RiskDecision
```

where `ProposalRiskContext` = `{symbol, side, quantity, entry_price, stop_loss, target, product, lot_size, underlying, estimated_margin}` — assembled in `ExecutionEngine.approve()` from `strategy_hint` + `_build_order` (the hint already carries stop_loss/target when the chain builder is used). Backward-compatible default (`None`) keeps existing tests/filters valid; new filters REQUIRE the context and return a conservative REJECT-with-reason when fields are missing (honesty rule: never assume a stop exists).

### 3.2 Add `Portfolio.equity`
Extend `Portfolio` with `equity: float | None` (None = unknown). Populate in `_portfolio_provider` from `paper_engine.get_portfolio()` capital in PAPER, and from broker `fund_limit.total` (margin poller — fix the `utilized`/`total` extraction) in LIVE. Unknown equity → heat/loss-% filters reject-or-degrade conservatively.

### 3.3 New filters (all in `intelligence/risk/risk_engine.py`, settings-backed)

| Filter | Algorithm | Default cap |
|---|---|---|
| `MaxLossPerTradeFilter` | `potential_loss = (entry − stop) × qty × lot_size` (options: `premium × qty × lot_size` when no stop); reject if `potential_loss > equity × pct`. No stop → reject in LIVE, allow-with-reason in PAPER/OBSERVER (honesty). Net-of-cost via `cost_model.compute_cost` if desired. | 2% of equity |
| `RiskRewardFilter` | `rr = (target − entry) / (entry − stop)`; reject if `rr < min_rr`. Applies only when both stop and target present; no target → allow (target is a nicety, stop is mandatory). | 1.5 |
| `MarginHeatFilter` | `post_trade_utilization = (margin_used + est_new_margin) / (margin_used + available_margin)`; reject if > cap. `est_new_margin` v1 = `premium × qty × lot_size` (MIS option) or `lot_size × lot × SPAN` estimate when the India margin module lands (Arch §04); fall back to `MarginFilter`'s existing floor when unknown. | 50% |
| `UnderlyingConcentrationFilter` | count positions per `underlying` (via `_resolve_position_metadata`-style parsing or `instrument_master.lookup`) + proposed; reject if > cap. | 3 per underlying |
| `SectorConcentrationFilter` | `sector_notional / total_notional` via `get_sector()` + proposed notional; reject if > cap. Reuse `portfolio_risk._compute_sector_exposure` shape. | 20% |
| `DirectionConcentrationFilter` | net long notional / total (or net delta from `_compute_greeks_concentration`); reject if a single direction > cap after adding the proposal. | 80% one-sided |
| `StopHitCooldownFilter` | in-memory (or SQLite-KV) ledger of `symbol → last_stop_exit_ts`; record on EXIT_TSL (subscribe to position exits / `PositionManager` actions); reject re-entry of same symbol within window. Count SL hits per symbol/day for the reason string. | 30 min |

Order the chain: `LossLimit → MaxLossPerTrade → RiskReward → Margin → MarginHeat → Underlying → Sector → Direction → MaxPosition → StopCooldown → Regime(stub)`.

### 3.4 New settings keys (`core/settings.py`)
`max_loss_pct` (0.01–0.10), `max_margin_utilization_pct` (0.1–1.0), `min_risk_reward` (0.5–5.0), `max_positions_per_underlying` (1–10), `max_sector_pct` (0.05–1.0), `max_direction_pct` (0.5–1.0), `stop_cooldown_minutes` (0–240) — each with a validator, defaults as §3.3, added to `_SPECS` so the settings form (settings_router) works unchanged. All new filters follow the `_settings_backed` re-read pattern of `LossLimitFilter`.

### 3.5 Flow & observability changes
1. **Soft pre-screen at `submit_signal`**: run the chain with a *degraded* context (proposal may lack stop) and mark `PENDING` proposals that would hard-fail, so the operator sees a risk tag before approving (never auto-reject at submit — D10 keeps the human in control).
2. **Publish `RISK_ALERT` on rejection**: in `approve()` when `check_entry` rejects, emit `Topic.RISK_ALERT` with `{symbol, filter_name, reason, proposal_id}` — the topic + subscribers already exist, only the publisher is missing.
3. **Fix the margin poller** (P2-3.3 carry-over): also publish `margin_used` (`utilized`) + `total` so heat/equity filters have real data in LIVE.

### 3.6 Guardrails from the design docs (do not regress)
- **Position management always allowed** (V1 fix, `check_position_management`) — cooldown/heat filters must gate **entries only**.
- **OBSERVER-first (D10)** — new rejections are advisory-but-hard at approve; never auto-place.
- **Honesty rule** — missing equity/stop/margin → REJECT with reason (LIVE) or degrade (PAPER), never fabricate a pass.
- `core/` has zero external imports; new settings live in `core/settings.py` (already stdlib-only). Filters stay in `intelligence/risk/` (imports core + options only — inject `instrument_lookup`/margin providers via constructor, never import `integration/`).

---

## 4. Reusable existing code (do not reinvent)

| Need | Reuse |
|---|---|
| Filter chain + settings-backed pattern | `intelligence/risk/risk_engine.py` `RiskEngine`/`LossLimitFilter`/`MaxPositionFilter` |
| Net-of-cost loss math | `intelligence/risk/cost_model.py` `compute_cost` |
| Stop/target generation | `intelligence/hints/strategy_hints.py:141` (SL=50% prem, TP=200% prem) — chain hint builder only; default builder needs extending |
| Underlying extraction from Fyers tickers | `intelligence/risk/portfolio_risk.py:_resolve_position_metadata` (line 127) |
| Sector classification | `core/knowledge/sector_map.py` `SYMBOL_SECTOR` / `get_sector()` |
| Sector notional aggregation | `portfolio_risk._compute_sector_exposure` (line 329) |
| Margin utilization math | `portfolio_risk._compute_margin_utilization` (line 552) — `utilization_pct` + `breach` |
| Direction/greeks concentration | `portfolio_risk._compute_greeks_concentration` (line 383) — delta long/short breakdown |
| Stop-hit signal | `PositionManager` `Action.EXIT_TSL` (`execution/position_manager.py:34`) — needs a recorder/subscriber |
| Settings plumbing | `core/settings.py` `_SPECS` + validators pattern; `/api/settings` form + `settings_router` |
| Alert topic + subscribers (publisher missing) | `core/event_bus/event_bus.py` `Topic.RISK_ALERT`; `RiskProjection.on_risk_alert`; `scanner_data.on_risk_alert` |
| Kill-switch / mode double-gate (already blocks bypass) | `execution/mode_router.py` |
| Cooldown concept (backtest-only today) | `core/interfaces/backtest_engine.py:87` `cooldown_bars`; `iaf_adapter.py:183` — pattern reference only |
| Proposal card already shows stop/target | `terminal/api/execution_router.py:_proposal_response` (lines 324-325) — display surface for pre-screen tags |

---

## 5. Constraints & gotchas

- **Protocol change is the crux** — extending `RiskFilter.check` touches `RiskEngine.check_entry` and every test in `tests/wave2/test_risk_engine.py` (helper `_make_portfolio` lacks equity). Add a default param; update tests.
- **`Position` strips option metadata** (no strike/expiry/option_type/lot_size, P2-3.3 blocker) — underlying/sector filters must re-derive via instrument parsing, or the proposal's own `strike`/`expiry`/`lot_size` (which the hint carries) must be the source of truth for the *new* leg.
- **Default hint builder has no stop/target** (`signal_bridge.py:59-86`) — production wiring uses it, so the chain builder's SL/TP never reaches proposals today. MaxLoss/RR filters must handle missing stops conservatively, and extending the default builder (or switching wiring to the chain builder) is a prerequisite for full coverage.
- **Margin data is live-unreliable** (poller drops `utilized`) — heat filter must be fail-closed when utilization is unknown.
- **Settings validators are strict** — new keys need validators matching the existing style (finite, bounded, typed); the settings form UI lists only known keys, so new caps appear automatically once in `_SPECS`.
- **Test gates:** suite is 1012 tests; new filters land under `tests/wave2/test_risk_engine.py` (existing home) with the `_make_portfolio` helper extended. No `import openalgo`. No file > 1000 lines.
- **Cooldown ledger state**: in-memory is fine for v1 but must survive the approval-persistence story — a SQLite-KV row (`core/storage/kv_store.py` pattern) is the restart-safe option, matching `settings.db`.
