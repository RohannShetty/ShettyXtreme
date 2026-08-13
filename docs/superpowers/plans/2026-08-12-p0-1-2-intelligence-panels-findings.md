# P0-1.2 Findings — Scanner, Hints, Analytics, IV Rank, PCR, Max Pain All Empty (v0.14.0)

**Date:** 2026-08-12
**Scope:** Root-cause analysis of dead intelligence panels (everything beyond raw LTP).
**Method:** Full trace of EventBus wiring, FastAPI lifespan, options module usage, and frontend data sources. Every claim below is backed by a file:line.

---

## 0. Executive summary

The panels are not one problem — they are four distinct failure classes sharing one upstream dependency:

| Metric | Root-cause class | Code state |
|---|---|---|
| Regime / Signal (base) | Wiring OK, data-dependent | Works *if* ticks flow (P0-1.1's sibling) |
| Scanner gaps | Data availability | Works *if* ticks carry `open`; detector wired |
| Scanner clusters / signal logs | **Wiring** | `SIGNAL_GENERATED` is never published anywhere |
| Hints | Data availability (+ field mismatch) | Code complete, request-driven; 503s without chain |
| Analytics (scorecard) | Data availability (by design) | DB-read; empty on fresh boot, not a bug |
| IV Rank | **Wiring (orphaned module)** | `IVRankCalculator` complete but never instantiated/fed |
| PCR | Data availability + orphaned tracker | 3 paths; all die with an empty chain (P0-1.1) |
| Max Pain | **Computation — does not exist on backend** | Only a frontend function; no backend implementation |

**Critical upstream:** PCR, Max Pain, the strip IV level, and Hints all read the NIFTY option chain from Fyers `/data/options-chain-v3` (`integration/fyers/data_adapter.py:425`). When that chain is empty/503 (P0-1.1 — Data-API entitlement, Fyers 403/-373), these four die simultaneously. **P0-1.2 cannot be fully closed until P0-1.1 is.**

---

## 1. EventBus wiring — what actually exists

**Projections live in `terminal/projections.py` — NOT `intelligence/projections/`** (that directory does not exist).

| Projection | Class / lines | Subscribes to | In lifespan? |
|---|---|---|---|
| WatchlistProjection | `terminal/projections.py:23` | `MARKET_DATA_TICK` (`:100`) | ✅ `app.py:180,187` |
| PositionProjection | `terminal/projections.py:105` | `POSITION_CHANGED` (`:142`) | ✅ `app.py:181,188` |
| RiskProjection | `terminal/projections.py:147` | `RISK_DECISION` / `RISK_ALERT` (`:188-189`) | ✅ `app.py:182,189` |
| AlertProjection | `terminal/projections.py:197` | `RISK_ALERT` / `SYSTEM_STATUS` (`:232-233`) | ✅ `app.py:183,190` |
| IntelligenceProjection | `terminal/projections.py:238` | `REGIME_CHANGED` / `SIGNAL_V2` / `SIGNAL_GENERATED` (`:310-312`) | ✅ `app.py:184,191` |
| HealthProjection | `terminal/projections.py:349` | (configured refs, `:360-379`) | ✅ `app.py:185,192` + `:437-444` |
| **ScannerProjection** | ❌ **does not exist** | — | — |
| **AnalyticsProjection** | ❌ **does not exist** | — | — |

Key facts:

- **IntelligenceProjection is NOT subscribed to `MARKET_DATA_TICK`** — and it must not be. It is a consumer of *computed* events. The tick→feature→regime/signal chain is:
  `MARKET_DATA_TICK → FeatureEngine (intelligence/pipeline.py:68) → FEATURES_COMPUTED → RegimeBusBridge (regime/bus_bridge.py:25) → REGIME_CHANGED` and `→ SignalEngine (pipeline.py:99-123) → SIGNAL_V2 → IntelligenceProjection`. **This chain is fully wired in the lifespan** (`app.py:204-227`) and is real code (pipeline.py:89-133, regime/bus_bridge.py:32-56).
- **Scanner is not projection-based.** It uses detectors in `terminal/api/scanner_data.py` — `GapDetector` (`:18`, subscribes `MARKET_DATA_TICK` `:74`), `LogCollector` (`:77`, subscribes `SIGNAL_GENERATED`/`ORDER_*`/`RISK_ALERT`/`SYSTEM_STATUS` `:124-130`), `ClusterDetector` (`:133`, subscribes `SIGNAL_GENERATED` `:167`). All three are subscribed at `app.py:195-201`.
- **Analytics is not EventBus-based at all.** `terminal/api/analytics_router.py` is a DB-read scorecard (sessions / research decisions / learning calibration / trade ledger), opened per-request and degrading to `available:false`. There is nothing to wire.

---

## 2. ProjectionDataSource (research tool injection)

- Defined: `terminal/api/research_source.py:77`. Injected: `app.py:246` `set_data_source(ProjectionDataSource(app.state))`.
- It reads `app.state` members: `watchlist_projection` (`:84`), `intelligence_projection` (`:105`), `alert_projection` (`:122`), **`iv_rank_calculator` (`:145`)**, **`oi_tracker` (`:163`)**, **`options_chain` (`:184`)**.
- Wiring status of those `app.state` attributes:

| Attribute | Set anywhere? | Where |
|---|---|---|
| `watchlist_projection` | ✅ | `app.py:238` |
| `position_projection` | ✅ | `app.py:239` |
| `risk_projection` | ✅ | `app.py:240` |
| `alert_projection` | ✅ | `app.py:241` |
| `intelligence_projection` | ✅ | `app.py:242` |
| `health_projection` | ✅ | `app.py:243` |
| **`iv_rank_calculator`** | ❌ **never** | grep of `src/` → only `research_source.py:145` (getattr) + `options/__init__.py:8` (export) + frontend comment |
| **`oi_tracker`** | ❌ **never** | grep → only `research_source.py:163` (getattr) + `options/__init__.py:10` (export) |
| **`options_chain`** | ✅ (conditional) | `prime_options_chain` `intelligence_router.py:229` (called `terminal_init.py:278`) and `GET /api/intelligence/options` `intelligence_router.py:363` |

**Conclusion:** live regime/alerts ARE injected into research tools (regime_summary, scanner_summary, chain_summary work off live state). The `options_summary` tool's IV-rank and OI-tracker branches are **dead code paths** — the calculators are never instantiated, so only the chain-derived branch (`research_source.py:184-195`) can ever fire.

---

## 3. Options module wiring

All files exist with complete (non-stubbed) implementations:

| Module | Status | Evidence |
|---|---|---|
| `options/greeks.py` — `GreeksCalculator` | ✅ **Wired** | Used by `intelligence_router.py:16` import, `:245` `GreeksCalculator(use_quantlib=False)`, `:259` `calculate_all` |
| `options/iv_rank.py` — `IVRankCalculator` | ⚠️ **Orphaned** | Full implementation (`:51-188`) but **zero instantiation** in `src/` (grep: only `options/__init__.py:8` export + `research_source.py:145` getattr) |
| `options/oi_tracker.py` — `OITracker` | ⚠️ **Orphaned** | Full implementation (`:46-355`) but **zero instantiation** in `src/` (grep: only `__init__.py:10` export + `research_source.py:163` getattr) |
| `options/quantlib_pricer.py` | ⚠️ Optional import | `options_intel.py:12-16` tries import; greeks path explicitly `use_quantlib=False` |
| `options/strategy_analyzer.py` | ✅ **Wired** | `strategy_hints.py:16` import, `:101` `StrategyAnalyzer.display_name` |
| `intelligence/hints/strategy_hints.py` — `StrategyHints` | ✅ **Wired** | `intelligence_router.py:15` import, `:393` instantiated by `GET /api/intelligence/strategy-hint` |
| `intelligence/scanners/gap_scanner.py`, `breakout_scanner.py` | ⚠️ **Orphaned** | Complete classes, exported `scanners/__init__.py:3-4`, but never instantiated — the terminal uses its own `GapDetector`/`ClusterDetector` |

**The orphaned-module pattern is the single biggest "code exists but isn't called" finding:** `IVRankCalculator` and `OITracker` are production-quality (ring-buffer IV history, per-symbol PCR, OI-change alerts) but nothing constructs them or feeds them data.

---

## 4. PCR — three paths, all chain-dependent

1. **`OITracker.get_pcr`** (`options/oi_tracker.py:176-201`): aggregates put/call OI across **all strikes of all expiries** (or one expiry when given). Complete. **Orphaned** — never instantiated, never fed via `update_from_chain` (`:84`) or the `MARKET_DATA_BAR` handler (`:320-355`).
2. **`render_options_posture`** (`research_source.py:13-74`): aggregates the cached chain for `app.state.options_chain["NIFTY"]` — the primed chain is **nearest expiry only** (`prime_options_chain` fetches with `expiry=None` → Fyers nearest, `intelligence_router.py:216`). Returns `None` on empty chain → research tool renders `[UNSOURCED]`.
3. **Frontend `computePcr`** (`TickerStrip.svelte:138-149`): pure function over the enriched `OptionsChainItem` list from `GET /api/intelligence/options` (`TickerStrip.svelte:119`).

All three die when the chain is empty (P0-1.1) or the endpoint 503s (no adapter / Data-API entitlement, `intelligence_router.py:356-359`). No algorithm is stubbed anywhere.

---

## 5. Max Pain — **does not exist on the backend**

- Grep for `max_pain|maxpain|MaxPain|MAX_PAIN` across `src/` → **3 hits, all frontend**:
  - `terminal/web/src/components/TickerStrip.svelte:97` (`$derived(computeMaxPain(contracts))`)
  - `TickerStrip.svelte:204-250` — the actual algorithm (correct O(n) prefix/suffix sums; pain(K) = Σ(s−K)·ce[s] + Σ(K−s)·pe[s])
  - `App.svelte:198` — comment referencing the strip
- **No backend module, no API endpoint, no projection, no options-module function computes max pain.** It is pure client-side.
- It requires `strike` + `oi` + CE/PE pairs from the enriched chain → dies with an empty chain. The frontend strips zero-OI strikes (`:210-211`), so it also renders `—` if the chain has no OI.

---

## 6. IV Rank — calculator is in-memory and unfed (no DB history)

- The task premise ("52-week IV history from time-series DB") is **not how this codebase works**:
  - `IVRankCalculator` (`options/iv_rank.py:51`) stores history in **in-memory deques** (`_historical_iv`, `:72-73`, maxlen 5000) — no persistence, no time-series DB.
  - `record_iv` / `record_iv_batch` (`:75-102`) are **never called** anywhere (grep: zero callers in `src/`).
  - `data/` ingestion writes to `TimeSeriesStore` only via `BarBuilder` (`terminal_init.py:189-191`) for OHLC bars — **nothing writes IV** to any store.
- Result: `symbols` is empty → `compute_iv_rank_percent` returns `None` (`iv_rank.py:120-122`) → the `options_summary` tool branch never fires → research says `[UNSOURCED]`.
- Frontend: the strip's "IV RANK" card **is not IV rank** — it renders mean chain IV level on a 0–40 gauge and says so explicitly (`TickerStrip.svelte:72-77`: "True IV *rank* (0–100, history-based) lives in the backend IVRankCalculator which is **not yet app-wired**"). It also dies with an empty chain.

---

## 7. Per-metric diagnosis + proposed fixes

### 7.1 Scanner — gaps
- **Category:** Data availability (code wired, depends on tick shape).
- Files: `terminal/api/scanner_data.py:18-74` (GapDetector), wired `app.py:195-201`; router `scanner_router.py:31-44`; Fyers tick `open` mapping `integration/fyers/data_adapter.py:198` (`open_price` → `open`).
- **Fix:** Ensure watchlist indices stream ticks with `open_price` (Fyers HSM does). GapDetector compares `open` vs *previous tick LTP* (`scanner_data.py:46-71`), so it only fires on bar-open vs last-close — verify semantics are what the panel promises (overnight gap needs a persisted prev-day close, which this code does **not** have; `_prev_close` is only seeded from this run's ticks, `:69-71`). Consider seeding `_prev_close` from `/data/quotes` at startup for true overnight-gap detection.

### 7.2 Scanner — clusters + signal logs
- **Category: Wiring (a topic that is never published).**
- Files: `intelligence/signals/simple_generator.py:116` is the only publisher of `SIGNAL_GENERATED` (topic declared `core/event_bus/event_bus.py:27`); consumers `scanner_data.py:124,167` + `projections.py:312`. `SimpleSignalGenerator` is exported (`signals/__init__.py:3`) but **never instantiated** — the live pipeline publishes `SIGNAL_V2` (`pipeline.py:109-123`), which `LogCollector`/`ClusterDetector` do not listen to.
- **Fix (two options):** (a) publish `SIGNAL_GENERATED` alongside `SIGNAL_V2` from `intelligence/pipeline.py:_on_features` (add `symbol` to the payload — ClusterDetector reads `d.get("symbol")`, `scanner_data.py:142`, and `SIGNAL_V2`'s dict has no symbol key); or (b) re-point `LogCollector`/`ClusterDetector` subscriptions at `SIGNAL_V2` in the lifespan.

### 7.3 Hints
- **Category: Data availability + a field-name mismatch (not stubbed).**
- Files: endpoint `intelligence_router.py:370-400`; generator `intelligence/hints/strategy_hints.py:42-196`; EV math `intelligence/options/options_intel.py:140-257` (complete).
- Failure modes: (a) 503 when no data adapter / entitlement missing (`intelligence_router.py:378-381`); (b) `stand_aside` when signal NEUTRAL or conviction < 0.25 or participation < 0.5 (`strategy_hints.py:70-96`); (c) `_select_strike` reads the **`premium`** key from raw chain rows (`strategy_hints.py:159`), but Fyers v3 rows expose `ltp`/`last_price` — premium defaults to 0.0, making EV ≈ −(slippage+brokerage) → "no strike offers positive EV" hint with strategy name (`:108-118`). Chain rows are raw (never enriched) when passed here (`intelligence_router.py:382-393`).
- **Fix:** map Fyers `ltp` → premium in `_select_strike` (or feed it the enriched contracts); verify signal gates are met by checking what voters actually emit (see §7.6 — only `micro_voter` can currently fire).

### 7.4 Analytics (scorecard)
- **Category: Data availability — by design, not a defect.**
- Files: `terminal/api/analytics_router.py:86-267`; `AnalyticsPanel.svelte:38`.
- Every metric degrades to `available:false` with a guidance note when its DB is empty (`:101-122`, `:150-194`, `:237-258`). On a fresh boot all DBs are empty → the whole panel reads zero/empty. Sessions and fills accumulate automatically; decisions/outcomes/calibration need human or research-scheduler activity.
- **Fix:** none required for wiring. Optionally surface the `available`/`note` fields more prominently so "empty = nothing recorded yet" reads as a state, not a failure. Confirm `sessions.db` is being written (it is — `SessionLog.start` at `app.py:305`).

### 7.5 PCR
- **Category: Data availability (chained on P0-1.1) + orphaned tracker.**
- Files: chain fetch `intelligence_router.py:164-194` / `integration/fyers/data_adapter.py:425-444`; posture `research_source.py:13-74`; frontend `TickerStrip.svelte:138-149`.
- **Fix:** (a) close P0-1.1 (chain empty / 403 entitlement); (b) optionally wire `OITracker` on `app.state.oi_tracker` in the lifespan and feed it from each `GET /api/intelligence/options` response (`intelligence_router.py:363-366` is the natural feed point), which restores the tracker branch of `research_source.options_summary` (`:163-183`) and gives change-based OI alerts. Also consider a dedicated `GET /api/intelligence/options-summary` endpoint instead of the current side-channel cache (TickerStrip.svelte:18-20 explicitly notes "a dedicated options-summary endpoint does not exist yet").

### 7.6 IV Rank
- **Category: Wiring — code exists, is never instantiated, never fed.**
- Files: `options/iv_rank.py:51-188`; desired consumer `research_source.py:145-162`; frontend `TickerStrip.svelte:72-77`.
- **Fix:** (a) in the lifespan (`app.py`), construct `IVRankCalculator` and `OITracker`, store on `app.state`, and feed them on every successful chain fetch (both the prime at `terminal_init.py:278` and the endpoint at `intelligence_router.py:363-366`) — `record_iv` for each row's `iv`, `update_from_chain` for OI; (b) expose a real IV-rank endpoint (e.g. `/api/intelligence/options-summary`) and point the strip's IV gauge at it — or keep the gauge but re-label it (it currently renders a level, not a rank); (c) if true 52-week rank is wanted, persist IV snapshots to `TimeSeriesStore` (which already exists, `core/storage/time_series_store.py`, used by BarBuilder) and seed the calculator from it at boot, since the current in-memory deque resets every process.

### 7.7 Max Pain
- **Category: Computation — backend implementation does not exist at all.**
- Files: frontend-only `TickerStrip.svelte:204-250`; no backend counterpart.
- **Fix:** port `computeMaxPain` to Python (e.g. `options/` new module or `intelligence/options/options_intel.py`), expose it on a `/api/intelligence/options-summary`-style endpoint, and have the frontend consume it. It is O(n) over the enriched chain; the frontend implementation is the reference algorithm. This also removes the need to ship the algorithm in the SPA and makes it available to research tools.

---

## 8. Cross-cutting action list (priority order)

1. **P0-1.1 first:** option chain empty/403 (`data_adapter.py:425` → `intelligence_router.py:164`) kills PCR, Max Pain, IV level, Hints simultaneously. Verify Data-API entitlement is active; surface, don't paper over.
2. **Wire the orphaned calculators:** instantiate `IVRankCalculator` + `OITracker` in the lifespan (`app.py` ~line 244), store on `app.state`, feed from the chain prime + endpoint.
3. **Publish `SIGNAL_GENERATED` (with `symbol`) from the pipeline** — unblocks LogCollector signal logs + ClusterDetector + the `SIGNAL_GENERATED` branch of IntelligenceProjection (`projections.py:312`).
4. **Implement backend max pain** (port from `TickerStrip.svelte:204-250`) + a dedicated options-summary endpoint feeding strip + research `options_posture` tool.
5. **Fix the hints premium mapping** (`strategy_hints.py:159` — Fyers uses `ltp`, not `premium`).
6. **Optional:** seed GapDetector `_prev_close` from `/data/quotes` at startup for true overnight gaps; re-label the strip's IV gauge honestly.

---

## 9. Evidence trail (quick links)

- Lifespan wiring: `terminal/api/app.py:149-502`
- Projections: `terminal/projections.py` (Intelligence at `:238-313`)
- DataSource: `terminal/api/research_source.py` (options_summary `:134-196`)
- Chain prime: `terminal/api/intelligence_router.py:197-233`; endpoint `:345-367`; hint `:370-400`
- Adapter chain: `integration/fyers/data_adapter.py:425-444`
- Pipeline: `intelligence/pipeline.py:35-133`; regime bridge `intelligence/regime/bus_bridge.py:12-62`
- Orphaned: `options/iv_rank.py:51`, `options/oi_tracker.py:46`, `intelligence/scanners/*`, `intelligence/signals/simple_generator.py:116`
- Frontend consumers: `TickerStrip.svelte` (regime/IV/PCR/max pain), `ScannerPanel.svelte:46-48`, `HintsPanel.svelte:38`, `AnalyticsPanel.svelte:38`, `ChainGrid.svelte:216,248`, `LogDrawer.svelte:62`
