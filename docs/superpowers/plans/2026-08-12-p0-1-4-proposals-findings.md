# P0-1.4 — Proposals are Useless (No Strike, No Expiry, No CE/PE, No Lot Size)

**Date:** 2026-08-12
**Severity:** P0 blocker (proposals cannot be executed as-is; "NIFTY BUY" carries no leg)
**Component:** `intelligence/hints/` → `execution/signal_bridge.py` → `execution/execution_engine.py` → `terminal/api/execution_router.py` → `terminal/web/src/components/ProposalQueue.svelte`

---

## Executive summary

The proposal pipeline **never generates a concrete option leg**. Proposals are built by a
hardcoded `default_hint_builder` that returns `symbol="NIFTY", exchange="NFO",
quantity=75, price=None, order_type=MARKET, product=MIS, hint_kind="default"` — nothing else.
`StrategyHints` (which *does* pick a strike + premium + EV) exists but is **only** wired to the
standalone `GET /api/intelligence/strategy-hint` endpoint; it is **never plugged into the
proposal flow**. There is no `OptionLeg` model anywhere in the codebase. `OrderRequest`
(core data model) has no strike/expiry/option_type fields, and the API
`ProposalResponse`/`Proposal` (TS) types carry no leg fields, so the frontend literally has
nothing to render beyond "NIFTY BUY". Approval sends only the proposal ID; the engine
re-derives the order from the stored (default) hint dict. Even if approved, the Fyers
adapter would resolve "NIFTY" as an **index** ticker — not an option contract — so the
order would be meaningless or rejected.

---

## 1. Current StrategyHint model — what's missing

`src/shettyxtreme/intelligence/hints/strategy_hints.py:31-39`:

```python
@dataclass
class StrategyHint:
    direction: str  # bullish / bearish / neutral
    strategy: str
    strike: float | None = None
    premium: float | None = None
    ev_after_cost: float = 0.0
    rationale: str = ""
    quantity: int | None = None
```

**Present:** direction, strategy, strike, premium (entry), ev_after_cost, rationale, quantity.
**Missing (vs. expected leg fields):**

| Field | Present? | Notes |
|---|---|---|
| strike | ✅ | float, but no expiry context |
| expiry | ❌ | only `days_to_expiry` int (default 7) used for EV math; real expiry date never surfaced |
| option_type (CE/PE) | ❌ | computed locally in `generate()` (`"CE" if bullish else "PE"`, line 100) but never stored on the hint |
| symbol / underlying | ❌ | hint is symbol-agnostic; proposal hardcodes "NIFTY" separately |
| exchange | ❌ | hardcoded "NFO" in `default_hint_builder` |
| qty | ⚠️ | `int \| None`; only set when `CalibratedSizing.active`; base 75, **never lot-rounded** |
| lot_size | ❌ | no field, never queried |
| stop_loss | ❌ | not computed anywhere in this layer |
| target | ❌ | not computed anywhere in this layer |
| confidence | ❌ | conviction exists on the `Signal`, not the hint |

There is **no `OptionLeg` dataclass/pydantic model anywhere in `src/`** (grep
`OptionLeg` → zero matches).

## 2. Hint generation — no instrument_master, no lot rounding

`StrategyHints.generate()` (`strategy_hints.py:65-132`):

- `option_type` derived from direction (`CE`/`PE`), never persisted.
- Strike selection via `_select_strike` → `select_strike_by_ev` using only
  `strike`, `premium`, `iv` from the chain rows (`strategy_hints.py:156-167`).
  The docstring of `select_strike_by_ev` (`options_intel.py:224`) claims strikes carry
  a `'lot_size'` key, but **no caller ever populates or reads it**.
- **Quantity: `self._sizing.adjust(self._base_quantity, conviction)`** with
  `_base_quantity=75` (line 54, 105). **No `instrument_master` lookup, no rounding to lot
  multiples.** If sizing is inactive/absent, quantity stays `None` — the proposal would
  default to `quantity=0` via `int(hint.get("quantity", 0))` in the router.
- `FyersInstrumentMaster` (`integration/fyers/instrument_master.py`) **has** lot_size in its
  schema (`lot_size INTEGER`, line 87) and a `search(internal_symbol, exchange,
  instrument_type, expiry, strike, option_type)` query (line 434) that returns lot_size —
  but **nothing in the hint/proposal layer touches it**. It is only used by the data adapter
  for symbol resolution (`fyers/data_adapter.py:150`).
- `expiry` is only used as DTE for EV (`_DEFAULT_DTE = 7`); the chain request's real expiry
  (available at the `/strategy-hint` endpoint via `_fetch_chain_with_spot`) is discarded.

**Wiring status:** `GET /api/intelligence/strategy-hint` (`intelligence_router.py:370-400`)
is the sole consumer of `StrategyHints`. The proposal bridge never calls it.

## 3. ProposalQueue.svelte — what it renders vs what it should render

`src/shettyxtreme/terminal/web/src/components/ProposalQueue.svelte` renders per row
(lines 214-282): symbol, SIDE badge (BUY/SELL), conviction badge, STALE badge,
DEFAULT HINT badge, `QTY`, `PRICE (MKT)`, `ORDER TYPE`, timestamp. The confirm dialog
(lines 307-314) shows: SYMBOL, SIDE, QUANTITY, PRICE, ORDER TYPE, PRODUCT + risk summary.

**The `Proposal` TS type (`web/src/lib/api.ts:310-329`) has exactly:** id, symbol,
exchange, side, quantity, price, order_type, product, conviction, D, P, G, source,
hint_kind, signal_id, status, reason, timestamp. **No strike, expiry, option_type,
lot_size, entry, stop_loss, target, rationale.**

So the UI faithfully renders the (empty) data — the comment on `hint_kind` even admits it:
*"default / chain — chain-derived when a real builder is plugged"* — **the real builder was
never plugged**.

**Should render:** a full leg card per proposal — underlying + expiry + strike + CE/PE,
qty (and lots × lot_size), entry/premium, stop_loss, target, rationale snippet, EV badge,
confidence. Confirm dialog should show the same leg fields + explicit "REAL order" warning.

## 4. Approve button — what it sends vs what it should send

`ProposalQueue.svelte:142` → `api.ts:342-354`:

```
POST /api/execution/proposals/{id}/approve?confirm={bool}   (+ X-CSRF-Token in LIVE)
```

**Sends only the proposal ID.** No leg object, no fields at all — the backend
(`execution_router.py:350-389`) looks the stored `PendingApproval` up by ID and rebuilds
the order from the **stored** hint dict (`execution_engine.py:327`,
`_build_order(signal, strategy_hint)`).

**Should send:** nothing structurally wrong with ID-based approval *if* the stored hint
carries the full leg. The real defect is upstream — the stored hint is the default stub.
(Optional hardening: approval could echo back the resolved leg for a final
operator-visible check, but it is not required for the fix.)

## 5. ExecutionEngine — how it receives the proposal

`ExecutionSignalBridge` (`execution/signal_bridge.py`) is the entry point:

- Subscribed to `Topic.SIGNAL_V2` (`start()`, line 73). On signal: skips NEUTRAL, builds a
  `Signal`, then `hint = self._hint_builder(values)` (**line 108 — defaults to
  `default_hint_builder`** since `app.py:396-399` passes no custom builder), dedupes by
  symbol+side, then `engine.submit_signal(signal, hint)`.
- `submit_signal` (`execution_engine.py:296-317`) wraps signal + hint dict into a
  `PendingApproval` and persists the full payload to `data/proposals.db` (F-KNOW-002).
- `approve(approval_id)` (`execution_engine.py:319-354`): risk check → validate →
  `_build_order(signal, strategy_hint)` → `executor.place_order(order)`.
- `_build_order` (`execution_engine.py:401-428`) reads `symbol`, `exchange`, `quantity`,
  `price`, `order_type`, `product` straight from the hint dict. **`OrderRequest`
  (`core/data_models/orders.py:45-63`) has NO strike/expiry/option_type fields.**
- Fyers path: `trading_adapter._fyers_symbol` (`trading_adapter.py:143-153`) resolves the
  symbol; `symbols.to_fyers` (`fyers/symbols.py:211`) **requires strike + option_type to
  build an OPTION ticker** (`"strike is required for OPTION symbols"`, line 273) and
  otherwise produces an INDEX/EQUITY ticker. So approving today would try to trade the
  **NIFTY index itself** — the option leg simply doesn't exist downstream.

**Expectation:** the engine already tolerates an arbitrary hint dict (forward-compatible);
it *can* receive a full leg if the hint dict carries `strike`, `expiry`, `option_type`,
`lot_size` and `quantity` is a lot multiple. The gap is that nothing upstream produces one,
and `OrderRequest`/adapters can't carry structured leg fields (they'd need the resolved
Fyers ticker or new fields).

---

## Proposed fix

### A. Model changes (backend)
1. **Add `OptionLeg` dataclass** (e.g. `intelligence/hints/option_leg.py`, or nested in
   `strategy_hints.py`):
   `underlying, exchange, strike, expiry (ISO date str), option_type (CE/PE),
   lot_size, qty (contracts = lots × lot_size), lots, entry_premium,
   stop_loss, target, dte`.
2. **Extend `StrategyHint`** with `leg: OptionLeg | None`, plus `confidence`,
   `stop_loss`, `target` and the existing fields kept for the `/strategy-hint` endpoint
   (add the missing ones to `StrategyHintResponse` in `terminal/api/models.py` too —
   currently `direction/strike/premium/ev_after_cost/rationale` only, line 73).
3. **Extend `OrderRequest`** (`core/data_models/orders.py`) with optional
   `strike/expiry/option_type/lot_size` (or a pre-resolved `fyers_symbol`), so the Fyers
   adapter can build the option ticker via `symbols.to_fyers` instead of resolving "NIFTY"
   as an index. This is the minimum for execution to be meaningful.
4. **Extend `ProposalResponse`** (`terminal/api/models.py:148`) and the TS `Proposal` type
   (`web/src/lib/api.ts:310`) with the leg fields (strike, expiry, option_type, lot_size,
   qty, entry, stop_loss, target, rationale). Backward-compatible: add optional fields with
   defaults.

### B. Hint generation changes
5. **Inject `FyersInstrumentMaster` (or a lot-size resolver Protocol)** into `StrategyHints`
   (it's already available as `app.state.instrument_master`). After strike selection, look
   up `lot_size` via `master.search(internal_symbol="NIFTY", instrument_type="OPTION",
   strike=..., option_type=..., expiry=...)` and **round qty up to a lot multiple**
   (`ceil(qty / lot_size) * lot_size`).
6. **Persist the real expiry** — pass the chain request's expiry date through
   `StrategyHints` instead of discarding it (the `/strategy-hint` endpoint already has it
   from `_fetch_chain_with_spot`).
7. **Compute stop_loss / target** from premium (e.g. premium-based SL/TP ratios, or reuse
   `learning/mfe_mae.py` MFE/MAE for target/SL tuning) and set `confidence` from the signal
   conviction.
8. **Write a real chain-aware hint builder** (`build_chain_hint` in `signal_bridge.py` or
   `intelligence/hints/`) that produces the full leg dict (symbol, exchange, strike, expiry,
   option_type, lot_size, qty, price, order_type=LIMIT, product=MIS, stop_loss, target,
   rationale, hint_kind="chain") — matching the `default_hint_builder` dict contract so
   `ExecutionEngine._build_order` keeps working unchanged.

### C. Pipeline wiring (app.py)
9. **Plug the builder in**: `app.py:396-399` →
   `ExecutionSignalBridge(engine=..., event_bus=..., hint_builder=chain_hint_builder)`.
   Because `_on_signal_v2` is async, an async builder (fetch chain via
   `data_adapter.get_option_chain` + lot_size via master) is supported — pass a coroutine
   or a small async adapter around the sync `StrategyHints`.

### D. Frontend changes (ProposalQueue.svelte + api.ts)
10. Extend the `Proposal` type and render a **full leg card** in the row: symbol +
    expiry + strike + CE/PE badge, `qty` with lot breakdown (`e.g. 2 lots × 75`), entry
    premium, SL / Target, EV/conviction badge, rationale line. Keep DESIGN.md conventions
    (tabular JetBrains Mono numerals, red=up/green=down untouched).
11. Confirm dialog: show the full leg + a "REAL order" warning in LIVE (already present),
    and surface rationale/SL/Target so the operator can verify before approving.
12. The "DEFAULT HINT" warning badge already exists (line 243) — after the fix it will
    correctly never appear for chain-derived proposals.

### E. Execution changes
13. `_build_order` (or the adapter layer) must resolve the **option ticker** via
    `symbols.to_fyers(symbol, exchange, "OPTION", strike=..., option_type=..., expiry=...)`
    or accept `fyers_symbol` from the hint — never trade the underlying index.
14. Enforce lot-multiple quantity at `_build_order` (guard: `qty % lot_size == 0`) as a
    validation backstop (OrderValidator).
15. Keep approval ID-based (safe once stored hint is complete). Consider echoing the resolved
    leg in the approve response for operator confirmation.

### Test surface
- `tests/` additions: hint generates leg with correct expiry/option_type/lot-rounded qty;
  proposal response serializes leg fields; `_build_order` produces an option OrderRequest;
  Fyers `to_fyers` round-trip for the chosen leg. Existing suites: `tests/execution/`,
  `tests/intelligence/`, `tests/terminal/`.

---

## File map (all touched paths)

| Concern | File |
|---|---|
| StrategyHint model | `src/shettyxtreme/intelligence/hints/strategy_hints.py` |
| New OptionLeg | new file (e.g. `intelligence/hints/option_leg.py`) |
| Hint builder (default → chain) | `src/shettyxtreme/execution/signal_bridge.py` |
| Bridge wiring | `src/shettyxtreme/terminal/api/app.py:396` |
| Execution/order build | `src/shettyxtreme/execution/execution_engine.py:401` |
| OrderRequest fields | `src/shettyxtreme/core/data_models/orders.py:45` |
| API response model | `src/shettyxtreme/terminal/api/models.py:73,148` |
| /strategy-hint endpoint | `src/shettyxtreme/terminal/api/intelligence_router.py:370` |
| Frontend Proposal type | `src/shettyxtreme/terminal/web/src/lib/api.ts:310` |
| ProposalQueue UI | `src/shettyxtreme/terminal/web/src/components/ProposalQueue.svelte` |
| Lot size source (exists, unused) | `src/shettyxtreme/integration/fyers/instrument_master.py` |
| Option ticker builder (exists, unused by exec) | `src/shettyxtreme/integration/fyers/symbols.py:211` |

## Verification of claims

- `StrategyHints` used only in `intelligence_router.py:393` (grep `StrategyHints`).
- `ExecutionSignalBridge` instantiated without `hint_builder` at `app.py:396-399`.
- `default_hint_builder` hardcodes NIFTY/75/MARKET/MIS, `hint_kind="default"` (`signal_bridge.py:38-53`).
- No `OptionLeg` matches in `src/` (grep).
- `ProposalResponse` and TS `Proposal` carry no leg fields.
- `approveProposal` sends only id + confirm flag + CSRF header.
- `_build_order` reads only symbol/exchange/quantity/price/order_type/product from the hint.
- `OrderRequest` has no strike/expiry/option_type; `to_fyers` requires them for OPTION tickers.
