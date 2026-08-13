# P0-1.5 — Quantity Hardcoded to 75 (or Wrong) Everywhere

**Date:** 2026-08-12
**Severity:** P0 blocker (every proposal/order carries a hardcoded, now-wrong NIFTY lot size of 75; Jan-2026 lot is 65)
**Component:** `execution/signal_bridge.py` → `execution/execution_engine.py` → `intelligence/hints/strategy_hints.py` → `intelligence/risk/cost_model.py` → `learning/walkforward.py` → `terminal/api/execution_router.py` → `terminal/web/src/components/ProposalQueue.svelte`
**Current lot sizes (Jan 2026+):** NIFTY=65, BANKNIFTY=30, FINNIFTY=60, MIDCPNIFTY=120, NIFTYNXT50=25, SENSEX=20

---

## Executive summary

The number `75` is hardcoded as the NIFTY quantity/lot size in **four production modules** and is
used as the **raw broker quantity** — there is **no `lot_size × lots` computation anywhere in the
codebase**. The pipeline is single-symbol (NIFTY) and `ExecutionSignalBridge.default_hint_builder`
returns `quantity=75` verbatim; that value flows untouched through `ExecutionEngine._build_order`
into `OrderRequest.quantity` and out to the Fyers API (`"qty": 75`) or paper engine. The
`FyersInstrumentMaster` **does** store `lot_size` (from `minLotSize`) and **is** wired onto
`app.state.instrument_master`, but **no order/proposal/hint/cost code ever reads it** — the only
consumers are symbol resolution (`symbols.py` / `data_adapter.py`). There is no
`get_lot_size()` helper and no cache-miss API fallback.

---

## 1. Inventory — every hardcoded quantity/lot-size value (src/, tests excluded)

| # | File : line | Value | Where it lands | Live path? |
|---|---|---|---|---|
| 1 | `src/shettyxtreme/execution/signal_bridge.py:35` | `_DEFAULT_QUANTITY = 75` | `default_hint_builder()` returns `quantity=75` (line 47) → proposal → order | ✅ **YES — this is the "75" the user sees in NIFTY qty** |
| 2 | `src/shettyxtreme/intelligence/hints/strategy_hints.py:54` | `base_quantity: int = 75` | `self._sizing.adjust(self._base_quantity, conviction)` (line 105) when `CalibratedSizing.active`; else `quantity=None` | ⚠️ partial — `intelligence_router.py:393` calls `StrategyHints(signal=..., chain=..., current_price=...)` with the default 75 |
| 3 | `src/shettyxtreme/intelligence/risk/cost_model.py:42` | `lot_size: int = 75` (default arg of `compute_cost`) | `num_lots = quantity // lot_size` (line 59) → brokerage-per-lot math | ✅ **YES — `position_manager.estimate_exit_cost` (position_manager.py:239-240) calls `compute_cost(quantity=..., price=...)` without lot_size → default 75** |
| 4 | `src/shettyxtreme/learning/walkforward.py:15` | `LOT_SIZE = 75` | gross P&L `(exit-entry)*LOT_SIZE` and `compute_cost(LOT_SIZE, entry)` (lines 127-130) | ⚠️ backtest/eval only, but corrupts cost-adjusted return + calibration |
| 5 | `src/shettyxtreme/learning/analytics.py:212` | `qty = hint.get("quantity", 1)` | per-trade P&L `(exit-entry)*qty` | ⚠️ default 1 is conservative, not 75 — low risk, worth a comment |
| 6 | `src/shettyxtreme/execution/ledger.py:41-42` | docstring: "a 75-qty BUY met … 30-qty SELL …" | documentation only | ❌ no code |

**Noise ruled out** (numbers 50/25/30/40/60/120 are thresholds, timeframes, ADX gates, IST offsets —
NOT quantities): `strategy_analyzer.py:60/100`, `iv_rank.py:136/143`, `oi_tracker.py:59-60`,
`regime_classifier.py:28-122`, `_util.py:21`, `ws_client.py:45`, `data_socket.py:38`,
`data_adapter.py:58/426`, `market_router.py:134-139`, `analytics_router.py:34`, `health_router.py`,
`scanner_data.py:163`, `settings.py`, `app.py:95/107`, `_DEFAULT_TTE`, `_STT_RATE`, etc.
(Tests excluded per mission; `tests/wave2/test_cost_model.py` uses 75 in fixtures.)

### The exact user-visible chain (qty=75 on NIFTY)

```
ExecutionSignalBridge (signal_bridge.py:35,47)  _DEFAULT_QUANTITY=75 → hint["quantity"]
  └─ ExecutionEngine.submit_signal (execution_engine.py:296)       → PendingApproval(hint)
       └─ ExecutionEngine._build_order (execution_engine.py:421)   quantity=int(hint["quantity"])  # 75
            └─ OrderRequest.quantity = 75
                 └─ ModeRoutingExecutor (execution/mode_router.py:216)
                      ├─ PAPER → PaperTradingEngine.place_order (paper_trading.py:43-72)  # raw 75
                      └─ LIVE  → FyersTradingAdapter.place_order (trading_adapter.py:280) → "qty": 75 (line 166)
```

**No `lot_size * lots` anywhere.** 75 is sent as the raw contract quantity. If the broker
accepts it (some do, treating it as qty not lots), the position is 10 qty oversize vs. the 65
lot; Fyers typically rejects non-lot-multiple option quantities, but the failure mode is
silent/wrong sizing rather than explicit.

---

## 2. Instrument master API — what exists, what's missing

File: `src/shettyxtreme/integration/fyers/instrument_master.py` (class `FyersInstrumentMaster`, line 166)

**Existing query API:**
- `lookup(fyers_symbol: str) -> dict | None` (line 408) — exact ticker row incl. `lot_size`.
- `search(internal_symbol, exchange=None, instrument_type=None, expiry=None, strike=None, option_type=None) -> list[dict]` (line 434) — filtered rows incl. `lot_size`.
- `ensure_fresh(max_age_hours=None) -> dict | None` (line 378) / `needs_refresh()` (line 358) / `refresh()` (line 223) — 24h staleness (F-INT-008).

**Missing (this is the fix):**
- ❌ **No `get_lot_size(symbol)` helper.** Must be added (see §4).
- ❌ **No cache-miss → API fallback.** `lookup`/`search` are pure SQLite reads. If the DB is empty
  or `refresh()` failed at boot, they return `None`/`[]` silently. `init_instrument_master`
  (`terminal/api/instrument_init.py:11-31`) calls `ensure_fresh` once at startup, logs, and returns
  `None` on any exception — after that nothing re-tries, and no code path consults the master for
  lot size anyway.

**Wiring that already exists (good news for the fix):**
- `app.state.instrument_master` — set in `terminal/api/terminal_init.py:136/158` via `init_instrument_master()`; defaults to `None` (`app.py:232`).
- The data adapter already queries the master for symbol resolution: `fyers/data_adapter.py:139-141` uses `master.search(s)`; `symbols.py` validates tickers via `master.lookup(ticker)`.
- Index ticker mapping for lookup keys: `fyers/symbols.py:56-60` — `NIFTY→NIFTY50-INDEX`,
  `BANKNIFTY→NIFTYBANK-INDEX`, `FINNIFTY→FINNIFTY-INDEX`; all other internals pass through
  (`MIDCPNIFTY→MIDCPNIFTY-INDEX`, `NIFTYNXT50→NIFTYNXT50-INDEX`, `SENSEX→SENSEX-INDEX`).

---

## 3. Frontend display — current state

| Location | Renders | Notes |
|---|---|---|
| `terminal/web/src/components/ProposalQueue.svelte:248` | `QTY <b>{p.quantity}</b>` | raw number, no lots context — the user sees bare `75` |
| `ProposalQueue.svelte:310` (confirm dialog) | `QUANTITY <b>{target.quantity}</b>` | same |
| `ProposalQueue.svelte:338` | `Confirm {target.side} {target.quantity} {target.symbol}` | same |
| `ProposalQueue.svelte:221` | aria-label `… {p.quantity} …` | a11y |
| `PositionsRiskStrip.svelte:112` | `{p.net_quantity}` | open positions, raw qty |
| `terminal/web/src/lib/api.ts:310-329` | `Proposal.quantity: number` | **no `lot_size` / `lots` field exists in the TS type** |
| `terminal/api/execution_router.py:156` | `quantity=int(hint.get("quantity", 0))` | backend never enriches with lot size (doesn't touch `app.state.instrument_master`) |

**Target display (user asked):** `1 lot (65 qty)` — needs `lot_size` on the API response model
(`ProposalResponse` in `terminal/api/models.py` + `Proposal` in `api.ts`) and the three
`ProposalQueue.svelte` render sites.

---

## 4. Order creation — where qty is set (question 4)

- **Single source:** `ExecutionEngine._build_order` → `execution_engine.py:421`
  `quantity=int(strategy_hint["quantity"])`. It trusts whatever the hint carries.
- The hint comes from `ExecutionSignalBridge`'s injectable `hint_builder`, defaulting to
  `default_hint_builder` (signal_bridge.py:38-53) → **fixed 75, fixed NIFTY, no leg, no lot math.**
- `StrategyHints.generate()` would be the chain-aware source (strike/premium/EV + optional
  sizing-scaled quantity) but it is **only wired to `GET /api/intelligence/strategy-hint`**
  (`intelligence_router.py:393`) — never to the proposal flow (see sibling P0-1.4 findings).
- `ModeRoutingExecutor` (execution/mode_router.py) passes the `OrderRequest` through unchanged;
  `FyersTradingAdapter.place_order` maps `qty=_to_int(order.quantity)` (trading_adapter.py:166).
- `OrderValidator` (integration/order_validator.py:111-114) only checks `quantity > 0` — no
  lot-multiple validation.

**Conclusion:** qty is set once (the hint), flows raw end-to-end, and the value is the hardcoded 75.

---

## 5. Proposed fix

### 5.1 Add `get_lot_size()` to `FyersInstrumentMaster` (instrument_master.py)

```python
def get_lot_size(self, internal_symbol: str,
                 exchange: str = "NSE",
                 instrument_type: str = "INDEX") -> int | None:
    """Lot size for an internal symbol (e.g. 'NIFTY').

    Prefers an INDEX row (uniform per underlying); callers with a concrete
    contract ticker should use lookup(ticker)['lot_size'] instead.
    """
    rows = self.search(internal_symbol, exchange=exchange,
                       instrument_type=instrument_type)
    # fall back to any row for the symbol if no INDEX row exists
    if not rows:
        rows = self.search(internal_symbol, exchange=exchange)
    for r in rows:
        if r.get("lot_size"):
            return int(r["lot_size"])
    return None
```

Cache-miss behavior (required for the "no fallback" gap):
1. If `search` returns nothing AND `count_instruments() == 0` (or mirror stale) →
   `self.ensure_fresh()` once, then retry the lookup.
2. If still `None` → return `None` — callers must NOT guess (see §6).

### 5.2 Replace each hardcoded value

| Site | Replace | With |
|---|---|---|
| `signal_bridge.py:35,47` | `_DEFAULT_QUANTITY = 75` | `get_lot_size(symbol) * lots` in `default_hint_builder` (default `lots=1`); drop the module constant. Builder needs access to the master — inject it into `ExecutionSignalBridge` (wired at `app.py:396` from `app.state.instrument_master`) |
| `strategy_hints.py:54` | `base_quantity: int = 75` | `base_quantity: int | None = None`; resolve from master inside the class when None; when master unavailable → leave `quantity=None` (explicit unknown beats a wrong 75) |
| `cost_model.py:42` | `lot_size: int = 75` | make `lot_size` a **required** kwarg (`lot_size: int`) or default `None` → `num_lots = quantity // lot_size if lot_size else 1`; update `position_manager.estimate_exit_cost` (line 239-240) to pass the master-resolved lot size |
| `walkforward.py:15` | `LOT_SIZE = 75` | constructor param `lot_size: int | None = None` (config-driven, master-optional for backtests); keep `LOT_SIZE` only as a named fallback with a loud warning |
| `analytics.py:212` | `hint.get("quantity", 1)` | keep 1 (safe) but add comment; or read `hint["lot_size"] * lots` when present |

### 5.3 Frontend: "X lots (Y qty)"

1. Backend `ProposalResponse` (terminal/api/models.py) + `_proposal_response`
   (execution_router.py:146-170): add `lot_size: int | None` and `lots: int` — computed from
   `app.state.instrument_master.get_lot_size(symbol)`; `lots = quantity // lot_size` when known.
2. TS `Proposal` (api.ts:310-329): add `lot_size: number | null; lots: number;`.
3. `ProposalQueue.svelte`:
   - line 248 → `QTY <b>{p.quantity}</b>` becomes
     `QTY <b>{p.lots} {p.lots === 1 ? "lot" : "lots"} ({p.quantity} qty)</b>` (when `p.lot_size` known; else keep raw with `—`).
   - line 310 → `QUANTITY` row same dual-unit format.
   - line 338 → `Confirm {target.side} {target.lots} lot(s) ({target.quantity} qty) {target.symbol}`.
   - line 221 aria-label → mirror the dual-unit text.
4. `PositionsRiskStrip.svelte:112` — optionally annotate with lot size; position `net_quantity`
   stays raw (it's broker truth) — display-only change.

---

## 6. Edge cases

1. **`get_lot_size()` returns `None` (master init failed / refresh failed / symbol unknown):**
   **Never silently fall back to 75.** Options, in order of safety:
   - **Block the proposal** (OBSERVER-first, D10-aligned): hint builder returns `None` → bridge logs
     "lot size unknown for NIFTY — proposal not created" (signal_bridge.py:108-110 already skips
     `None` hints).
   - Or surface a **STATIC LOT SIZE** warning on the proposal with a per-symbol static table
     (NIFTY=65, BANKNIFTY=30, FINNIFTY=60, MIDCPNIFTY=120, NIFTYNXT50=25, SENSEX=20) clearly tagged
     as fallback — never silently.
2. **Stale mirror:** `ensure_fresh` (24h, F-INT-008) covers changed lot sizes within a day; the
   `get_lot_size` cache-miss path must call it once before giving up.
3. **Lot size can differ per contract:** option rows carry their own `minLotSize`; for a concrete
   option ticker prefer `lookup(ticker)["lot_size"]` over the INDEX row. For the current
   NIFTY-only pipeline the INDEX row is correct.
4. **Per-symbol, not per-NIFTY:** the fix must be symbol-parameterized — watchlist
   (`configs/default_watchlist.yaml`) seeds multiple underlyings; `_PIPELINE_SYMBOL = "NIFTY"`
   (signal_bridge.py:34) and `intelligence_router.py:376` both hardcode NIFTY today and should
   take the symbol from context.
5. **Non-lot-multiple validation:** add a broker-side guard in `OrderValidator` (order_validator.py)
   — `quantity % lot_size == 0` — so a future sizing regression fails loudly at approve time, not
   at the broker.
6. **Backtest/calibration purity:** `walkforward.LOT_SIZE=75` and `analytics` P&L math skew
   `cost_adjusted_return` and calibration curves; the lot size must be injected from the same
   source so live vs. backtest numbers stay comparable.
7. **`cost_model` default-arg removal is a breaking change for tests/callers** — update
   `tests/wave2/test_cost_model.py` fixtures (they pass 75 explicitly in most cases) and
   `position_manager.estimate_exit_cost`.

---

## 7. Test/verification plan (manual — no CI in repo)

1. Unit: `get_lot_size("NIFTY")` == 65 against a seeded mirror; returns `None` on empty DB; triggers
   `ensure_fresh` once on cache miss.
2. Unit: `default_hint_builder` with injected master → `quantity == 65` (1 lot).
3. Unit: `compute_cost(quantity=65, price=..., lot_size=65)` — brokerage = 1 lot.
4. Integration: start terminal (`run.py --mode OBSERVER`), wait for a signal → proposal shows
   `1 lot (65 qty)`; OBSERVER never places.
5. Full suite: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
6. `npm run check` (0 errors) + `npm run build` after the Svelte/TS changes.

---

## 8. Cross-reference

- Sibling P0-1.4 findings: `docs/superpowers/plans/2026-08-12-p0-1-4-proposals-findings.md` (proposals carry no strike/expiry/CE/PE — qty 75 noted there as "never lot-rounded").
- F-INT-008 (master staleness): instrument_master.py:12-18, 358-397.
- D10 (OBSERVER-first): AGENTS.md; execution_router approve gate.
- Lot-size truth: Fyers master `minLotSize` field → `instrument_master.py:322` (`_as_int(row.get("minLotSize"))`).
