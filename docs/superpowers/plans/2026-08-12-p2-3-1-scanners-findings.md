# P2-3.1 Findings — Opportunity Scanners (11 Scanner Types)

**Date:** 2026-08-12
**Scope:** Full scanner architecture trace — `intelligence/scanners/`, `terminal/api/scanner_data.py` + `scanner_router.py`, EventBus topics, option analytics calculators (`options/`), data sources (DuckDB `TimeSeriesStore`, Fyers chain REST), frontend `ScannerPanel.svelte`.
**Version under investigation:** v0.14.0 (CHANGELOG head; suite 1244 passed per P1 findings docs).
**Mission spec:** 11 scanner types (Gamma Spike, IV Crush Candidate, IV Expansion, PCR Extremes, Max Pain Drift, Theta Harvest, Calendar Spread, Vertical Skew, Gap Fill, Volume Anomaly, OI Buildup). **No P2-3.1 spec doc exists in `docs/`** — the spec is the mission text; the only prior scanner reference is `docs/architecture/v2/sections/08-feature-map.md` (gap + breakout scanners only) and the S5 UI findings (`2026-08-05-s5-scanner-intelligence-findings.md`, UI-only).

---

## Executive summary

The scanner is **not one stub — it is two disconnected stacks, neither of which does the job:**

1. **`intelligence/scanners/` (GapScanner, PriceBreakoutScanner) — dead code.** Tested (2 test files), but **never instantiated anywhere in `src/`**. They subscribe to `MARKET_DATA_BAR`, compute results into in-memory `_last_results`, and **never emit events**. No alert, no topic, no REST surface.
2. **`terminal/api/scanner_data.py` (GapDetector, LogCollector, ClusterDetector) — the live but primitive stack.** Wired in `app.py` lifespan, polled via `/api/scanner/*` REST. Only does overnight-gap detection, signal-log collection, and naive 5-minute multi-signal clustering. **No options awareness whatsoever.**

**Of the 11 required scanner types: 2 partially exist (Gap Fill, OI Buildup), 9 do not exist.** The `SCANNER_GAP` / `SCANNER_CLUSTER` / `SCANNER_LOG` EventBus topics are defined but **never published by anything** (zero publishers in `src/`). There is **no VIX feed and no earnings calendar anywhere** in the codebase — two scanners (IV Expansion, IV Crush) have no data source today. Options data reaches the app only via REST polling of the Fyers chain; it never rides the EventBus. The DuckDB `TimeSeriesStore` is write-only (only `BarBuilder` writes to it; no code reads it back).

**The good news:** the computational primitives for 8 of 11 scanners already exist (`options/greeks.py` Black-76, `options/iv_rank.py`, `options/oi_tracker.py`, `options/max_pain.py`, `intelligence/options/options_intel.py`). The work is wiring + cadence + 2 missing data feeds + event emission — not greenfield math.

---

## 1. Current scanner architecture (what exists)

### 1.1 Stack A — `intelligence/scanners/` (spec layer, unwired)

`src/shettyxtreme/intelligence/scanners/__init__.py` exports two classes:

| File | Class | Topic | What it does |
|---|---|---|---|
| `gap_scanner.py` | `GapScanner` | subscribes `MARKET_DATA_BAR` | Per-symbol in-memory bar history (lookback 10); overnight + intraday gap detection; categorizes `common` (>1.0%) / `breakaway` (>1.5%) / `exhaustion` (gap against trend) |
| `breakout_scanner.py` | `PriceBreakoutScanner` | subscribes `MARKET_DATA_BAR` | Lookback-window (default 20) high/low breakout with volume confirmation; 0–100 confidence score |

**Shared pattern (the template to reuse):** `__init__(event_bus, **params)` → `async start()/stop()` subscribe/unsubscribe → `async _on_bar(event)` maintains per-symbol history → `_scan_symbol()` returns `list[dict]` → `scan_bars()` standalone entry for tests → `last_results` property → `tracked_symbols` property.

**Key defect:** results go only into `self._last_results` (a plain in-memory list, overwritten per symbol scan). **No `publish()` call anywhere** — no EventBus emission, so no projection/REST/WS can ever see them. And nothing in `src/` constructs these classes (only `tests/intelligence/test_gap_scanner.py`, `test_breakout_scanner.py`).

### 1.2 Stack B — `terminal/api/scanner_data.py` (the live stack)

Wired in `app.py` lifespan (`app.py:196-203`): instances created, `.subscribe(bus)` called, passed to `init_scanner_data()` for the router.

| Class | Subscribes | Stores | Cap |
|---|---|---|---|
| `GapDetector` | `MARKET_DATA_TICK` | prev-close per symbol; gap findings (`gap_type` common/breakaway/exhaustion, `gap_percent`, direction) | 100 gaps |
| `LogCollector` | `SIGNAL_GENERATED`, `ORDER_PLACED/FILLED/REJECTED/UPDATED`, `RISK_ALERT`, `SYSTEM_STATUS` | structured log entries | 500 |
| `ClusterDetector` | `SIGNAL_GENERATED` | ≥2 signals on same symbol within 5 min → `cluster` (strength = count/5) | 50 |

REST surface (`scanner_router.py`, prefix `/api/scanner`):
- `GET /api/scanner/gaps` → `list[GapResponse]` (read from `GapDetector.gaps`)
- `GET /api/scanner/clusters` → `list[ClusterResponse]` (read from `ClusterDetector.clusters`)
- `GET /api/scanner/alerts` → `list[AlertResponse]` — **NOT scanner findings**; reads `app.state.alert_projection` (RISK_ALERT/staleness/system alerts)
- `GET /api/scanner/logs` → `list[LogResponse]` (from `LogCollector.logs`)

**Note the naming trap:** `/api/scanner/alerts` returns risk/staleness alerts, not scanner opportunity alerts. The 11-type scanner output has no wire surface at all.

### 1.3 Frontend — `ScannerPanel.svelte`

Exists (432 lines), fully polished (Phase 3 S5 + Phase 7 Wave 1 badge work):
- 3 columns: **Gaps / Clusters / Alerts**, each a card with eyebrow label + count stat.
- Fetches `/api/scanner/gaps`, `/api/scanner/clusters`, `/api/scanner/alerts` **on mount only** (manual refresh button; no polling interval).
- STALE chip (>60s since `fetchedAt`), roving-tabindex arrow-key navigation, conviction badges mapped from alert `severity`.
- Types are hardcoded to the 3 legacy collections — **no per-scanner-type taxonomy**.

---

## 2. What's missing — the 11 scanners vs existing primitives

| # | Scanner (spec) | Exists as scanner? | Primitives available today | Data gaps |
|---|---|---|---|---|
| 1 | **Gamma Spike** (gamma > 2× avg at strike) | ❌ No | `GreeksCalculator` (`options/greeks.py:121`) computes gamma per contract; chain enrichment (`intelligence_router._enrich_chain`) already computes gamma per row | Per-strike gamma history (avg) must be accumulated in-memory; chain fetch cadence |
| 2 | **IV Crush Candidate** (IV Rank > 80% + earnings ≤48h) | ❌ No | `IVRankCalculator` (`options/iv_rank.py`) gives 0–100 rank | **No earnings calendar anywhere** (grep `earnings` in `src/` = 0). IV history is in-memory only |
| 3 | **IV Expansion** (IV Rank < 20% + VIX up 10% 1D) | ❌ No | `IVRankCalculator` + `compute_iv_rank` (0–1) | **No VIX feed** (grep VIX = 0). INDIAVIX not in `INDEX_SYMBOLS` (`integration/fyers/_util.py:15`) — resolvability via instrument master unverified |
| 4 | **PCR Extremes** (PCR < 0.5 or > 1.5) | ❌ No (voter exists) | `OITracker.get_pcr()` (`options/oi_tracker.py:176`); `pcr_signal()` (`intelligence/options/options_intel.py:60`); `options_flow_voter` uses 0.7/1.3 (different thresholds) | PCR only populated when a chain has been fetched (REST) |
| 5 | **Max Pain Drift** (spot > 2% from max pain, <3 DTE) | ❌ No | `compute_max_pain()` (`options/max_pain.py:11`) — already exposed via `GET /api/intelligence/options-summary` | Needs spot + max pain + DTE per symbol; chain cadence |
| 6 | **Theta Harvest** (theta/vega > 3, DTE < 10) | ❌ No | `GreeksCalculator.calculate_all` returns theta (per day, `greeks.py:135`) + vega (per 1%, `:127`) | Chain cadence; theta/vega units consistent |
| 7 | **Calendar Spread** (same strike, month vs week IV diff > 15%) | ❌ No | `data_adapter.get_option_chain(underlying, expiry)` supports **arbitrary expiry** — can fetch week + month chains | Needs expiry resolution (weekly vs monthly — `resolve_default_expiry` / `classify_expiry` exist in `integration/fyers/symbols.py`) + two-chain alignment by strike |
| 8 | **Vertical Skew** (25Δ IV vs 75Δ IV diff > 5%) | ❌ No | Chain carries per-strike IV + computed delta (`_enrich_chain`); delta→strike interpolation needed | Need to solve for strike at target delta (or approximate by moneyness); chain cadence |
| 9 | **Gap Fill** (opening gap > 1%, no catalyst) | ⚠️ Partial | `GapDetector` (tick, >0.5%) + `GapScanner` (bar, >1.0%) both detect gaps | "No catalyst" filter (news) has no data source; threshold spec 1% matches `GapScanner` not `GapDetector`; neither emits events |
| 10 | **Volume Anomaly** (volume > 3× 20-day avg, price unchanged) | ❌ No | `Bar` carries volume; ticks carry volume; `TimeSeriesStore.bars` persisted | 20-day avg needs history — in-memory rolling window or DuckDB read (currently unread) |
| 11 | **OI Buildup** (OI change > 20%, price up/down) | ⚠️ Partial | `OITracker` (`options/oi_tracker.py`) — per-contract OI change alerts at 25/50/100% thresholds; `record_symbol_oi`/`get_symbol_oi` for bar-level OI | Threshold 25% ≠ spec 20%; alerts stored in-memory, **never published or surfaced**; requires chain feed for per-contract path |

**Tally: 9 missing, 2 partial. Zero of the 11 are wired end-to-end (compute → event → projection → REST → UI).**

---

## 3. EventBus wiring status

| Aspect | Status |
|---|---|
| `SCANNER_GAP` / `SCANNER_CLUSTER` / `SCANNER_LOG` topics | **Defined** (`core/event_bus/event_bus.py:43-45`) — **zero publishers** in `src/` |
| Scanners subscribed to `MARKET_DATA_TICK`? | Only `GapDetector` (terminal stack). `intelligence/scanners/` subscribes to `MARKET_DATA_BAR` |
| Scanners subscribed to `MARKET_DATA_BAR`? | `GapScanner`, `PriceBreakoutScanner` (uninstantiated), `OITracker._on_market_data` (`oi_tracker.py:320` — bar-level OI) |
| Scanners emit alert events? | **No.** No scanner publishes to any topic. `OITracker` accumulates `OIAlert` objects in memory only |
| Option-chain on the bus? | **No.** Chain is REST-only (`data_adapter.get_option_chain`); no `OPTION_CHAIN` topic exists |
| What *does* flow on the bus | `MARKET_DATA_TICK` (Fyers bridge → `terminal_init._publish_market_tick`), `MARKET_DATA_BAR` (BarBuilder), `SIGNAL_GENERATED`/`SIGNAL_V2` (intelligence pipeline), `RISK_ALERT`, `REGIME_CHANGED`, order topics |

**Core gap:** there is no scanner-findings event type and no scanner emission path. The architecture doc (`ARCHITECTURE_V2.md` §06) mandates `SCANNER_GAP / SCANNER_CLUSTER / SCANNER_LOG: scanners → terminal` — this contract is unimplemented.

---

## 4. Data source architecture (time-series DB vs recomputation)

**Current state: recompute-from-live-events, plus a write-only DuckDB.**

- **DuckDB `TimeSeriesStore`** (`core/storage/time_series_store.py`, `data/shetty_ts.db`): `bars` and `ticks` tables. **Only `BarBuilder` writes** (`bar_builder.py:170` persists every completed bar). **No production code reads it** (`get_bars` exists but is unused in `src/`). Storage manager exposes it via `StorageManager.ts` (`core/storage/storage_manager.py:9`).
- **Everything else is in-memory rolling windows**: `GapScanner`/`PriceBreakoutScanner` keep per-symbol bar deques; `GapDetector` keeps prev-close; `IVRankCalculator` keeps per-symbol IV deques (`max_history=5000`, **lost on restart**); `OITracker` keeps OI dicts (lost on restart); `LogCollector`/`ClusterDetector` keep capped lists.
- **Option chain**: REST-only, Fyers `/data/options-chain-v3?greeks=1` (`data_adapter.get_option_chain`, `data_adapter.py:442`). Fetched (a) once at terminal init for NIFTY only (`prime_options_chain`, `intelligence_router.py:237`), and (b) per-hit of `GET /api/intelligence/options`. Chain rows feed `IVRankCalculator.record_iv()` + `OITracker.update_from_chain()` (`_feed_options_calculators`, `intelligence_router.py:205`).
- **Missing feeds**: no VIX quotes (IV Expansion), no earnings calendar (IV Crush), no news/catalyst (Gap Fill "no catalyst" clause).

**Implication for the fix:** chain-dependent scanners (1, 2, 4, 5, 6, 7, 8) cannot be pure EventBus consumers — they need a periodic chain-refresh task (the `_margin_poll_loop` pattern in `app.py:172` is the house precedent). Bar/tick-dependent scanners (9, 10, 11) can be pure subscribers. IV history should graduate from in-memory deques to the DuckDB `bars`/a new `iv_history` table if rank stability across restarts matters.

---

## 5. Proposed fix approach (algorithm-level, not code)

### 5.1 Shape: one registry + one projection, two cadence tiers

**Scanner classes** live in `intelligence/scanners/` following the existing pattern, extended with **emission**:
- Each scanner: `__init__(event_bus, **params)` → `start()/stop()` → subscribe to its input topic(s) → on finding, `publish_nowait(Event(topic=SCANNER_FINDING, data={scanner_type, symbol, detail…}))`.
- **New unified topic** `SCANNER_FINDING` (or reuse/rename the three existing `SCANNER_*` topics) — one topic keeps the projection and REST surface uniform; a per-type emitter id in the payload replaces the three-topic split.
- **Registry**: `intelligence/scanners/` exports a list/registry of `(type, class)` (mirror the `@voter` decorator registry in `intelligence/signals/signal_engine.py` — house plugin pattern). Wiring instantiates all registered scanners with per-type config.

**Cadence tiers:**
- **Tier A — event-driven** (subscribe `MARKET_DATA_BAR`/`MARKET_DATA_TICK`): **Gap Fill** (9), **Volume Anomaly** (10), **OI Buildup** bar-level path (11), **PCR Extremes** (4) if a chain source is added.
- **Tier B — snapshot-driven** (REST-polled chain, like `_margin_poll_loop`): **Gamma Spike** (1), **IV Crush** (2), **IV Expansion** (3), **Max Pain Drift** (5), **Theta Harvest** (6), **Calendar Spread** (7), **Vertical Skew** (8), plus per-contract **OI Buildup** (11). A single `OptionsChainPoller` task (one symbol per run, token-bucket aware — `client.py` throttles ~8 req/s) feeds a shared chain snapshot cache that the Tier-B scanners consume; the poller also seeds `IVRankCalculator` + `OITracker` (replacing the ad-hoc `_feed_options_calculators` calls).

**Projection:** a new `ScannerProjection` (terminal layer) subscribes to the scanner topic, stores capped per-type finding lists (like `AlertProjection`), replacing/absorbing `GapDetector`/`ClusterDetector`. The router reads the projection; `/api/scanner/alerts` stays as-is (risk alerts) and a new `/api/scanner/findings?type=…` (or `/api/scanner/{type}`) serves opportunities.

### 5.2 Per-scanner algorithm notes

1. **Gamma Spike** — per chain refresh, per strike: mean gamma across history (in-memory ring per symbol+strike), flag strike where current gamma > 2× mean. Needs 2+ observations → only fires after the poller has run a few cycles.
2. **IV Crush Candidate** — `IVRankCalculator.compute_iv_rank_percent` > 80 **and** DTE ≤ 2 (earnings proxy when calendar absent — earnings ≤48h ≈ expiry ≤2 sessions for index options; note as a **fallback**, flag as limitation). Real earnings calendar = new data source (see §5.4).
3. **IV Expansion** — `IVRankCalculator` < 20 **and** VIX 1D return ≥ +10%. VIX via `data_adapter.get_quotes(["INDIAVIX"])` 1D apart (needs instrument-master resolvability check; add INDIAVIX to `INDEX_SYMBOLS` if resolvable).
4. **PCR Extremes** — `OITracker.get_pcr()` outside [0.5, 1.5]; thresholds configurable (spec 0.5/1.5 vs voter's 0.7/1.3 — keep separate, they serve different purposes).
5. **Max Pain Drift** — per chain: `compute_max_pain(contracts)`; DTE from resolved expiry (`business_days_to_expiry` via `QuantLibPricer`, or calendar days); flag when `abs(spot/max_pain - 1) > 2%` and DTE < 3.
6. **Theta Harvest** — per ATM contract: `theta/vega` ratio from `GreeksCalculator` (theta per day / vega per 1%); flag ratio > 3 and DTE < 10. Note theta is negative — use absolute values.
7. **Calendar Spread** — fetch week + month chains for same underlying (`get_option_chain(underlying, weekly)` and `(underlying, monthly)` via `resolve_default_expiry`/`classify_expiry`); for each common strike, flag `|IV_week − IV_month|/IV_week > 15%`.
8. **Vertical Skew** — within one chain, estimate strikes at 25Δ / 75Δ (interpolate delta-vs-strike from the computed greeks; or approximate by moneyness — delta from `_enrich_chain` is already per-row); flag when `|IV(25Δ) − IV(75Δ)| > 5%`.
9. **Gap Fill** — adopt `GapScanner` bar logic with spec threshold (>1%); add optional "no catalyst" filter that is **a no-op until a news source exists** (documented gap). Emit findings instead of `_last_results`.
10. **Volume Anomaly** — per symbol, 20-day avg volume from `TimeSeriesStore.get_bars()` (first real read of DuckDB) or an in-memory daily ring; flag current-bar volume > 3× avg **and** |Δ close| < small epsilon (e.g. 0.5%).
11. **OI Buildup** — `OITracker.update_from_chain` path with threshold 20% (config param); emit findings from returned `OIAlert`s; bar-level path via `record_symbol_oi` for symbols without chain feeds.

### 5.3 Wiring & surface

- `app.py` lifespan: after the intelligence pipeline, instantiate + start all scanners and the chain poller (guarded — degrade to "scanner idle" when no adapter, matching the pipeline's `degraded` pattern).
- REST: extend `scanner_router.py` with `GET /api/scanner/findings` (+ optional `?type=` filter) → `ScannerPanel` grows a per-type column grid. Existing gaps/clusters/alerts endpoints unchanged (back-compat with tests `test_scanner_data.py`, `test_integration.py:test_scanner_alerts_empty`).
- Research `scanner_alerts` tool (`research/tools.py:109`) and `scanner_summary()` (`research_source.py:121`) should read the new projection so the briefer surfaces 11-type findings, not just risk alerts.

### 5.4 Data sources to add (the two hard gaps)

| Need | Today | Options |
|---|---|---|
| **VIX** (IV Expansion) | none | Fyers quotes for `INDIAVIX` (verify in instrument master); fallback: use NIFTY ATM IV 1D change as VIX proxy (documented deviation) |
| **Earnings calendar** (IV Crush) | none | Fyers corporate-actions endpoint (unverified), manual `configs/earnings.yaml` seed, or DTE≤2 fallback with a `catalyst_known=false` flag on the finding |

### 5.5 Import-boundary note

AGENTS.md says `intelligence/` imports core only, but live code already imports `shettyxtreme.options.*` from `intelligence/hints/strategy_hints.py` (and `learning/`). Options calculators are effectively a shared library — Tier-B scanners may import them directly (consistent with hints), keeping the `options/` package broker-agnostic and pure (it already is — no I/O).

---

## 6. Reusable code inventory

| Piece | Location | Reuse for |
|---|---|---|
| `GreeksCalculator.calculate_all` (Black-76 δ/γ/θ/ν/ρ) | `options/greeks.py:73` | Gamma Spike, Theta Harvest, Calendar (IV), Vertical Skew |
| `IVRankCalculator` (0–100 rank/percentile, in-memory) | `options/iv_rank.py:51` | IV Crush, IV Expansion |
| `compute_iv_rank` / `compute_iv_percentile` (0–1) | `intelligence/options/options_intel.py:22,41` | same, canonical scale |
| `OITracker` (`update_from_chain`, `get_pcr`, `get_alerts`, `record_symbol_oi`) | `options/oi_tracker.py:46` | PCR Extremes, OI Buildup |
| `compute_max_pain` | `options/max_pain.py:11` | Max Pain Drift |
| `GapScanner` / `PriceBreakoutScanner` (+ their tests) | `intelligence/scanners/` | Gap Fill; the class-template + test-style for all 11 |
| `GapDetector` / `ClusterDetector` / `LogCollector` + router + models | `terminal/api/scanner_data.py`, `scanner_router.py`, `models.py` | live REST surface to extend; back-compat baseline |
| `BarBuilder` + `TimeSeriesStore` (bars persisted) | `data/pipeline/bar_builder.py`, `core/storage/time_series_store.py` | Volume Anomaly 20-day avg (first DuckDB read) |
| `data_adapter.get_option_chain(underlying, expiry)` + `prime_options_chain` | `integration/fyers/data_adapter.py:442`, `intelligence_router.py:237` | chain snapshot cache / poller for Tier-B scanners |
| `resolve_default_expiry` / `classify_expiry` | `integration/fyers/symbols.py` | Calendar Spread (week vs month) |
| `_margin_poll_loop` polling pattern | `terminal/api/app.py:172` | periodic chain-refresh task |
| `@voter` decorator registry | `intelligence/signals/signal_engine.py` | scanner type registry pattern |
| `AlertProjection` capped-store pattern | `terminal/projections.py:235` | `ScannerProjection` model |
| `_enrich_chain` (computes per-row greeks incl. delta/gamma/theta/vega) | `terminal/api/intelligence_router.py:278` | chain → greeks already done; scanners can consume enriched rows |

## 7. Test surface that must keep passing

- `tests/intelligence/test_gap_scanner.py`, `tests/intelligence/test_breakout_scanner.py` (148 + ~150 lines) — existing scanner unit tests; keep the `scan_bars()` API or migrate them.
- `tests/terminal/test_scanner_data.py` — GapDetector/LogCollector/ClusterDetector contracts.
- `tests/terminal/test_integration.py:117` `test_scanner_alerts_empty` — `/api/scanner/alerts` must stay empty-with-no-state.
- `tests/wave8/test_research_tools.py:77` — `scanner_alerts` tool returns `UNSOURCED` with no source.
- `tests/intelligence/test_intelligence.py` + `tests/wave9/test_lifespan_wiring.py` — pipeline wiring; new scanner startup must not break lifespan.
- Full suite gate: **1012–1244 passed / 0 failed** per AGENTS.md; `npm run check` 0 errors for frontend changes.

## 8. Open questions for the spec/plan phase

1. Earnings calendar — is a real calendar in scope (Fyers corporate actions / manual seed), or is the DTE≤2 proxy with a `catalyst_known=false` flag acceptable for P2-3.1?
2. India VIX — confirm `INDIAVIX` resolvability via instrument master; if not, ATM-IV proxy fallback?
3. Chain coverage — NIFTY-only (current `prime_options_chain` behavior) or per-watchlist-symbol chains? Watchlist has only 3 indices today.
4. Should `/api/scanner/alerts` keep returning risk alerts (back-compat) with findings on a new endpoint, or merge?
5. Scanner config — per-type thresholds from a YAML (`configs/scanners.yaml`) or constructor defaults only?
