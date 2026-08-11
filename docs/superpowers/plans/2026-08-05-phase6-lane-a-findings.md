# Phase 6 · Lane A — F-CORE-001 Model Consolidation: Findings

**Date:** 2026-08-05
**Status:** Complete — all pairs consolidated, 1182 tests passing
**Recon source:** `docs/superpowers/plans/2026-08-05-phase6-recon.md` §1
**Scope:** Divergent model pairs in `core/interfaces/` vs `core/data_models/`; `oi` bus flow

---

## 1. What was consolidated

| Pair | Before | After | Verdict |
|------|--------|-------|---------|
| **Tick** | interfaces had `oi`, data_models didn't | One class in `data_models` **with `oi: int \| None = None`**; interfaces re-exports | ✅ Merged — `oi` no longer dropped at the bus boundary |
| **Bar** | byte-identical | One class in `data_models`; interfaces re-exports | ✅ Merged (no field change) |
| **Order** | interfaces = placement *request* (enums, no `order_id`); data_models = *record* (`order_id`, `status: str`, `created_at`) | Placement renamed **`OrderRequest`** (lives in `data_models`); record stays **`Order`** | ✅ Kept distinct by name — shapes are genuinely different, merging would break execution_engine/validator/adapter |
| **OrderResult** | interfaces `status: OrderStatus` enum + `rejected_reason`; data_models `status: str`, no reason | One class in `data_models`: `status: OrderStatus` + `rejected_reason: str \| None = None`. **`OrderStatus` is now a `str`-subclassed enum** so enum and plain-string statuses compare equal in both directions | ✅ Merged (enum-vs-str resolved via str-compatible enum) |
| **Position** | interfaces had `day_buy_quantity`/`day_sell_quantity` (required); data_models lacked them | One class in `data_models` with the two fields **appended with `= 0` defaults** | ✅ Merged — **correction to recon §1.1**: the pairs were NOT field-identical (recon missed the two day-qty fields). Appending (not inserting) preserves `Position("A","NSE",75,100,0,75,0,0,"NRML")` 9-arg positional constructions in tests |
| **Holding / OrderBook** | interfaces only (account_info.py) | Moved to `data_models`; interfaces re-exports | ✅ Canonicalized (singletons, not a pair) |
| Quote / OptionChain / OptionContract / Fill / Trade | data_models only | unchanged | ✅ No conflict |

**Enums** (`OrderSide`, `OrderType`, `ProductType`, `OrderStatus`) are now canonical in `core/data_models/orders.py`, subclassing `str` — this keeps `OrderValidator`'s string-tolerant checks and `mappings.py`'s enum-keyed dicts working with both member and plain-string values.

## 2. Architecture outcome

- **`core/data_models/`** = single source of truth for every data class + enum.
- **`core/interfaces/`** = Protocols only (`OrderExecutor`, `MarketDataStream`, `AccountInfo`, `DataProvider`, `BrokerGateway`, callback type aliases); each module re-exports the canonical data classes from `data_models`.
- Both packages export the *same class objects*, so:
  - `from core.interfaces import Tick` and `from core.data_models import Tick` are the **same class** — `isinstance` dispatch works on either side of the bus.
  - The `terminal_init._to_bus_tick` isinstance gate is now a pass-through no-op (kept for foreign shapes, fallback also forwards `oi`).
- `core/interfaces/order_executor.py` `OrderExecutor` protocol signature now reads `place_order(order: OrderRequest) -> OrderResult` — matching the placement semantics.

## 3. `oi` now flows through the bus (the live bug)

Chain before: `data_adapter._parse_tick` (emits interfaces.Tick with `oi` from SDK `OI` key) → `_to_bus_tick` **dropped `oi`** (no field on data_models.Tick) → bar builder / OI tracker never saw live open interest.

After: interfaces.Tick IS data_models.Tick (has `oi`), so the bridge passes ticks through untouched and `BarBuilderState.apply_tick` / `options/oi_tracker` receive real OI values. The fallback constructor in `_to_bus_tick` also forwards `oi` via `getattr(tick, "oi", None)`.

## 4. Files changed (Lane A scope)

**Canonical models**
- `core/data_models/market_data.py` — `Tick.oi` added
- `core/data_models/orders.py` — rewritten: str-enums, `OrderRequest`, merged `OrderResult`, merged `Position`, moved `Holding`/`OrderBook`
- `core/data_models/__init__.py` — full export surface

**Interfaces alias layer**
- `core/interfaces/order_executor.py` — Protocol only, re-exports data classes, signature → `OrderRequest`
- `core/interfaces/market_data_stream.py` — Protocol only, re-exports Tick/Bar
- `core/interfaces/account_info.py` — Protocol only, re-exports Position/Holding/OrderBook
- `core/interfaces/__init__.py` — re-export union

**Consumers (request `Order` → `OrderRequest`, imports → data_models)**
- `execution/execution_engine.py` (`PendingApproval.order`, `approve`, `_build_order`)
- `execution/mode_router.py` (`place_order`/`modify_order`/`_place_paper`; dropped unused `OrderType` import)
- `execution/signal_bridge.py` (enums → data_models)
- `integration/order_validator.py` (`validate(order: OrderRequest)`)
- `integration/fyers/trading_adapter.py` (data imports → data_models, `OrderRequest`)
- `integration/fyers/mappings.py` (enums → data_models)
- `integration/fyers/data_adapter.py` (Tick/Bar → data_models; keeps callbacks from interfaces)
- `integration/fyers/_util.py` (Bar → data_models)
- `terminal/api/terminal_init.py` (`_to_bus_tick` oi pass-through)

**Tests**
- `tests/execution/test_mode_router.py`, `tests/wave1/test_order_validator.py`, `tests/integration/test_fyers_trading_adapter.py`, `tests/integration/test_fyers_mappings.py`, `tests/wave5/test_proposal_flow.py`, `tests/wave5/test_execution_engine.py` — `Order`→`OrderRequest`, imports → data_models
- **NEW `tests/core/test_model_consolidation.py`** (30 tests) — regression suite: pair identity (`interfaces.X is data_models.X` for every pair), `oi` bridge flow, `OrderRequest` vs `Order` shapes, str-compatible `OrderStatus`, `Position` dual construction styles, enum identity.

Untouched by Lane A (but modified in the shared tree by parallel lanes B/C/D): `execution/kill_switch.py`, `terminal/api/{analytics_models,analytics_router,execution_router,models,watchlist_router}.py`, `terminal/static/*`, `terminal/web/src/*`, `tests/{execution/test_kill_switch_gate.py, wave3/test_api.py, wave7/test_watchlist_hydration.py, wave9/test_analytics_api.py, integration/test_fyers_data_adapter.py}`.

## 5. Verification

| Gate | Result |
|------|--------|
| `pytest tests/ -q --tb=short --basetemp=... -p no:cacheprovider` | ✅ **1182 passed / 0 failed / 0 errors** (fresh basetemp) |
| `grep "import openalgo\|from openalgo" src/` | ✅ zero matches |
| No file > 1000 lines | ✅ none |
| `core/` external-import layering | ✅ only stdlib / relative / `shettyxtreme.core.*` — the pre-existing `yaml` import in `core/config/config_manager.py` remains (documented in AGENTS.md, out of scope) |
| `graphify update .` | ✅ updated |

**Note on a flaky Windows quirk (not caused by this change):** one full-suite run reported 10 setup errors — `PermissionError` deleting a `research.db` temp file still held open by a research-store test (sqlite handle leak at teardown, pre-existing). The affected files pass in isolation, and a re-run with a fresh `--basetemp` passes the entire suite cleanly. Lane A introduces no sqlite/file-handle usage.

## 6. Caveats / follow-ups

- **Two `Order` names remain** (deliberate): `OrderRequest` (placement) and `Order` (record). Any future API that places orders should type against `OrderRequest`; anything reading broker/paper state against `Order`.
- `WatchlistProjection` broadcast payload still narrows to 5 fields — extending the wire payload with `oi`/`strike`/`option_type` is Lane C (roadmap #2), not this lane.
- `core/interfaces/__init__.py` re-exports the record `Order` too, so any code that previously imported the *request* via `core.interfaces.Order` would now silently get the record — all such call sites were migrated to `OrderRequest` in this pass (verified by full-suite green).
