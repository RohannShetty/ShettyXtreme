# Phase 5 Lane E — Intelligence/Knowledge Fixes (4 items)

**Date:** 2026-08-05
**Scope:** Phase 5 Lane E — medium-effort correctness/reliability fixes in intelligence and knowledge layers after Phase 4 quick wins.
**Status:** Complete — all 4 fixes implemented with regression tests. Full suite green: **1116 passed / 0 failed / 0 errors**.

---

## Deliverables

| Item | File | Change |
|---|---|---|
| F-INTEL-006 | `src/shettyxtreme/intelligence/features/feature_engine.py` | FeatureEngine now tracks `last_update` (epoch seconds of the last fresh tick); stale ticks no longer refresh it |
| F-INTEL-006 | `src/shettyxtreme/intelligence/signals/signal_engine.py` | New `max_age_seconds` (default 60s) + `Signal.stale` flag; `compute_signal` skips voters and returns a stale NEUTRAL signal when the feature snapshot is older than the cutoff |
| F-KNOW-004 | `src/shettyxtreme/options/oi_tracker.py` | `_on_market_data` now understands the real `MARKET_DATA_BAR` payload (`Bar` objects, not `{symbol, expiry, contracts}`); records symbol-level OI via new `record_symbol_oi`/`get_symbol_oi`; chain dicts still feed `update_from_chain` |
| F-INTEL-008 | `src/shettyxtreme/options/iv_rank.py` | 0-100 (percent) variant renamed for scale clarity: `IVRankResult.iv_rank` → `iv_rank_percent`, `IVRankCalculator.compute_iv_rank` → `compute_iv_rank_percent`; canonical 0-1 `intelligence.options.compute_iv_rank` unchanged |
| F-INTEL-008 | `src/shettyxtreme/terminal/api/research_source.py` | Caller updated to `compute_iv_rank_percent` / `iv_rank_percent` |
| F-KNOW-003 | `src/shettyxtreme/execution/position_manager.py` | `_is_eod` converts the IST `eod_exit_time` cutoff to UTC (`_IST_OFFSET_MINUTES = 5*60+30`) before comparing against the UTC `now` |

Collateral test updates:

- `tests/intelligence/test_intelligence.py::test_intelligence_layers` — feeds the tick through `FeatureEngine.process_tick` (the engine never subscribed to `MARKET_DATA_TICK`; the test previously relied on empty/stale features) so the F-INTEL-006 stale guard sees fresh data.
- `tests/wave2/test_signal_engine.py` — **4 new** `TestStaleSignalGuard` regressions (F-INTEL-006).
- `tests/wave2/test_feature_engine.py` — **2 new** `TestLastUpdateTracking` regressions (F-INTEL-006); the `test_register_and_get_indicator` bus double is now an `AsyncMock` so `process_tick` is awaitable.
- `tests/options/test_oi_tracker.py` — **5 new** `TestMarketDataEvents` regressions (F-KNOW-004).
- `tests/options/test_iv_rank.py` — renamed to the `_percent` API + **2 new** scale-consistency regressions (F-INTEL-008).
- `tests/wave5/test_position_manager.py` — **2 new** EOD timezone regressions (F-KNOW-003).

---

## 1. F-INTEL-006 — Stale data treated as fresh at the SignalEngine boundary

### 1.1 The bug

`SignalEngine.compute_signal` computed a fresh-looking `Signal` from whatever
was in `FeatureEngine.features` regardless of how old that snapshot was. The
FeatureEngine did drop *ticks* older than `STALE_THRESHOLD_SECONDS = 10` (they
were not folded into the feature state), but the engine never recorded *when*
the last good update happened — so a consumer sitting downstream (the signal
engine, potentially fed by bar-cadence data with longer lulls) could emit a
signal that *looked* current while its inputs were minutes old.

### 1.2 The fix

**FeatureEngine** (`feature_engine.py`):

- New `max_age_seconds` constructor param (defaults to `STALE_THRESHOLD_SECONDS`,
  so the existing 10s tick-level behavior is unchanged).
- New `last_update: float` — epoch seconds of the last *fresh* tick that
  updated `self.features`; `0.0` means "no fresh data ever".
- `process_tick` stamps `last_update` only on the non-stale path. Stale ticks
  neither refresh `last_update` nor mutate `self.features` (last good values
  are preserved, exactly as before).

**SignalEngine** (`signal_engine.py`):

- New `max_age_seconds: float = 60.0` constructor param.
- `Signal` gains `stale: bool = False` (defaulted field — no existing
  construction site changes).
- New `_data_stale()`: engines that do not expose `last_update` (test doubles)
  are treated as fresh; a real FeatureEngine with `last_update == 0.0` (no
  data yet) is stale; otherwise fresh iff `time.time() - last_update <= max_age_seconds`.
- `compute_signal` short-circuits on stale data: voters are never consulted,
  the result is `Signal(NEUTRAL, 0.0, [], stale=True)`. `compute_signal_from_votes`
  is the same alias, so it inherits the guard.

### 1.3 Regression tests

`TestStaleSignalGuard` (4 tests):

- Fresh `last_update` → normal non-stale signal (UP, voters run).
- `last_update` 120s old vs `max_age_seconds=60` → stale NEUTRAL, 0 conviction, empty voters.
- `last_update == 0.0` (never fed) → stale.
- MagicMock feature engine (no `last_update`) → legacy fresh behavior preserved.

`TestLastUpdateTracking` (2 tests):

- Fresh tick stamps `last_update` near `time.time()`.
- Stale tick neither refreshes `last_update` nor mutates `features`.

---

## 2. F-KNOW-004 — OI tracker subscribed to the wrong event shape

### 2.1 The bug

`OITracker.__init__` subscribed to `Topic.MARKET_DATA_BAR`, and `_on_market_data`
expected a dict payload `{symbol, expiry, contracts}`. The only publisher of
`MARKET_DATA_BAR` is `data/pipeline/bar_builder.py`, which publishes a
`core.data_models.Bar` dataclass — an OHLCV aggregate with an optional
per-symbol `oi` field and **no** expiry/strike/option_type chain. The handler's
`isinstance(data, dict)` guard therefore never matched, so the subscription was
silent dead weight: the OI tracker never processed a single bus event.

### 2.2 The fix

`_on_market_data` now matches the real payload shapes (F-KNOW-004):

- `Bar` object → record its aggregate OI via the new `record_symbol_oi(symbol, oi)`;
  a bar cannot feed the per-contract chain path (`update_from_chain` needs
  expiry/strike/option_type), so its OI is kept as symbol-level observations
  exposed via `get_symbol_oi(symbol)`. `clear_oi_data` clears these too.
- option-chain dict `{symbol, expiry, contracts}` → still routes to
  `update_from_chain` (kept for any publisher emitting chains).
- bar-shaped dict `{symbol, oi, ...}` → `record_symbol_oi`.
- any other payload → ignored, never crashes.

### 2.3 Regression tests

`TestMarketDataEvents` (5 tests, all through a live `EventBus` + `publish_nowait`):

- `Bar` with `oi=12345` → `get_symbol_oi("NIFTY") == [12345]`, no chain rows tracked.
- `Bar` with `oi=None` → skipped cleanly.
- chain dict → `get_oi(...) == 1000` via `update_from_chain`.
- bar-shaped dict `{symbol, oi: "77"}` → `[77]` (string coercion).
- unrelated payload `{symbol, ltp, volume}` → no crash, no state.

---

## 3. F-INTEL-008 — Two IV-rank implementations with different units

### 3.1 The bug

Two implementations of IV rank coexisted with different scales:

1. `intelligence/options/options_intel.py::compute_iv_rank` — canonical **0-1**
   pure function `(current - min) / (max - min)`, exported and unit-tested as 0-1.
2. `options/iv_rank.py::IVRankCalculator.compute_iv_rank` — stateful, 0-100
   (`* 100.0`), stored in `IVRankResult.iv_rank`. Its `iv_percentile` is also
   0-100 while `options_intel.compute_iv_percentile` is 0-1.

Both named `compute_iv_rank` — a caller could not tell which scale a result was
on, and the `%` formatter in `research_source.py` silently assumed 0-100.

### 3.2 The fix

Keep the **0-1 scale canonical** (`options_intel.compute_iv_rank` untouched —
tests in `tests/wave2/test_options_intel.py` already lock it to 0-1). The
0-100 class-based variant is a genuinely different service (stateful history,
classification, percentiles) so it is kept but renamed to make the unit explicit:

- `IVRankResult.iv_rank` → `iv_rank_percent`
- `IVRankCalculator.compute_iv_rank` → `compute_iv_rank_percent`
- `classify_iv` internal call updated.
- Caller `terminal/api/research_source.py` updated to
  `rank.compute_iv_rank_percent(symbol)` / `result.iv_rank_percent`.
- Docstrings on `IVRankResult` / `IVRankCalculator` now state the percent scale
  and point at the canonical 0-1 function.

Note (not changed, flagged for awareness): `IVRankResult.iv_percentile` is
also 0-100 vs the 0-1 `compute_iv_percentile` — the same dual-scale pattern
exists for percentiles; left as-is because the ticket scoped F-INTEL-008 to
IV rank.

### 3.3 Regression tests

- `test_percent_rank_is_100x_canonical_zero_to_one` — for a shared history,
  asserts `result.iv_rank_percent == pytest.approx(compute_iv_rank(...) * 100)`
  and that the canonical result is in [0, 1] — the two scales can never silently
  diverge again.
- `test_iv_rank_percent_field_is_0_to_100` — pins the percent field's range.
- Full rename of the existing 13 assertions in `tests/options/test_iv_rank.py`.

---

## 4. F-KNOW-003 — EOD compares UTC hours vs IST config (5h late)

### 4.1 The bug

`PositionManager._is_eod` parsed `eod_exit_time` (config default `"15:15"`,
an **IST** market-close wall-clock) and compared it directly against
`datetime.now(UTC).hour/minute`. IST is UTC+5:30, so the check `(hour, minute) > (15, 15)`
fired at 15:15 **UTC** = 20:45 IST — 5.5 hours after the market closed. An
"end of day" exit that never triggers at 15:15 IST and only fires at 20:45 IST
is functionally a bug: positions stay open across the close, exposed to
overnight gap risk.

### 4.2 The fix

New module constant `_IST_OFFSET_MINUTES = 5 * 60 + 30`. `_is_eod` converts the
IST cutoff to UTC before comparing:

```python
cutoff_utc_min = (eh * 60 + em - _IST_OFFSET_MINUTES) % (24 * 60)
cu_h, cu_m = divmod(cutoff_utc_min, 60)
return (ref.hour, ref.minute) > (cu_h, cu_m)
```

`now` stays UTC (`datetime.now(UTC)` default; the `now` parameter is documented
as UTC). `"15:15"` IST → 09:45 UTC. The strict `>` keeps the exact cutoff open
(same semantics as before). Existing tests that feed UTC times still behave
identically (`15:30 UTC` is past the 09:45 UTC cutoff → EOD).

### 4.3 Regression tests

`test_eod_cutoff_is_ist_not_utc`:

- 10:00 UTC (= 15:30 IST, after close) → EOD **true** (would be false under the old UTC-vs-IST compare).
- 09:44 UTC (= 15:14 IST) → **false** (before cutoff).
- 09:45 UTC (= 15:15 IST, exact cutoff) → **false** (strict `>`).
- 15:30 UTC (the old buggy trigger point = 20:45 IST) → **true** (still EOD, but for the right reason).

`test_eod_default_manage_position_at_ist_cutoff` — end-to-end: `manage_position`
at 10:00 UTC returns `EXIT_EOD` with default config.

---

## Verification

```powershell
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase5b -p no:cacheprovider
# → 1116 passed, 0 failed, 0 errors (2 warnings: upstream pkg_resources + starlette deprecation)
```

Manual gates:

1. Full suite passes: **1116 passed / 0 failed / 0 errors** (suite was 1051 at v0.13.0; +65 incl. 15 new regressions here).
2. `grep -r "import openalgo" src/` → **ZERO matches**.
3. No file > 1000 lines: max modified file is `oi_tracker.py` at 355 lines.
4. `core/` untouched by this lane (no new external imports; the pre-existing `yaml` violation in `core/config/config_manager.py` is unchanged).
5. All modified modules `py_compile` clean.
