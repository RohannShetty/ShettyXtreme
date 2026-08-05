# Phase 5 Lane F — Terminal/execution fixes (findings)

Date: 2026-08-05 · Lane F (4 items) · Suite baseline 1051 → **1116 passed / 0 failed** (v0.13.0)

## F-TERM-002 — ws_manager double-disconnect race → ValueError — FIXED

**File:** `src/shettyxtreme/terminal/api/ws_manager.py` (`WebSocketManager.disconnect`)

**Finding:** `disconnect()` called `self._connections.remove(websocket)` unconditionally.
When the client-drop path and the server-shutdown path race (app.py's WS endpoint
calls `disconnect` on disconnect, and `broadcast()` also removes dead connections via
`disconnect`), the second call raised `ValueError: list.remove(x): x not in list`.

**Fix:** Membership guard first — `if websocket not in self._connections: return`.
`disconnect()` is now idempotent: a second call for an already-removed connection is a
silent no-op. `_topics.pop(websocket, None)` was already safe (dict.pop with default).

**Tests added** (`tests/wave3/test_ws_manager.py`):
- `test_double_disconnect_is_idempotent` — disconnect twice; no raise, count 0, topics empty.
- `test_disconnect_never_connected_is_noop` — disconnect a never-connected ws; no raise.

## F-TERM-005 — Adapter transport failures → raw 500 — FIXED

**File:** `src/shettyxtreme/terminal/api/market_router.py` (`/bars`, `/ltp`)

**Finding:** The router only caught `FyersDataEntitlementError`. Any other adapter
failure — `FyersRateLimitError` (the data adapter does NOT swallow it on the history
path), httpx transport errors (`httpx.ConnectTimeout`, `ReadTimeout`, `ConnectError`,
…) and `asyncio.TimeoutError` — bubbled up as a raw 500 exposing the exception message
(Fyers SDK internals) and gave the client no way to tell transient from permanent.

**Fix:** Added `_adapter_error_response(exc)` classifying by exception type, plus a
catch-all `except Exception` on both endpoints that re-raises the classified
`HTTPException` (never the raw exception text):
- `FyersTokenExpired` → **500** `{error_code: auth_failed}` (permanent: auth/config).
- `FyersRateLimitError` → **503** `{error_code: rate_limited}` (transient).
- `asyncio.TimeoutError` / `httpx.TransportError` → **503** `{error_code: upstream_unavailable}` (transient: network).
- anything else → **500** `{error_code: adapter_error}`.

The pre-existing `FyersDataEntitlementError` → 503 path is unchanged (string detail,
covered by existing tests — no existing test churn).

**Tests added** (`tests/wave7/test_market_router.py`, via a `RaisingAdapter` that
raises a fixed exception from every data verb):
- `test_bars_network_timeout_503_structured` — `httpx.ConnectTimeout` → 503,
  `error_code == upstream_unavailable`, raw message (`connect timed out`) not leaked.
- `test_bars_asyncio_timeout_503_structured` — `asyncio.TimeoutError` → 503.
- `test_bars_rate_limit_503_structured` — `FyersRateLimitError` → 503, `rate_limited`.
- `test_bars_auth_failure_500_structured` — `FyersTokenExpired` → 500, `auth_failed`,
  raw `HTTP 401` not leaked.
- `test_bars_generic_adapter_error_500_structured` — `RuntimeError` → 500, `adapter_error`,
  raw message not leaked.
- `test_ltp_transport_timeout_503_structured` — `/ltp` path classifies `ReadTimeout` → 503.

## F-AUTH-001 — Pre-market liveness probe always used a credential-less client — FIXED

**File:** `src/shettyxtreme/auth/health_monitor.py` (`TokenHealthMonitor`)

**Finding:** `__init__` defaulted `self._http_client = http_client or FyersHTTPClient()`.
Because `_http_client` was therefore *always* truthy, the probe's
`client = self._http_client or FyersHTTPClient(app_id=app_id, access_token=access_token)`
always picked the **credential-less** client — the credentialed branch was dead code.
Every morning at 8:45 IST the probe called `/profile` without credentials, got
`FyersTokenExpired("No Fyers credentials configured")`, and published a false
`TOKEN EXPIRED — re-auth required` warning even with valid credentials.

**Fix:**
- `self._http_client = http_client` (default `None`) — do not eagerly create a
  credential-less client. When no client is injected, the probe now builds
  `FyersHTTPClient(app_id=…, access_token=…)` from the store (matches the
  `CredentialValidator` pattern).
- Probe guard tightened to `if not access_token or not app_id: return` — with no
  credentials the probe is skipped entirely (no client, no false alarm).

**Tests added** (`tests/wave7/test_health_monitor.py`, monkeypatching
`health_monitor.FyersHTTPClient` with a recording client):
- `test_premarket_probe_uses_credentialed_client_when_available` — store with
  `app_id="APP123"`, `access_token="tok_probe"` → probe constructs a client with
  exactly `("APP123", "tok_probe")`.
- `test_premarket_probe_skips_when_no_token` — store without token → no client
  constructed, no `CREDENTIAL_WARNING` published.

## Oracle #5 — Credential encryption key derivation — AUDITED, NOT STATIC

**File:** `src/shettyxtreme/auth/credential_store.py` (`CredentialStore._fernet`)

**Finding:** The key is **not** a static fallback and **not** a hardware secret. It is
derived per machine: `urlsafe_b64encode(sha256(hostname + username).digest())` → Fernet
key. Properties verified by test:
- **Machine-bound in practice** — different hostname/user derive different keys, so
  `credentials.enc` is not portable: a store written on machine A returns `None` from
  `load()` on machine B (decrypt fails), never the plaintext.
- **Deterministic per machine** — same hostname+user always derives the same key, so
  saves survive restarts on the same machine.

Documented limitations (accepted for a local single-workstation tool, now in the module
docstring): (1) hostname+username is low-entropy and guessable, so an attacker holding
the ciphertext could brute-force the key offline — there is no DPAPI/TPM binding; (2) two
machines sharing both hostname AND username would derive the same key. No warning log was
added because the key is machine-bound, not static (the static case is what the task
specified a warning for).

**Tests added** (`tests/wave7/test_credential_store.py`):
- `test_fernet_key_derivation_is_machine_bound` — different hostname → different Fernet.
- `test_fernet_key_derivation_is_deterministic` — same machine identity: a payload
  encrypted with one derivation decrypts with the next (cross-decrypt, not `==` on
  `Fernet` objects, which has no `__eq__`).
- `test_credentials_not_portable_across_machines` — save on machine A, `load()` on
  machine B → `None`.

## Verification

- Affected test files: `test_ws_manager.py` (13), `test_market_router.py` (20),
  `test_health_monitor.py` (13), `test_credential_store.py` (14) — **60 passed**.
- Full suite with a fresh basetemp: **1116 passed / 0 failed / 0 errors**
  (`pytest tests/ -q --tb=short --basetemp=…pytest-phase5-lanef -p no:cacheprovider`).
- NOTE: the shared `pytest-phase5` basetemp shows intermittent Windows
  `PermissionError`/`FileExistsError` setup errors when parallel lanes run the suite
  concurrently (SQLite DB file locks) — environmental, unrelated to this lane; a unique
  basetemp per run eliminates them.
- Gates: no `import openalgo` in `src/`; no file > 1000 lines (max changed file:
  `test_health_monitor.py` at 426).
- Diff confined to: `ws_manager.py`, `market_router.py`, `health_monitor.py`,
  `credential_store.py`, the four corresponding test files, and this report.
