# P3-4.1 Findings — Paper Trading Must Feel Real

**Date:** 2026-08-12 · **Status:** Investigation complete — no code changed · **Scope:** `execution/` + risk chain + cost model

---

## TL;DR

Paper trading in ShettyXtreme is a **deterministic, cost-free, leverage-free simulator**:
MARKET orders fill instantly at LTP, LIMIT/SL orders fill with 100% certainty the moment
the price is touched, there is **zero slippage, zero fees, zero fill probability, and no
margin sizing** (full-notional cash debits only, and no check inside the engine). The
building blocks for realism already exist elsewhere in the repo (`intelligence/risk/cost_model.py`
computes slippage+brokerage+STT+exchange charges; `Tick` carries bid/ask; the ledger already
FIFO-pairs partial fills) — but nothing connects them to execution.

---

## 1. Current paper trading architecture (what exists)

### 1.1 The engine — `src/shettyxtreme/execution/paper_trading.py`

`PaperTradingEngine` — in-memory, event-driven. Constructor
`(event_bus=None, initial_capital=1_000_000.0)`; subscribes to `Topic.MARKET_DATA_TICK`.
State: `_capital`, `_positions: dict[str, Position]`, `_orders`, `_pending_orders`,
`_fills`, `_ltp_cache`, `_trade_seq`.

### 1.2 Order flow (the whole execution model)

```
place_order()  paper_trading.py:44
  ├─ MARKET → _fill_order() immediately            ← INSTANT fill, full qty
  ├─ LIMIT/SL → _pending_orders, returns OPEN      ← waits for a tick
  └─ anything else → REJECTED (incl. SL_M!)
_on_tick()  paper_trading.py:148                    ← trigger-based, no probability
  └─ LIMIT BUY fills when ltp <= price; SELL when ltp >= price
     SL BUY fills when ltp >= trigger; SELL when ltp <= trigger
_fill_order()  paper_trading.py:179
  ├─ MARKET: fill_price = ltp (rejects honestly if no LTP cached — F-EXEC-004)
  ├─ LIMIT/SL: fill_price = order.price             ← exact limit, no slippage/improvement
  ├─ fills FULL quantity always (no partials)
  ├─ _update_positions()  (avg-price bookkeeping, pos.pnl accumulates on close)
  ├─ margin accounting: BUY → _capital -= notional; SELL → _capital += notional
  └─ emits ORDER_FILLED + POSITION_CHANGED on the bus
```

### 1.3 Margin — full notional, no sizing

- Every BUY fill debits **100% of notional** (`qty × fill_price`); every SELL credits it
  back (paper_trading.py:218-222). This is CNC-style full cash, **no leverage, no SPAN,
  no premium collection for short options**.
- `get_portfolio()` (paper_trading.py:123-146): `total_margin_used = open notional`,
  `available_margin = _capital` (cash, not equity).
- **No margin check inside the engine** — `place_order` can drive capital negative on an
  oversized order. The only gate is upstream:
  - `ExecutionEngine.approve()` → `_get_portfolio()` → `RiskEngine.check_entry()` →
    `MarginFilter` (`intelligence/risk/risk_engine.py:105-122`).
  - `MarginFilter` is crude: `required = total_margin_used × 0.1`, floored at ₹5000; rejects
    if `available < required`. **It never sizes the *incoming* order** — a ₹10L order against
    ₹5L cash with no open positions passes (5000 ≤ 500000).
- PAPER-mode margin wiring was fixed in **P0-1.3**: `app.py` `_portfolio_provider` falls back
  to `paper_engine.get_portfolio().available_margin` when `risk.margin_available` is None and
  mode is PAPER (`app.py:458-463`). Config: `configs/default.yaml` `paper_trading_margin: 1000000`,
  env `SHETTY_PAPER_TRADING_MARGIN` (config_manager.py:30,63,116).

### 1.4 P&L — realized is effectively broken in the engine

- `_recalculate_pnl()` (paper_trading.py:272-281): m2m (unrealized) at cached LTP.
- `get_pnl()` (paper_trading.py:96-121):
  ```python
  realised = sum(getattr(t, "pnl", None) or 0.0 for t in self._fills)
  ```
  **`Fill` has no `pnl` field** (core/data_models/orders.py:97-100) → `realised_pnl` is
  **permanently 0.0**. The engine's own realized P&L is dead code; the real round-trip P&L
  accumulates in `pos.pnl` (via `_update_positions`) but is never surfaced. `daily_pnl` in
  `get_portfolio()` is therefore just unrealized m2m.
- The **correct** realized P&L exists one layer down: `TradeLedger.pair_fills()`
  (`execution/ledger.py:34-101`) FIFO-pairs opposite-side fills per symbol (partial-aware)
  and feeds analytics — but it is **cost-free and not fed back into the engine**.
- `total_invested = initial_capital - _capital` (paper_trading.py:119) returns to 0 after any
  round trip — a misnomer, not real invested capital.

### 1.5 Surrounding wiring

- **Router:** `execution/mode_router.py` — PAPER → `paper.place_order`; cancels → paper;
  modify → rejected in PAPER. No margin/portfolio passed through.
- **Recording:** `execution/ledger_recorder.py` — `ORDER_FILLED` → `TradeLedger` row
  (source=`"paper"`, sqlite `fills` table). Fill schema has **no fee/commission column**.
- **App wiring:** `terminal/api/app.py:417-421` — engine created with `cfg.paper_trading_margin
  or 1_000_000`; `ModeRoutingExecutor` + `ExecutionEngine` + risk chain at app.py:426-477.
- **Tests:** `tests/execution/test_paper_trading.py` (13 tests: instant market fill at LTP,
  honest reject without LTP, limit pending, cancel, margin decrement/restore).

---

## 2. What's missing (gap-by-gap vs. the mission checklist)

| Capability | Current state | Severity |
|---|---|---|
| **Slippage** | **None in execution.** MARKET fills at exact LTP; LIMIT at exact limit price. `_on_tick` reads only `ltp` — the `Tick.bid`/`Tick.ask` fields (populated by the Fyers adapter, data_adapter.py:211-212) are ignored. | High — biggest realism gap |
| **Brokerage / STT / exchange / GST / SEBI / stamp** | **None in execution.** No charge applied on any fill; `_capital` moves by gross notional only. | High |
| **Fill probability** | **None.** LIMIT/SL fill with 100% certainty on first touch; full quantity always; no distance/volume/time factors; orders never expire (in-memory, persist only for process life). `SL_M` (in `OrderType` enum) is **rejected as unsupported**. | High |
| **Partial fills** | **None in the engine** (always full qty) — though `OrderStatus.PARTIALLY_FILLED` exists and the ledger pairing is partial-aware. | Medium |
| **Margin requirements** | Full-notional cash debit only; no SPAN/premium/position margin; no engine-side check; upstream `MarginFilter` never sizes the incoming order. | High |
| **Realized vs unrealized P&L** | Unrealized m2m at LTP (fine). Realized: engine's own value is dead (always 0.0); real FIFO realized P&L lives in the ledger but is cost-free and not connected to the engine. No daily/15:30 settlement boundary. | Medium |
| **Cost-adjusted P&L** | None — no fees anywhere, so P&L overstates every result. | High |

### Where realism already exists (but is not wired to execution)

- **`intelligence/risk/cost_model.py`** — `compute_cost(quantity, price, slippage_bps=2.0,
  brokerage_per_lot=20.0, lot_size)` returns `CostBreakdown{slippage, brokerage, stt,
  exchange_charges}`. Rates: STT 0.01% of premium, exchange 0.05%. Used only by
  `learning/walkforward.py` (line 134) and strategy hints. **Missing GST (18%), SEBI
  (₹10/crore), stamp duty, and the ₹20-or-0.03%-whichever-lower brokerage rule.**
- **`core/interfaces/backtest_engine.py`** — `BacktestConfig.slippage_bps=2.0`,
  `brokerage_per_lot=20.0`; `integration/external/iaf_adapter.py:190-193` maps them into
  IAF's `TradingCost` (bps → decimal). Same conventions the paper engine should use.
- **`core/data_models/market_data.py`** — `Tick` carries `bid`/`ask` (and Fyers populates
  them) → spread-based slippage is feasible today.
- **`execution/ledger.py` `pair_fills`** — FIFO realized P&L with partial-remainder support.
- **Analytics precedent** — `docs/superpowers/plans/2026-08-02-pending-hygiene-ledger-knowledge-v2.md:746`
  uses `_COST_PER_FILL = 25.0` (brokerage 20 + slippage 5) as a per-fill cost constant.
- **Architecture mandate** — v2 feature map (`docs/architecture/v2/sections/08-feature-map.md:91`)
  lists "Risk engine + cost model (slippage, spread, brokerage, STT)" as MVP/Essential.

---

## 3. Proposed fix approach (algorithm, not code)

All four gaps are execution-side concerns of `PaperTradingEngine`. Introduce **injected,
configurable policy objects** (defaults enabled) so paper behavior is realistic but tunable
and testable without a real broker. Keep every event (`ORDER_FILLED`, `POSITION_CHANGED`)
shape unchanged so the ledger, projections, and UI keep working.

### 3.1 Slippage model — layered, applied at fill price computation

Layered model in priority order, each layer configurable in bps:

1. **Spread-based (primary, when the tick carries bid/ask):** BUY fills at
   `ask × (1 + s_bps)`; SELL at `bid × (1 − s_bps)` where `s_bps` is a small residual
   (e.g. 1-2 bps). Fall back to LTP-based when bid/ask are None.
2. **Fixed bps by order type:** MARKET ~5 bps, SL-M ~10 bps (marketable, worst), resting
   LIMIT 0 bps of slippage on the price but fills **at the limit, never better** (no price
   improvement — realistic for a small retail sim, keeps it conservative).
3. **Volume-based add-on (optional tier):** add bps proportional to
   `log(order_notional / typical_tick_value)` so large orders pay more — disabled by
   default until per-symbol volume stats exist.
4. Directionality: BUY adds slippage to the fill price, SELL subtracts — never symmetric.

Where applied: `_fill_order` for MARKET/SL-M; `_on_tick` for LIMIT/SL fills. SL fills should
use LTP/bid-ask **at trigger time** (real SL-M fills at market), not the resting price.

### 3.2 Fees model — India-correct charge sheet per fill

A `FeesModel` (extend `cost_model.compute_cost` into a round-trip-aware `ChargesModel`),
applied on **every fill**, debited from `_capital` at fill time, and recorded per-fill:

| Charge | Equity delivery | Futures | Options |
|---|---|---|---|
| Brokerage | min(₹20, 0.03% of turnover) | min(₹20, 0.03%) | min(₹20, 0.03%) |
| STT | 0.1% on sell side | 0.0125%/0.02% on sell side | 0.1% of premium on sell side |
| Exchange Txn | ~0.003% of turnover | ~0.0017% | ~0.035% of premium |
| GST | 18% on (brokerage + exchange + SEBI) | same | same |
| SEBI | ₹10 / crore turnover | same | same |
| Stamp duty | 0.003% buy side | 0.002% buy | 0.003% buy |

Precise NSE rates belong in the config, not hardcoded. Deduct at fill time; a small
`_fees_paid` accumulator surfaces in `get_pnl()`; a `fees` column on the ledger `fills`
table lets `pair_fills` net realized P&L per pair.

### 3.3 Fill probability — LIMIT orders become probabilistic

Keep trigger detection, replace certainty with a probability at each qualifying tick:

- **Spread-aware touch:** with bid/ask, a resting BUY LIMIT fills when `ask <= limit`
  (SELL when `bid >= limit`) — deterministic at the touch level (this IS the real market
  rule), probabilistic in **which touch**.
- **Distance factor:** orders placed far from LTP get lower fill probability and slower
  first-touch time; probability rises as price approaches.
- **Time-in-market:** probability of fill at the touch decays with age and tick count
  (queue fade) — an order that has seen N ticks without a fill fades to ~0.
- **Volume factor (optional):** require cumulative traded volume at/near the level before
  filling (needs tick `volume`, which `Tick` carries).
- **Partial fills:** fill `min(qty, available_depth)` and keep the remainder pending
  (reuse `OrderStatus.PARTIALLY_FILLED` + the ledger's existing partial pairing).
- **Gap-through:** if LTP gaps through a resting limit, fill at the limit (resting orders
  never fill better); if it gaps **past** the limit price, fill at limit (conservative).

### 3.4 Margin requirements — engine-side pre-trade sizing

Move the margin gate **into the engine** (reject before filling, not after), with an
injected `MarginPolicy` that returns required margin per order:

- **Equity MIS (intraday):** ~20% of notional (configurable upfront margin).
- **Futures:** SPAN proxy ≈ 12-15% of notional per contract (configurable factor; wire a
  real SPAN feed later via a `margin_provider` callback — Fyers `get_margin`/instrument
  master already exist as a source pattern).
- **Options long (buy):** full premium (qty × premium).
- **Options short (sell):** premium collected + per-contract SPAN factor (config-driven
  until a margin engine exists).
- `get_portfolio()` should report `equity = _capital + unrealized` and
  `margin_used = sum(required for open positions)` separately; reject when
  `required(new) > available`. Also fix `MarginFilter` upstream so the risk chain sizes the
  **incoming** order, not just 10% of current open notional.

### 3.5 P&L timing — realized at close, cost-adjusted

- **Realized:** on any fill that closes a position — write `pos.pnl` (gross) minus fees for
  both legs onto the fill/emit a `TRADE_CLOSED` event; **fix `get_pnl()`** to sum the
  position-level realized accumulator instead of the dead `fills[].pnl` sum.
- **Unrealized:** keep tick-level m2m (already correct); optionally settle daily at 15:30 IST
  (the fyers `_util.py` IST boundary helpers already exist).
- **Ledger:** add per-fill fees; `pair_fills` nets fees per pair so analytics realized P&L
  becomes net-of-cost.

---

## 4. Reusable existing code (do not reinvent)

| Asset | Where | Reuse for |
|---|---|---|
| `compute_cost` / `CostBreakdown` | `intelligence/risk/cost_model.py:16-74` | Fee base (extend with GST/SEBI/stamp + ₹20-or-0.03% rule) |
| `slippage_bps` / `brokerage_per_lot` | `core/interfaces/backtest_engine.py:89-90`; `iaf_adapter.py:190-193` | Same bps conventions, shared config shape |
| `Tick.bid` / `Tick.ask` | `core/data_models/market_data.py:15`; Fyers populates at `data_adapter.py:211-212` | Spread-based slippage + touch detection |
| `Tick.volume` | `core/data_models/market_data.py:14` | Volume-based fill probability (optional tier) |
| `OrderStatus.PARTIALLY_FILLED` | `core/data_models/orders.py:39` | Partial fill state |
| `pair_fills` FIFO + partial remainders | `execution/ledger.py:34-101` | Cost-adjusted realized P&L |
| `Portfolio` + PAPER-mode fallback | `intelligence/risk/risk_engine.py:21-27`; `app.py:458-463` | Margin plumbing (P0-1.3 already wired) |
| `MarginFilter` | `intelligence/risk/risk_engine.py:105-122` | Fix to size incoming order |
| `_margin_poll_loop` / `get_margin` pattern | `app.py:113-146`; `integration/fyers/trading_adapter.py:426-452` | Future real-margin source for paper |
| IST day-boundary helpers | `integration/fyers/_util.py:105-106` | Daily settlement boundary |

## 5. Test implications

Existing `tests/execution/test_paper_trading.py` asserts instant/no-slippage behavior
(e.g. `average_price == 18450.0` at LTP) and will need updating to a **default
slippage/fees-enabled** engine, or policy-injection so tests pass zero-cost/slippage
configs. New tests: slippage directionality (BUY pays more), fee deduction on fill,
limit-fill probability bounds (0 ≤ p ≤ 1, never instant), margin rejection for oversized
orders, partial-fill remainder behavior, realized P&L non-zero after a close.

## 6. Verification steps (after implementation)

1. Full suite: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
2. `grep -r "import openalgo\|from openalgo" src/` → zero matches.
3. No file > 1000 lines.
4. Manual: `run.py --mode PAPER` → approve a proposal → fill shows slippage + fees in
   order message; position P&L net of cost; oversized order rejected with margin reason.
