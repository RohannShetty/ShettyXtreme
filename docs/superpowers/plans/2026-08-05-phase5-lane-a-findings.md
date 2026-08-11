# Phase 5 Lane A — Data socket lifecycle fixes (findings)

Date: 2026-08-05 · Lane A (3 items) · Suite baseline 1051 → **1102+ passed** (v0.13.0; see "Suite note" below)

## F-INT-003 — `_fatal_error` never cleared on reconnect — FIXED

**File:** `src/shettyxtreme/integration/fyers/data_socket.py` (`_supervisor`, `connect`, new `reconnect`)

**Finding:** The supervisor loop breaks on `_fatal_error` (token expiry / exhausted retries) and
exits, but the wrapper then left `_running = True` forever (the supervisor's exit path never
reset it). Because `connect()` short-circuits on `_running`, any later `connect()` was a no-op —
**after one fatal error the socket could never recover**, even after the app refreshed the token.
There was also no `reconnect()` API at all.

**Fix:**
- `_supervisor` clears `_fatal_error` at the start of **each supervisor iteration**, so a stale
  fatal error from a previous socket life never poisons a fresh connection attempt.
- The supervisor body is wrapped in `try/finally`; on exit (fatal error, exhausted retries, or
  stop) it releases ownership: `_running = False`, `_supervisor_future = None`, `_socket = None`,
  `_reconnecting = False`. A subsequent `connect()` now actually restarts the supervisor.
- New `async def reconnect()`: clears `_fatal_error` then delegates to `connect()` — the explicit
  recovery path after a fatal condition (e.g. token refreshed).

**Tests added** (`tests/integration/test_fyers_data_socket.py`, class `TestRecovery`):
- `test_reconnect_recovers_after_transient_fatal_error` — first socket fires a token-expiry SDK
  error (`11001`), supervisor stops and releases ownership; `reconnect()` restores the socket,
  clears the error, and re-applies the outstanding subscription set.
- `test_connect_after_fatal_error_restarts_supervisor` — plain `connect()` after a fatal error
  also recovers, proving the ownership-release fix.

## F-INT-004 — Socket fatal errors invisible to app — FIXED

**File:** `src/shettyxtreme/terminal/api/terminal_init.py` (order-socket wiring block)

**Finding:** The order-socket wiring registered only `on_message`. `FyersOrderSocket` already
supports `on_error(exc)` and `on_close()` callbacks, but nothing was wired — transport errors and
socket closes were silent logger lines with no path to the app/UI.

**Fix:** Wired both callbacks on the order socket. Each logs the event and publishes a
`Topic.SYSTEM_STATUS` event on the app event bus (`source="fyers_order_socket"`):
- `on_error(exc)` → `{"status": "data_socket_error", "error": str(exc)}`
- `on_close()` → `{"status": "data_socket_closed"}`

The event bus is already in scope at that point in `init_terminal_adapters`; the callbacks are
async and `FyersOrderSocket._notify_error`/`_notify_close` await coroutine results, so both sync
and async handlers are supported.

**Test added** (`tests/wave7/test_terminal_init.py`):
- `test_order_socket_error_and_close_publish_system_status` — runs the full init, extracts the
  wired `on_error`/`on_close` callbacks, drives each, and asserts a `SYSTEM_STATUS` event with
  the correct payload (`data_socket_error` with the error string, `data_socket_closed`).

## F-INT-010 — `connected` reports True during restart backoff — FIXED

**File:** `src/shettyxtreme/integration/fyers/data_socket.py` (`connected` property, `_supervisor`)

**Finding:** `connected` returned `self._socket is not None`. During restart backoff the
supervisor is still running (waiting out `_stop_event.wait(delay)`) and still references the dead
previous socket object — so `connected` reported **True while the link was actually down**.

**Fix:**
- New `_reconnecting` flag: set `True` for the duration of the backoff delay, reset to `False`
  when the next socket is built and on supervisor exit.
- `connected` is now `self._socket is not None and not self._reconnecting` — False during
  backoff, True once a fresh socket is live. `is_connected()` inherits the fix (the F4 adapter's
  health check goes through it).

**Test added** (`tests/integration/test_fyers_data_socket.py`, class `TestBackoffReporting`):
- `test_connected_false_during_restart_backoff` — dropping socket with a 1s backoff: asserts
  `_reconnecting` is True and `connected` is False while waiting, and both return to False/False
  after a local disconnect.

## Suite note

- My scope (data_socket + terminal_init + their tests) is green: `tests/integration/test_fyers_data_socket.py`
  and `tests/wave7/test_terminal_init.py` pass 22/22 including the 4 new regression tests.
- Red-green verified for all 4 new tests (each fails against the unfixed code, passes with the fix).
- Full-suite runs during this session were unstable **not because of Lane A changes**: other lanes
  (B and later) are actively editing files under the running suite (`test_iv_rank`, `test_feature_engine`,
  `test_credential_store`, `test_intelligence`, `test_fyers_instrument_master`) — failure sets changed
  between identical runs, and the `test_intelligence_layers` failure reproduces only with the other
  lanes' `event_bus.py`/`signal_engine.py`/`feature_engine.py` changes in the tree (verified: passes on
  clean HEAD). No Lane A file is imported by any failing test.
