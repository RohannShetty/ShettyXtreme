# Phase 5 Lane B — Tick/bar correctness fixes (findings)

Date: 2026-08-05 · Lane B (3 items) · Suite baseline 1051 → **1053 passed / 0 failed** (v0.13.0)

## F-INT-005 — Live tick OI hardcoded to None — FIXED

**File:** `src/shettyxtreme/integration/fyers/data_adapter.py` (`_parse_tick`)

**Finding:** `_parse_tick` returned `oi=None` unconditionally even though the SDK
tick dict carries open interest. Verified the field name from the installed SDK
(`.venv/Lib/site-packages/fyers_apiv3/FyersWebsocket/map.json`): the `data_val`
list (which the HSM decoder emits as tick keys) contains the uppercase **`OI`**
field — no `open_interest` variant exists. `index_val` (index ticks) does **not**
carry OI.

**Fix:**
- Read `raw.get("OI")` and pass `oi=_to_int(raw_oi) if raw_oi is not None else None`.
- Missing/invalid → `None` (honest, matches history-candle parsing which also
  yields `None` for absent OI).
- Docstring updated to document the `OI` key and its data_val-only presence.
- The `Tick` dataclass already declared `oi: int|None = None` — no dataclass change.

**Bonus:** because `BarAggregator.apply` already snapshots `tick.oi` into the bar,
live bars now inherit OI from parsed ticks automatically (no extra change).

**Tests added** (`tests/integration/test_fyers_data_adapter.py`):
- `TestSubscribeTicks.test_oi_extracted_when_present` — tick with `OI: 123456` →
  `tick.oi == 123456`.
- `TestSubscribeTicks.test_oi_none_when_missing` — index tick without `OI` key →
  `tick.oi is None`.

## F-INT-006 — Bar volume = per-tick sum of cumulative `vol_traded` — ALREADY FIXED

**File:** `src/shettyxtreme/integration/fyers/_util.py` (`BarAggregator.apply`)

**Finding:** Already fixed (by F-INTEL-002 in a prior phase). Lines 169–172 snapshot
`volume_at_bar_open` from the first tick of the bar, and line 177 computes the bar
volume as the delta `max(0, tick.volume - baseline)` — never a running sum of
cumulative values. No change needed.

**Existing regression test:** `TestSubscribeBars.test_client_side_aggregation_from_ticks`
feeds cumulative `vol_traded_today` (1000 → 1005 → 1010) and asserts `bar.volume == 5`
(not 1000 + 1005 + 1010). Skipped (documented only).

## F-INT-007 — `subscribe_bars` keyed by unresolved symbol — ALREADY FIXED

**File:** `src/shettyxtreme/integration/fyers/data_adapter.py` (`subscribe_bars`)

**Finding:** Already fixed. Line 272 resolves every symbol via
`self._resolve_symbol(s, "NSE_FNO")` and the resolved tickers are what gets
subscribed (`resolved` list → `self._data_socket.subscribe(resolved, "SymbolUpdate")`,
line 277). Note the bar-callback/aggregator keys deliberately use the raw internal
symbol (`(str(s).strip(), tf_label)`) so tick dispatch matches on the internal
symbol — the subscription itself uses the resolved ticker. No change needed.

**Existing regression test:** `TestSubscribeBars.test_client_side_aggregation_from_ticks`
asserts `data_socket.subscribe.assert_awaited_once_with(["NSE:SBIN-EQ"], "SymbolUpdate")`
— resolved ticker, not the raw `"SBIN"`. Skipped (documented only).

## Verification

- `tests/integration/test_fyers_data_adapter.py` + `test_fyers_util.py`: **22 passed**
- Full suite: **1053 passed / 0 failed** (`pytest tests/ -q --tb=short --basetemp=… -p no:cacheprovider`)
- Diff is confined to: `data_adapter.py` (`_parse_tick` OI extraction + docstring),
  `test_fyers_data_adapter.py` (2 new tests), and this report.
