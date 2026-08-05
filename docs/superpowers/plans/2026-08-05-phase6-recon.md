# Phase 6 Recon — Findings & Execution Plan

**Date:** 2026-08-05
**Status:** Reconnaissance complete · Phase 5 done (1116 tests passing, v0.13.0)
**Scope:** Roadmap items 1–11 (`docs/superpowers/plans/2026-08-05-phase4-plus-roadmap.md` §5)
**Baseline gates:** full pytest suite · `npm run check` 0 errors · `npm run build` · `graphify update .`

---

## 1. F-CORE-001 — Divergent model pairs (roadmap #1, 2–3 days)

### 1.1 Duplicated models (interfaces vs data_models)

| Model | `core/interfaces/` | `core/data_models/` | Verdict |
|-------|--------------------|---------------------|---------|
| **Tick** | `market_data_stream.py:8-12` — **has `oi`** | `market_data.py:13-16` — **no `oi`** | Divergent — **`oi` is silently dropped at the bus boundary** (`terminal/api/terminal_init.py:63-75`, `_to_bus_tick` never copies `oi`) |
| **Bar** | `market_data_stream.py:15-18` | `market_data.py:7-10` | Byte-identical — clean merge |
| **Order** | `order_executor.py:31-42` — placement *request* (enums `OrderSide/OrderType/ProductType`, no `order_id`) | `orders.py:7-12` — order *record* (`order_id`, `status: str`, `created_at`) | **Not a pure duplicate — semantically different shapes.** A naive merge breaks `execution_engine` / `order_validator` / `trading_adapter` |
| **OrderResult** | `order_executor.py:45-51` — `status: OrderStatus` enum + `rejected_reason` | `orders.py:15-17` — `status: str`, no `rejected_reason` | Divergent (enum vs str) |
| **Position** | `account_info.py:7-11` | `orders.py:26-28` | Field-identical — clean merge |
| (Holding, OrderBook, Quote, OptionChain, OptionContract, Fill, Trade) | Holding/OrderBook only in interfaces (`account_info.py:14-22`); Quote/Chain/Contract only in data_models (`market_data.py:19-31`); Fill/Trade only in data_models (`orders.py:20-36`) | — | No conflict |

Both packages re-export the overlapping names: `interfaces/__init__.py:1-5`, `data_models/__init__.py:1-3` — so `from ...core.interfaces import Tick` and `from ...core.data_models import Tick` can both exist in one process.

### 1.2 Import map (who imports what)

**`core.interfaces` importers (src, 10 files):**
- `integration/fyers/data_adapter.py:25` (Tick, Bar, callbacks)
- `execution/order_validator.py:18` · `execution/signal_bridge.py:27` · `execution/mode_router.py:25` · `execution/execution_engine.py:27` (order_executor)
- `integration/fyers/trading_adapter.py:24-25` (account_info + order_executor)
- `integration/fyers/mappings.py:20` · `integration/fyers/_util.py:185` (order_executor / Bar)
- comments only: `terminal/api/market_router.py:8`, `terminal/api/terminal_init.py:55-57`

**`core.data_models` importers (src, 22 files):**
- `terminal/projections.py:13` · `terminal/api/scanner_data.py:12` · `terminal/api/terminal_init.py:59` · `intelligence/pipeline.py:21` · `intelligence/features/adapters.py:13` · `feature_engine.py:9` · `intelligence/features/indicators/{atr,adx,rsi,bars,vwap,sma,ema}.py` (Tick)
- `intelligence/scanners/{gap_scanner,breakout_scanner}.py` · `options/oi_tracker.py:15` (Bar)
- `execution/paper_trading.py:14` · `learning/outcome_tracker.py:17` (orders: Order/Fill/OrderResult/Position)
- `intelligence/risk/risk_engine.py:13` · `terminal/api/app.py:329` (Position)
- `core/interfaces/broker_gateway.py:3-5` composes the three interface modules

**Tests (~15 files):** `tests/{wave1..9, integration, execution, intelligence, terminal, options}` — both sides imported (e.g. `tests/integration/test_fyers_data_adapter.py:15` → interfaces Tick; `tests/intelligence/test_gap_scanner.py:13` → data_models Bar).

### 1.3 What breaks on consolidation

1. **`_to_bus_tick` isinstance gate** (`terminal_init.py:61`) — the bridge only works because the two Tick classes are *distinct*; after unification it becomes a no-op guard (safe), but **before** unification the `oi` field loss (1.1) is the live bug today.
2. **The two `Order` classes have different constructors** — `mode_router._place_paper` (`mode_router.py:161-182`) already hand-bridges interfaces.Order → paper kwargs; `execution_engine.py` builds interfaces.Order; `paper_trading.py` consumes data_models.Order. Any merge must keep both call sites compiling.
3. **`isinstance`-based dispatch** in `projections.py:30` and `scanner_data.py` keys on the bus (data_models) Tick; adapters emit interfaces Tick — the bridge keeps them apart.

### 1.4 Blast radius

- **~32 src files** touch the models (10 interfaces + 22 data_models importers) + **~15 test files**.
- Only ~10 construct the dataclasses; the rest import for typing.
- **Recommended strategy:** canonicalize in `core/data_models` (the "standard models" layer, already imported by the bus-facing side), then make `core/interfaces` re-export the same classes (keep protocol files untouched) — one alias layer, `isinstance` works everywhere, `oi` starts flowing. Rename the placement `Order` → `OrderRequest` (or keep two names) since shapes differ. Compat aliases keep the diff mechanical; ~1 day of the 2–3 is test churn.

---

## 2. Live chain on the wire (roadmap #2, 1.5 days)

### 2.1 Current tick broadcast structure

- **Adapter parse** → `_parse_tick` (`data_adapter.py:154-199`): `{symbol, exchange, ltp, volume(vol_traded_today), timestamp(last_traded_time), bid, ask, open, high, low, close(prev_close_price), oi(OI — uppercase, data_val ticks only)}`. F-INT-005 (live OI) is **already done** here.
- **Bus bridge** → `_to_bus_tick` (`terminal_init.py:52-75`) converts interfaces.Tick → data_models.Tick, **dropping `oi`** (no field on the bus class).
- **Projection** → `WatchlistProjection.on_market_data` (`projections.py:28-60`) broadcasts `tick` with **only** `{symbol, ltp, change_pct, volume}` (`projections.py:55-60`).
- **Wire** → `ws_bridge.broadcast` (`ws_bridge.py:26-39`) → `ws_manager.broadcast` (`ws_manager.py:105-127`, topic-filtered, `default=str` JSON).

### 2.2 What is missing for the chain

| Field | Streamable today? | Where it is dropped |
|-------|-------------------|---------------------|
| `strike` | **Yes** — `from_fyers(ticker)` already returns `strike` (`symbols.py:349-356, 364-369`) at `data_adapter.py:176-182` | Dropped: neither Tick class has the field |
| `option_type` | **Yes** — same `from_fyers` dict (`symbols.py:355, 370`) | Same drop |
| `oi` | **Yes** — parsed at `data_adapter.py:183-198` | Dropped by `_to_bus_tick` (`terminal_init.py:63-75`) |
| `iv` | **No** — the HSM symbol-update feed has no IV field. IV only exists in `/data/options-chain-v3` REST (`data_adapter.py:384-397` → `intelligence_router.py:161-191`) | Not a broadcast problem — **source limitation** |

**Honest finding:** `strike`/`option_type`/`oi` can ride the wire today with a Tick field-add + payload extension; **`iv` cannot go fully live** — the 15s REST poll (below) must remain for IV (or accept stale IV per refresh cycle).

### 2.3 Where data is available but not broadcast

- `data_adapter.py:176-182` — strike/option_type computed by `from_fyers` then discarded.
- `terminal_init.py:63-75` — oi dropped at the bus boundary (also affects the bar builder / scanners).
- `projections.py:34-41` — the dict is narrowed to 5 fields before broadcast (payload widening is a 4-line change; the chain contract parse regex `ChainGrid.svelte:150-157` (`parseTickKey`) becomes redundant once strike/option_type ride along).

### 2.4 Per-contract subscription scope

- **Today:** topic-only. `ws_manager._topics: dict[WebSocket, set[str]]` (`ws_manager.py:56`); `broadcast` filters by topic (`ws_manager.py:114-116`); the frontend subscribes to the `tick` topic globally (`ws.ts:146-166`). Every client receives every watchlist tick.
- **Server-side HSM:** `FyersDataSocketWrapper.subscribe` (`data_socket.py:205-221`) already supports per-symbol subscribe/unsubscribe — and the adapter only subscribes the socket to **watchlist symbols** (`terminal_init.py:198-199`). But there is **no client→server symbol-interest signal** (the `/ws` subscribe frame carries topics only).
- **Scope options:**
  1. *Payload-level (cheap, no protocol change):* add `symbol` + `strike`/`option_type` to every tick; clients filter. Reduces *client work* but not *bandwidth*.
  2. *Symbol-routed (real scope):* extend `ws_bridge` with `{symbol → set[WebSocket]}` and extend the `/ws` subscribe frame (`ws.ts:74-78` + `ws_manager.subscribe` `ws_manager.py:77-89`) to carry symbols. ChainGrid then subscribes only its ~100 contracts; non-subscribed clients keep topic fallback (`ws_manager.py:112-116` already preserves unfiltered delivery for clients with no declared set).
  3. *HSM-interest-driven:* only subscribe symbols with ≥1 interested client (`data_socket.py:205-221` per-symbol API) — saves Fyers socket capacity too. This is the "true" fix but couples chain state to connection state (reconnect re-subscription on `_apply_subscriptions`, `data_socket.py:330-340`).

**Recommendation:** (1) lands the chain on the wire immediately; (2) is the Phase-6 scope item; (3) is follow-up — note `ChainGrid.applyTick` (`ChainGrid.svelte:163-201`) already handles explicit `strike`/`option_type` fields ("future payload" branch at lines 166-175), so the frontend is ready.

**Note:** ChainGrid's 15s poll (`REFRESH_MS = 15000`, `ChainGrid.svelte:47`, `refreshSilently` at 249-261) hits `/api/intelligence/options` (`intelligence_router.py:303-323`) — after the wire extension this poll only needs to stay for IV, so the 15s cadence can be relaxed.

---

## 3. Watchlist hydration batching (roadmap #3 — F-TERM-003, 1–2 days)

### 3.1 Current hydration flow (REST call count)

`GET /api/watchlist` (`watchlist_router.py:72-89`) → `_hydrate_from_rest` (`watchlist_router.py:36-69`):
- Iterates projection rows **sequentially** (`watchlist_router.py:50`) — no `asyncio.gather`.
- Skips rows with `ltp > 0` (already live) — the fallback only fires when the feed is idle (`watchlist_router.py:51-52`).
- For each idle symbol: `adapter.get_ohlc(query)` (`watchlist_router.py:56`) → **1 REST call** to `/data/quotes?symbols={ticker}` (`data_adapter.py:344-361`); on no ltp, a **second** call `get_ltp` (`watchlist_router.py:59` → `data_adapter.py:363-382`).

**Cost:** N idle symbols = **N (worst case 2N) sequential REST calls**. The token bucket throttles at ~8 req/s burst 8 (`client.py:43-44`, `_TokenBucket` at `client.py:99-126`), so 10 idle symbols ≈ **1.25 s of pure throttle wait** before any latency. The roadmap's "2N sequential Fyers calls" description matches exactly.

### 3.2 Fyers API limits (batching feasibility)

- `/data/quotes` accepts **comma-separated symbols** — the roadmap's "≤50-symbol grouping" convention. The response is a dict keyed by ticker (`data_adapter.py:352-353`). **The current code always passes a single symbol — the multi-symbol capability is unused.**
- Rate cap is the client's own 8/s token bucket (`client.py:43`); Fyers bans for a full day on abuse (`client.py:47-48`) — never burst past the bucket.
- **Batching opportunity:** add `get_quotes(symbols: list[str])` to the adapter (one `/data/quotes` call with comma-joined tickers, dict parse). Group idle symbols into ≤50-ticker batches → **10 idle symbols = 1 call instead of 10**. `get_ohlc` and `get_ltp` (`data_adapter.py:344-382`) are near-duplicates — fold both into the batched method (merge `watchlist_router.py:56-59` into a single batched lookup).
- **Parallelism vs grouping:** grouping matters more than concurrency — the 8/s bucket serializes anyway. Optionally run multi-batch `asyncio.gather` for latency, but never bypass the bucket.
- Also consider a small TTL cache on the hydration result so a fast-clicking client doesn't re-trigger the loop on every `GET` (`watchlist_router.py:77` hydrates unconditionally per request).

---

## 4. Tab keep-alive (roadmap #4, 1 day)

### 4.1 Current tab switching logic (`terminal/web/src/App.svelte`)

- **ChainGrid: always mounted**, hidden via `class:hidden={$activeTab !== "chain"}` (`App.svelte:93-95`).
- **Scanner / Hints / Analytics: conditionally mounted** with `{#if $activeTab === "…"}` (`App.svelte:96-110`) → **remounted on every tab switch**.

### 4.2 State lost on remount

- Component-local `$state`: scroll positions, applied filters, loaded data, selected rows, in-flight requests.
- `onMount` re-runs: WS subscriptions re-established (`onMessage`), timers restart (e.g. ScannerPanel/ChainGrid polling), initial fetches re-fire — the roadmap's "remount + re-fetch on every tab switch" (S5 §4.5 / current-ui-analysis #2).

### 4.3 Keep-alive implementation options (Svelte 5)

1. **Hidden-not-unmounted (recommended):** render all three panels always, hide with `class:hidden` exactly like ChainGrid (`App.svelte:93`). Smallest diff (swap three `{#if}` blocks for `class:hidden` divs), kills re-fetch churn, preserves all state + WS subscriptions. Cost: 3 extra mounts/fetches at boot; panels idle-hidden (add `inert`/`aria-hidden` for a11y if needed).
2. **Store-backed state:** move each panel's state to module-level `$state` runes so a remount re-reads state — heavier refactor, only needed if boot-mount cost is unacceptable.
3. **Component-instance caching:** Svelte 5 has no built-in `<KeepAlive>`; a `$state` map of mounted components is overkill here.

**Recommendation:** option 1 — it matches the established ChainGrid pattern and is a ~30-line diff. The tab-panel layout (`App.svelte:176-189`, flex column) must keep `display:none` panels out of layout — `class:hidden` uses `display:none`, safe.

**Same-file coupling (roadmap §5 note):** item 8 (LIVE banner 4th grid row, `App.svelte:146-152` currently 3 rows `auto minmax(0,1fr) auto`) edits the same file — **serialize 4 → 8** (same writer).

---

## 5. Kill switch race (roadmap #9 — Oracle #4, 1–2 days)

### 5.1 Current implementation

- **File-based:** `~/.shetty_kill_switch` (`terminal/api/execution_router.py:46`), armed via `Path.touch()` / disarmed via `unlink` (`execution_router.py:267-277`); read via `os.path.exists` in `is_kill_switch_armed()` (`execution_router.py:58-60`). Initialized at import time so a previous process's kill survives restarts (`execution_router.py:44-46`).
- **Wiring:** `app.py:323` passes `kill_switch_provider=is_kill_switch_armed` into `ModeRoutingExecutor`.
- **Enforcement points:**
  - `mode_router.place_order` → `if self._kill_provider(): reject` (`mode_router.py:56-59`)
  - `mode_router.modify_order` → `mode_router.py:103-106`
  - `mode_router.cancel_order` (LIVE) → `mode_router.py:130-132`
  - `execution_router.approve_proposal` → `execution_router.py:324-325` (checked again inside `mode_router.place_order` via `engine.approve` → double check exists)

### 5.2 Where the race occurs

1. **Check-to-wire TOCTOU (primary):** `mode_router.py:56` reads the file → `await live.place_order(order)` at `mode_router.py:83` is an **await point**. An operator arming the switch *after* the gate passes does not stop the in-flight placement — the order lands after "kill armed" was shown. The paper path has the same shape (`mode_router.py:68` → `_place_paper`, `mode_router.py:161-182`).
2. **Two separate checks** (`execution_router.py:324` + `mode_router.py:56`) are each individually TOCTOU — the gap between them is *closed* (a second gate before the wire), so ordering is decent, but neither is atomic with the wire.
3. **No in-flight notification:** arming only affects the *next* call (lazy providers, `mode_router.py:17-18`). Nothing signals an in-progress placement, and nothing records whether an order crossed the wire inside the arm window.
4. **File semantics:** `touch`/`unlink`/`exists` are not atomic against concurrent arm/disarm requests (two parallel POSTs can interleave). Low severity — but an `os.replace`-style atomic write is trivial.

### 5.3 Synchronization needed

- **In-process:** an `asyncio.Event`-based kill gate shared by `execution_router` and the mode router. `place_order` should **double-check immediately before** `live.place_order` (`mode_router.py:83`) — after any pre-await, shrinking the window to the final call (inherent TOCTOU remains, but is minimal).
- **Honest reporting:** log/surface whether any placement crossed the wire during the arm window ("placed just before kill") — Phase-1.0 honesty-first principle.
- **Cross-process:** keep the file for persistence + restart survival; add atomic write (`tempfile` + `os.replace`) and read-once-per-placement.
- **Scope audit:** enforcement lives only in `ModeRoutingExecutor` + `approve_proposal` — grep confirms no direct `live.place_order` bypass in `src/`, so the gate coverage is complete today.

---

## 6. Component migration candidates (roadmap #10, 3–5 days)

### 6.1 Existing `ui/` inventory (`terminal/web/src/lib/components/ui/`)

**12 families present:** `badge`, `button`, `card` (6), `checkbox` (2), `dialog` (10), `input` (2), `label`, `table` (7), `tabs` (4), `textarea` (2), `tooltip` (3).

### 6.2 Missing (roadmap #10 list) + migration value

| Component | Present? | Value / rationale |
|-----------|----------|-------------------|
| **scroll-area** | ❌ | **Highest value.** `ChainGrid .table-wrap` (`ChainGrid.svelte:494-497`) and `Watchlist .list` / right-col all hand-roll `overflow:auto` native scrollbars — the most visible "not-DESIGN" element. A shadcn scroll-area port (custom scrollbar) also pre-pays Phase 7 #4. |
| **select** | ❌ | Native `<select>`s remain in `ChainGrid` expiry selector (`ChainGrid.svelte:327-331`) and ResearchPanel filters (roadmap §2.2 #8). OS-default styling breaks DESIGN.md. |
| **dropdown-menu** | ❌ | Prerequisite for select; also needed for Phase 7 #2 command palette. |
| **skeleton** | ❌ | ChainGrid `loading` state (`ChainGrid.svelte:56, 402-404`) and ScannerPanel show raw empty text; skeleton is the DESIGN answer. |
| **separator** | ❌ | Right-dock `drawer-head` (`App.svelte:114-123`), panel headers — cheap cosmetic. |
| **sonner** | ❌ | `AlertProjection` broadcasts alerts (`projections.py:189-208`) but there is **no toast surface** in the UI — sonner would wire WS alerts → toasts. |
| **kbd** | ❌ | For Ctrl+R/Ctrl+M/Ctrl+F shortcut hints (`App.svelte:43-55`, Phase 7 #11) — only useful once shortcut UI/docs exist. **Lowest priority.** |

### 6.3 Notes

- Port with the repo-local `.skills/` (`design-system`, `industrial-brutalist-ui`, `ui-ux-pro-max-data`) with DESIGN.md as the contract — **red = up `#f6525c`, green = down `#2ebd85`, JetBrains Mono tabular numerals / Inter labels are binding** (never "fix" the Indian price convention).
- Touches only `ui/` + adopting consumers — fully parallel to every other lane. Bundle-size check after adding dependencies.

---

## 7. Dependency graph (what must come first)

```
F-CORE-001 (#1) model consolidation
   │  every backend item that touches Tick/Order/Bars inherits the canonical classes
   ▼
#2 live chain on the wire ── needs strike/option_type/oi fields on Tick
   │  (or a non-breaking field-add to both Tick classes — see §2.4 rec. 1)
#3 hydration batching        independent (data_adapter + watchlist_router only)

#4 tab keep-alive ─► #8 LIVE banner    same file App.svelte — SAME WRITER, serialized

#5 ChainGrid container-query ── shares ChainGrid.svelte with #2 (payload consumer)
#6 TableRow rest-forwarding       independent primitive, needed by #5/#10
#7 selection.ts → {symbol,exchange} ── shares Header.svelte + ChainGrid.svelte with #5

#9 kill switch race      independent (execution/ + execution_router.py)
#10 component migration  independent (ui/ only + adopters)
#11 scorecard regime     tiny, independent (analytics_router + AnalyticsPanel.svelte)
```

**ChainGrid.svelte is the serialization hotspot:** edited by #2 (tick payload consumer), #5 (container-query), #7 (selection) — one writer at a time over that file.

## 8. Parallelization opportunities (what can run concurrently)

| Lane | Items | Files | Notes |
|------|-------|-------|-------|
| **A — architecture** | #1 F-CORE-001 (2–3 d) | `core/interfaces/*`, `core/data_models/*`, ~32 importers | Run first; everything inherits it |
| **B — money-path** | #9 kill switch (1–2 d) | `execution/mode_router.py`, `terminal/api/execution_router.py` | Fully parallel with A |
| **C — integration** | #2 live chain (1.5 d) ∥ #3 batching (1–2 d) | `terminal/projections.py`, `data_adapter.py`, `terminal_init.py`, `watchlist_router.py`, `ws_bridge.py`, `ws_manager.py`, `ws.ts` | #3 independent; #2 depends on A's Tick (or a field-add) |
| **D — frontend** | #4→#8 serialized (same writer: App.svelte) ∥ #5 ∥ #6 ∥ #7 | `App.svelte`, `ChainGrid.svelte` (serialized #2→#5→#7), `table-row.svelte`, `selection.ts`, `Header.svelte` | #6 (4 h) anywhere; #11 (2 h) anywhere |
| **E — ui-lib** | #10 (3–5 d) | `web/src/lib/components/ui/` only | Parallel to everything; adopters land later |

## 9. Risk assessment (what could break)

| Item | Risk | Mitigation |
|------|------|------------|
| **#1 F-CORE-001** | **Highest.** 32 src + 15 test files; the two `Order` classes are semantically different (request vs record) — a naive merge breaks `execution_engine`, `order_validator`, `trading_adapter`, `mode_router` | Canonicalize in `data_models`, re-export from `interfaces` (aliases); keep `isinstance` dispatch working (`terminal_init.py:61`); full suite + layering grep + `grep openalgo` gate |
| **#2 live chain** | Broadcast payload growth — frontend already tolerant (`ChainGrid.svelte:166-175` "future payload" branch). WS protocol change (per-symbol subscribe) touches both sides | Add fields incrementally (backward-compatible); keep topic fallback (`ws_manager.py:112-116`); ship payload extension first, symbol-routing second |
| **#3 batching** | Rate-limit abuse → Fyers **full-day ban** on 429 storms (`client.py:47-48`) | Cap groups ≤50; never bypass the 8/s token bucket (`client.py:43`); test with a mocked transport |
| **#4 keep-alive** | Hidden-but-mounted panels run boot-time fetches/timers (3 extra polls at startup); `display:none` must not break flex layout | `class:hidden` (display:none, safe for flex); optionally lazy-mount first-visited tabs |
| **#9 kill switch** | Money-path semantics — a bad gate blocks OBSERVER/PAPER or lets LIVE through | Keep file persistence + restart survival (`execution_router.py:44-46`); add asyncio gate + double-check before the wire (`mode_router.py:83`); regression tests for all three modes |
| **#10 components** | New deps → bundle size; DESIGN.md tokens must match (red=up/green=down binding) | `npm run check` + `npm run build` gate; port with `.skills/` design skills; verify against DESIGN.md §4 |

## 10. Estimated effort per item

| # | Item | Effort | Depends on |
|---|------|--------|-----------|
| 1 | F-CORE-001 model consolidation | **2–3 days** | — |
| 2 | Live chain on the wire | **1.5 days** | #1 (or field-add) |
| 3 | Hydration batching | **1–2 days** | — |
| 4 | Tab keep-alive | **1 day** (≈4 h for hidden-not-unmounted) | — |
| 5 | ChainGrid container-query | **1 day** | — (CSS only) |
| 6 | TableRow rest-forwarding | **4 h** | — |
| 7 | selection.ts {symbol, exchange} | **1 day** | — |
| 8 | LIVE banner 4th grid row | **4 h** | #4 (same file) |
| 9 | Kill switch race | **1–2 days** | — |
| 10 | Component migration wave 1 | **3–5 days** | — |
| 11 | Scorecard carries current_regime | **2 h** | — |
| | **Total** | **~13–18 days** | ~1–2 weeks wall-clock with 5 lanes |

## 11. Recommended execution order

```
Week 1 (parallel):
  Lane A: #1 F-CORE-001            Lane B: #9 kill switch
  Lane C: #3 batching (no dep)     Lane E: #10 ui-lib (no dep)
  #11 (2 h, anyone)

After #1 lands (or alongside via field-add):
  Lane C: #2 live chain  — payload extension first, symbol-routing second

Week 1–2 (frontend, one writer per file):
  Lane D: #4 → #8 (App.svelte serialized), #6 (4 h) in a gap,
          #7 after #5 (ChainGrid serialized: #2 → #5 → #7)

Gate after each item: full pytest suite (1116 baseline) ·
npm run check 0 errors · npm run build · graphify update .
```

**Sequencing rationale:** #1 is the shared substrate (roadmap §5: "run first; everything touches it"). #2's full value needs #1's canonical Tick; #9 is the only other money-path item and is fully independent — do it early. #3/#10/#11 absorb idle capacity. Frontend items are gated only by per-file write serialization (App.svelte: 4→8; ChainGrid: 2→5→7).
