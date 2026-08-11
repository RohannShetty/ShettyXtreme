# Phase 5 Lane D — EventBus + Config Fixes: Findings

**Date:** 2026-08-05
**Lane:** D
**Items:** F-CORE-002 (EventBus sync/raising handler crash), F-CORE-004 (config validation),
Oracle #3 (EventBus FIFO ordering under concurrent publishers)
**Status:** Implemented — regression tests green; full-suite reds are sibling-lane WIP only

---

## Summary

Three correctness items in the core layer were fixed:

1. **F-CORE-002** — the EventBus `start()` loop died when a subscriber was sync
   or raised synchronously. The loop now filters to awaitables, catches sync
   exceptions, logs them, and keeps running.
2. **F-CORE-004** — `ConfigManager` claimed validation in its docstring
   ("validate with pydantic") but had none. Added a dependency-free dict-schema
   `validate()` (required keys + type checks) called on every load.
3. **Oracle #3** — the per-publisher FIFO ordering guarantee under concurrent
   publishers was unverified. Added a concurrent publish test and documented the
   guarantee in the module docstring.

Nothing was committed.

---

## 1. F-CORE-002 — EventBus `start()` crash on sync / raising handlers

### Root cause

`src/shettyxtreme/core/event_bus/event_bus.py:75` (old):

```python
results = [h(event) for h in handlers]
gathered = await asyncio.gather(*results, return_exceptions=True)
```

Two failure modes:

- A **sync handler** returns a non-coroutine; `asyncio.gather` then raises
  `TypeError: An asyncio.Future, a coroutine or an awaitable is required`,
  killing the bus loop.
- A handler that **raises synchronously** propagates out of the list
  comprehension, again killing the loop — and it takes down every other
  subscriber for that event with it.

`return_exceptions=True` only covers exceptions raised *inside* awaited
coroutines, not synchronous raises during handler invocation.

### The fix

```python
for handler in handlers:
    try:
        result = handler(event)
    except Exception:
        logger.exception("EventBus handler raised synchronously on topic %s", ...)
        continue
    if inspect.isawaitable(result):
        coroutines.append(result)
    else:
        logger.debug("... returned a non-awaitable result; discarded", handler)
if coroutines:
    gathered = await asyncio.gather(*coroutines, return_exceptions=True)
    ...
```

Design notes:

- The handler is invoked exactly once. Detecting "sync" by *first* calling and
  then re-running via `asyncio.to_thread` would double-invoke side-effecting
  handlers, so sync results are simply discarded (the mission explicitly
  allowed "call them and discard the result").
- `inspect.isawaitable` covers every callable shape — bound async methods,
  `functools.partial` wrappers, and callable instances with `async __call__` —
  which an `iscoroutinefunction` pre-check would miss for callable instances.

### Regression tests (`tests/core/test_event_bus.py`)

- `test_sync_handler_does_not_crash_loop` — sync handler, 3 events delivered.
- `test_sync_handler_raising_does_not_crash_loop` — sync handler raises per
  event; healthy sibling handler still sees both events.
- `test_async_handler_exception_logged_but_loop_continues` — failing AsyncMock
  alongside a healthy async handler; loop processes all 3 events and the error
  is captured by `caplog` (`EventBus handler error`).

---

## 2. F-CORE-004 — ConfigManager had no validation despite the docstring claim

### Root cause

The module docstring promised `Load config.yaml -> override with env vars ->
validate with pydantic`, but there was no validation and no pydantic
dependency — `_load_yaml` set attributes blindly (`setattr` on whatever keys
matched), so a typo like `mode: 123` or a missing `mode` sailed through and
could silently put the system in a bogus execution mode.

### The fix (`src/shettyxtreme/core/config/config_manager.py`)

Added a dependency-free dict schema and a public `validate()`:

- `_SCHEMA` maps every known key to its expected type (`str`, `bool`, or
  `str | None` for the credential fields). Unknown keys are ignored (forward
  compatibility — matches the existing `test_unknown_key_in_yaml_ignored`
  contract).
- `_REQUIRED_KEYS = ("mode",)`. `mode` is the load-bearing safety switch
  (OBSERVER-first, D10), so a config file that fails to declare it raises
  `ValueError`. Everything else has a safe dataclass default, so partial config
  files remain accepted — this preserves the pre-existing behaviour exercised
  by `test_unknown_key_in_yaml_ignored` (which loads a config containing only
  `mode` + an unknown key).
- `validate(data: dict | None = None)` checks required keys and types; with
  `data` omitted it validates the merged config state (defaults + YAML + env)
  via `asdict(self._config)`.
- `_load_yaml` calls `validate(data)` on the raw YAML before applying values;
  `__init__` now delegates to a new `load()` method that runs YAML → env
  overrides → `validate()`. The docstring's false "with pydantic" claim was
  corrected.

### Regression tests (`tests/core/test_config.py`, new `TestConfigValidation`)

- `test_missing_required_key_raises` — YAML without `mode` raises `ValueError`.
- `test_wrong_type_raises` — `mode: 123` raises `ValueError`.
- `test_valid_config_passes` — full valid config constructs and loads.
- `test_validate_method_rejects_partial_mapping` / `test_validate_method_accepts_required_keys_only`
  — exercise the public `validate()` directly (missing key, then a wrong-typed
  `dry_run`).

---

## 3. Oracle #3 — EventBus FIFO ordering under concurrent publishers

### Status before the fix

Unverified. The implementation relies on `asyncio.Queue` (FIFO) drained by a
single `start()` consumer loop, which *should* guarantee that a publisher's own
sequence is delivered in order — but no test exercised concurrent publishers.

### The fix

- **Documentation:** the module docstring now states the guarantee: events are
  delivered strictly FIFO as enqueued; global interleaving across concurrent
  publishers is nondeterministic, but each publisher's events are delivered in
  the order they were published (per-publisher FIFO) because the single
  consumer drains one event at a time.
- **Test** `test_concurrent_publishers_preserve_per_publisher_fifo`: 4
  publishers × 25 events, each yielding `await asyncio.sleep(0)` between
  publishes so the loop genuinely interleaves them; the consumer runs
  *concurrently* with publishing; delivery completes via an `asyncio.Event`
  gate (no flaky sleeps); then asserts all 100 events arrived and each
  publisher's `seq` values are `[0..24]` in order.

No production code change was needed — the guarantee held; it was just
undocumented and untested.

---

## Verification

| Check | Result |
|---|---|
| `tests/core/test_event_bus.py` + `tests/core/test_config.py` | **24 passed** |
| Red-phase confirmation (before fixes) | 6 new tests failed with the exact reported bugs (`TypeError ... awaitable is required`, `ValueError` killing the loop, `AttributeError: no attribute 'validate'`) |
| Full suite run (at completion) | 1047 passed, 13 failed — see below |
| File-size gate (< 1000 lines) | event_bus.py 120, config_manager.py 122 |
| `grep "import openalgo" src/` | unchanged (no matches added) |

### Full-suite reds are sibling-lane WIP, not Lane D

The 13 failures in the final full run map 1:1 to files other lanes are editing
in this shared working tree (verified: none import my modified modules; the one
event_bus reference in `tests/wave2/test_signal_engine.py:248` is
`FeatureEngine(event_bus=MagicMock())` — a mock, untouched by my change):

| Failure set | Sibling lane's file (git status) |
|---|---|
| 7 × `tests/options/test_iv_rank.py` | `src/shettyxtreme/options/iv_rank.py` + test file modified (WIP) |
| 4 × `tests/wave2/test_signal_engine.py::TestStaleSignalGuard` | `src/shettyxtreme/intelligence/signals/signal_engine.py` modified (WIP — staleness guard in progress) |
| 2 × `tests/wave7/test_instrument_init.py` | untracked new file (WIP) |

**Working-tree contention caveat:** during this task the shared tree was reset
by a sibling lane mid-verification (my four files momentarily showed as clean,
then reappeared). One transient failure (`test_intelligence_layers`) referenced
a `signal_engine.py:169` staleness warning that does not exist in the current
file — the file was mid-edit during the run; it passed on re-run. As the Phase 4
lane-e findings documented, treat full-suite reds during the overlap window as
WIP noise, not regressions, and re-run after each lane lands.

Lane-D scope itself: **24/24 tests green** on the targeted run.

## Files touched (Lane D scope only)

- `src/shettyxtreme/core/event_bus/event_bus.py` — resilient `start()` loop
  (catch sync raises, filter to awaitables, discard sync results) + module
  docstring documenting the per-publisher FIFO guarantee + `import inspect`.
- `src/shettyxtreme/core/config/config_manager.py` — `_SCHEMA`/`_REQUIRED_KEYS`
  dict schema, public `validate()`, `load()` entry point wiring YAML → env →
  validate, corrected docstring.
- `tests/core/test_event_bus.py` — 4 new regression tests (sync handler, sync
  raise, async raise + loop-continues + caplog, concurrent FIFO ordering).
- `tests/core/test_config.py` — new `TestConfigValidation` class (5 tests).

This file. No other files were modified. Nothing committed.
