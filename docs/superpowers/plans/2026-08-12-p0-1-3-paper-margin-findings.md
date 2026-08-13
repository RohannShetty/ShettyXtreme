# P0-1.3 Findings — Paper Trading Margin = 0 (all PAPER-mode orders rejected)

**Date:** 2026-08-12 · **Blocker:** P0 · **Status:** Investigation complete — fix not yet applied

**Symptom:** In PAPER mode, every approval is rejected with
`pre-execution risk check rejected: insufficient margin: available=0.00 < required=5000.00`
before the order ever reaches `PaperTradingEngine.place_order`.

---

## 1. The exact failure point

The rejection originates in the **`MarginFilter`** risk filter:

- **`src/shettyxtreme/intelligence/risk/risk_engine.py:113-122`**
  ```python
  def check(self, signal, portfolio):
      required_margin = portfolio.total_margin_used * self.margin_threshold_ratio
      if required_margin <= 0:
          required_margin = 5000.0  # minimum margin for one lot
      if portfolio.available_margin < required_margin:
          return RiskDecision.reject(
              f"insufficient margin: available={portfolio.available_margin:.2f} < required={required_margin:.2f}",
              filter_name=self.name,
          )
      return RiskDecision.allow(self.name)
  ```
  With `total_margin_used=0.0`, `required_margin` floors to **5000.0**. Any
  `available_margin < 5000.0` rejects — and `available_margin` is **0.0**.

- **`src/shettyxtreme/execution/execution_engine.py:330-335`** — `approve()` raises
  `RuntimeError(f"pre-execution risk check rejected: {decision.reason}")` when the
  filter chain rejects. This is the error surfaced to the operator.

## 2. Where margin=0 is read — the full data flow

```
ExecutionEngine.approve()                       execution_engine.py:329
  └─ portfolio = await self._get_portfolio()    execution_engine.py:286-294
       └─ portfolio_provider()                  app.py:357-386  (wired at app.py:388-393)
            └─ risk = risk_proj.get()           RiskProjection (terminal/projections.py:147-189)
                 └─ margin_available            projections.py:160  → **None by default**
                      └─ coerced to 0.0         app.py:380-385 ("Unknown margin (None) → 0.0")
                           └─ MarginFilter      risk_engine.py:113-122  → REJECT
```

### The injection that is missing

`ExecutionEngine` **does** accept a `portfolio_provider: Callable[[], Portfolio]`
(`execution_engine.py:195`) and `app.py` **does** wire one (`app.py:357-391`). The
break is **upstream of the provider**: the provider reads `margin_available` from
`RiskProjection`, and in PAPER mode **nothing ever publishes a real margin value**.

The only source of a real `margin_available` is the **`_margin_poll_loop`**
(`app.py:113-146`), which polls the **Fyers broker adapter**:

- `app.py:122-141` — `adapter = app.state.trading_adapter`; calls
  `adapter.get_margin()`, publishes `{"margin_available": available}` on
  `Topic.RISK_DECISION` only when the broker returns a number.
- **In PAPER mode without Fyers credentials, `trading_adapter` is `None`**:
  - `app.py:230` — `app.state.trading_adapter = None` at lifespan start.
  - `terminal_init.py:128-131` — `init_terminal_adapters` returns early with
    `"No Fyers access token — adapters not initialized"` when there is no session.
  - Therefore the poller publishes **nothing**; `RiskProjection` keeps the honest
    default `margin_available: None` (`projections.py:160`), and the provider coerces
    `None → 0.0` (`app.py:385`).

`RiskBusBridge` (`intelligence/risk/bus_bridge.py:32`) is deliberately conservative:
`self._margin_available: float | None = None`, and it only forwards `margin_available`
into RISK_DECISION payloads when a real source (the poller) supplied it
(`bus_bridge.py:75-76`). This honesty rule (v0.12.0 "fix #2") is exactly what makes
PAPER mode fail closed: no broker → no margin → 0 → reject everything.

## 3. PaperTradingEngine — what it expects vs. what exists

**`src/shettyxtreme/execution/paper_trading.py`** (class at line 18):

- Constructor `__init__(event_bus=None, initial_capital: float = 1_000_000.0)` (line 25-29).
- Tracks `self._capital` / `self._initial_capital` (lines 32-33).
- Exposes P&L + capital via **`get_pnl()`** (lines 95-120): returns
  `available_cash`, `total_invested`, `total_exposure`, etc.
- **It does NOT expose a `Portfolio` and does NOT decrement capital on fills.**
  `_capital` is never updated in `_fill_order` (lines 153-201) or
  `_update_positions` (lines 203-238). `get_pnl()["available_cash"]` is a static
  `1_000_000.0` for the life of the engine — there is no margin accounting on
  fill/close at all.
- The engine never touches `Portfolio`/`available_margin`; it has no concept of
  margin for the risk chain.

**How it is called:** `ModeRoutingExecutor.place_order` (mode_router.py:216-243)
bridges `OrderRequest` → `PaperTradingEngine.place_order`. It passes symbol/exchange/
side/order_type/quantity/price/trigger_price/tag — **no margin, no portfolio, no
capital**. The routing executor is purely a placement target; risk is entirely the
`ExecutionEngine`'s job.

**Lifespan wiring (`app.py:342`):**
```python
paper_engine = PaperTradingEngine(event_bus=_event_bus)
```
Created with the default `initial_capital=1_000_000.0`, stored on
`app.state.paper_engine`, handed to `ModeRoutingExecutor` (app.py:348-354). **Nothing
connects the paper engine's capital to `_portfolio_provider`.** The two subsystems
share the process but no state.

## 4. Margin source classification

| Aspect | Current state |
|---|---|
| **Hardcoded?** | No. v0.12.0 removed the hardcoded "infinite" 1B margin (CHANGELOG.md:298: "Removed hardcoded 'infinite' 1B margin, now uses provider-injected portfolio"). |
| **Config-driven?** | **No.** No `PAPER_TRADING_MARGIN` / `paper_margin` / capital key exists anywhere — not in `configs/default.yaml` (7 lines: broker/config_dir/data_dir/dry_run/log_dir/log_level/mode), not in `ConfigManager._SCHEMA` (`config_manager.py:20-30`), not in `SettingsStore._SPECS` (`core/settings.py:147-157`). |
| **API-driven?** | Partially — LIVE mode gets real margin from `FyersTradingAdapter.get_margin()` (`integration/fyers/trading_adapter.py:426-452`, via `_margin_poll_loop`). PAPER mode has **no API source** (no broker adapter) and no fallback. |
| **Paper engine capital?** | Present but **orphaned** — `PaperTradingEngine._capital` (default ₹10L) is never read by the risk chain, never decremented on fills. |

## 5. Frontend (PositionStrip) — not the bug, but worth noting

- Component: **`src/shettyxtreme/terminal/web/src/components/PositionsRiskStrip.svelte`**.
- Calls `GET /api/execution/positions` and `GET /api/execution/risk`
  (`PositionsRiskStrip.svelte:53-54`).
- Backend: `execution_router.py:192-212` `get_risk` → `RiskResponse` with
  `margin_available=risk.get("margin_available")` — **honest `null` in PAPER mode**
  (`execution_router.py:207`, `models.py:125`).
- The strip renders `margin_available === null` as **"MARGIN UNKNOWN" / "—"**
  (`PositionsRiskStrip.svelte:75, 145, 153-154`). So the UI correctly shows "unknown";
  it is the **risk gate that treats unknown as 0 and rejects**, not the UI.
- No frontend change is required for the core fix; the strip will start showing real
  paper margin once the backend publishes it.

## 6. Git history — what v0.12.0 actually changed (commit `5546354`)

- `intelligence/risk/bus_bridge.py`: `self._margin_available = 0.0` →
  `None`; decision payload now omits `margin_available` unless a real source
  reported it ("fix #2 honesty rule").
- `terminal/api/app.py`: added `_margin_poll_loop`, `_MARGIN_AVAILABLE_KEYS`,
  `_MARGIN_POLL_CADENCE_SECONDS` (30s); `_portfolio_provider` changed
  `available_margin=risk.get("margin_available", 0.0)` →
  `margin_available if margin_available is not None else 0.0`.
- `terminal/projections.py`: `RiskProjection` default `margin_available` → `None`.
- The 1B margin removal is documented in CHANGELOG.md:298 (Wave 7, 2026-07-22).

**Net effect:** the honest-`None` design is correct for LIVE (broker poller exists)
but has **no PAPER-mode source**, so PAPER fails closed with margin 0. The bug is the
missing **paper capital injection**, not the honesty rule itself.

## 7. Proposed fix

### 7.1 Add the config key

Add `paper_trading_margin` (a `float`) to:

1. **`configs/default.yaml`** — e.g. `paper_trading_margin: 1000000` (₹10L, matching
   the existing `PaperTradingEngine.initial_capital` default).
2. **`core/config/config_manager.py`** — add `"paper_trading_margin": (float, type(None))`
   to `_SCHEMA` (line 20-30) and `paper_trading_margin: float | None = None` to the
   `Config` dataclass (line 44-59). `None` = unset (fall back to engine default).
   Optional: env override `SHETTY_PAPER_TRADING_MARGIN` in `_load_env_overrides` (line 105-118).

> Alternative/companion: a `paper_trading_margin` key in the `SettingsStore` schema
> (`core/settings.py:147-157`) so it can be edited at runtime like `loss_limit`. This
> is optional — YAML config is sufficient for the P0, the settings-store route adds
> runtime editability.

### 7.2 Give PaperTradingEngine a portfolio/margin view

Add to **`execution/paper_trading.py`**:

- Track **actual** margin accounting: decrement `_capital` on BUY fills
  (`notional = quantity * fill_price`) and restore on closes/SELLs, so
  `available_margin` reflects open positions (currently `_capital` never moves —
  see §3). This also fixes the stale `available_cash`/`total_invested` in `get_pnl()`.
- Add a method the risk chain can call, e.g.:
  ```python
  def get_portfolio(self) -> Portfolio:
      # available_margin = remaining capital after notional of open positions
      return Portfolio(positions=list(self._positions.values()),
                       daily_pnl=..., total_margin_used=..., available_margin=...)
  ```
  (Constructing `Portfolio` from `core.data_models.Position` — mirror the shape used
  in `execution_engine.py:286-294` / `app.py:357-386`.)
- Alternative minimal surface: `get_margin() -> dict` mirroring the Fyers adapter
  contract (`{"available": ..., "utilized": ..., "total": ...}`) so the existing
  `_margin_poll_loop` could treat the paper engine as a drop-in "adapter".

### 7.3 Inject into the risk chain (lifespan, `app.py`)

In `lifespan` (around app.py:342-391):

```python
paper_engine = PaperTradingEngine(
    event_bus=_event_bus,
    initial_capital=config.paper_trading_margin or 1_000_000.0,
)
```

and in `_portfolio_provider` (app.py:357-386), **when the current mode is PAPER**
(and `margin_available` is `None`), fall back to the paper engine's capital:

```python
margin_available = risk.get("margin_available")
if margin_available is None and get_mode_value().upper() == "PAPER":
    paper = getattr(app.state, "paper_engine", None)
    margin_available = paper.get_portfolio().available_margin if paper else None
```

Mode-aware so LIVE keeps the honest broker value and PAPER gets simulated capital.
(The `mode` gate is already available via `get_mode_value`.)

### 7.4 Keep margin fresh on fill/close

`PaperTradingEngine._fill_order` (paper_trading.py:153-201) already publishes
`POSITION_CHANGED` (line 193-196). `RiskBusBridge` subscribes to `POSITION_CHANGED`
(bus_bridge.py:39) — so **if the paper engine's `get_portfolio()`/margin is made the
source** (via §7.2-7.3) and/or the poller's publish path is used, margin updates flow
through the existing bus without new plumbing. Two concrete options:

- **Option A (recommended):** `_portfolio_provider` reads
  `paper_engine.get_portfolio()` live on every `approve()` — always fresh, zero bus
  latency.
- **Option B:** mirror Fyers: make `_margin_poll_loop` poll the paper engine when
  mode is PAPER and publish via RISK_DECISION (reuses RiskBusBridge/RiskProjection
  unchanged). Slightly stale (30s cadence) but keeps one margin pipeline.

## 8. Reusable existing code

| Asset | Where | Reuse |
|---|---|---|
| `Portfolio` dataclass | `intelligence/risk/risk_engine.py:21-27` | Construct from paper engine state |
| `portfolio_provider` injection point | `execution/execution_engine.py:195, 286-294` | Already wired; just needs PAPER fallback |
| `_margin_poll_loop` + `_MARGIN_AVAILABLE_KEYS` | `app.py:113-146` | Pattern for Option B (paper-as-adapter) |
| `FyersTradingAdapter.get_margin` | `integration/fyers/trading_adapter.py:426-452` | Contract template for `PaperTradingEngine.get_margin()` |
| `RiskBusBridge` `POSITION_CHANGED` listener | `intelligence/risk/bus_bridge.py:39,48-52` | Already receives paper fill events — margin_used updates free |
| `PaperTradingEngine.get_pnl()` | `paper_trading.py:95-120` | `available_cash`/`total_exposure` already computed |
| `get_mode_value` | `app.py` (mode provider) | Mode-gate the PAPER fallback |

## 9. Tests to add (once fixed)

- `tests/execution/test_paper_trading.py` — `get_portfolio()` returns
  `available_margin == initial_capital` at start; BUY fill reduces it; SELL/close
  restores it.
- `tests/wave2/test_risk_engine.py` (TestMarginFilter, line 84) — with a
  paper-funded `Portfolio(available_margin=1_000_000)`, entry is allowed (mirror
  `test_margin_sufficient_allows_entry`).
- `tests/terminal/test_projections.py` / `tests/intelligence/test_risk_bus_bridge.py`
  — PAPER-mode margin flows RISK_DECISION → RiskProjection → `_portfolio_provider`
  end-to-end (currently `margin_available is None` is asserted at
  test_projections.py:178).
- Integration: PAPER-mode `ExecutionEngine.approve()` succeeds for a real signal
  (currently it raises at execution_engine.py:335).

## 10. Verification steps

1. `.venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider` (1012-pass baseline).
2. `grep -r "import openalgo\|from openalgo" src/` → zero matches.
3. Manual: `run.py --mode PAPER` → approve a proposal → fill succeeds; risk strip
   shows real margin instead of "MARGIN UNKNOWN".
