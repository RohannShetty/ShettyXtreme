# P1-2.4 — UI State Confusion: Connected / Disconnected / Open

**Date:** 2026-08-12
**Severity:** P1 (header shows contradictory connection states; operator cannot trust the status chrome)
**Component:** `terminal/projections.py` (HealthProjection) → `terminal/api/health_router.py` + `terminal/api/auth_router.py` → `terminal/web/src/components/Header.svelte` + `terminal/web/src/lib/ws.ts`

---

## Executive summary

The header renders **three independent status widgets fed by three different backend
sources with two different definitions of "connected"**, and neither the backend nor the
frontend has a connection state machine. The connection pip derives its state locally in
`Header.svelte` from a 30-second REST poll of `/api/health`; the credential chip derives
"CONNECTED" from `/auth/status` where `connected = token_valid and bool(access_token)` —
**a token-validity check, not a socket check**. So the pip can honestly say DISCONNECTED
(data socket down) while the cred chip says CONNECTED (token valid), and vice-versa.
Meanwhile the browser WebSocket client tracks its own module-level connection state that
**no component can read**, so a dropped WS silently freezes the LTP hero while the pip
still pulses LIVE. There is no CONNECTING state anywhere, STALE is dead code for the Fyers
adapter, and health is pull-only — socket drops are never pushed to the UI.

---

## 1. Current state architecture

### 1.1 HealthProjection — pull-only, no state field, subscribes to nothing

`src/shettyxtreme/terminal/projections.py:349-473`

```python
class HealthProjection:
    def __init__(self) -> None:
        self._event_bus: EventBus | None = None
        self._data_adapter: Any = None
        self._trading_adapter: Any = None
        self._feature_engine: Any = None
        self._signal_engine: Any = None
        self._token_health_provider: Any = None

    def subscribe(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus          # ← stores the bus, subscribes to NOTHING

    def get(self) -> dict[str, Any]:          # ← pure pull: recomputed on every call
        ...
        components.append({"name": "data_adapter", "status": da_status, ...})
        components.append({"name": "trading_adapter", "status": ta_status, ...})
        ...
        return {"components": components, "overall": overall}
```

**Key facts:**

- **No `status`/`state` field.** `get()` re-derives everything fresh each time it is called.
  There is no stored state to transition between.
- **Not event-driven.** `subscribe()` keeps the bus reference but registers no handlers.
  HealthProjection does **not** subscribe to `SYSTEM_STATUS` or `CREDENTIAL_HEALTH_CHANGED`
  even though both topics exist (`core/event_bus/event_bus.py:34,40`).
- **Per-component status vocab:** `healthy / stale / disconnected / token_expired / down`,
  plus `overall` ∈ `healthy / degraded / down`. There is **no `connecting`** value anywhere.

**Component derivation details (the bugs live here):**

| Component | Logic | Gap |
|---|---|---|
| `data_adapter` | `_data_adapter_connected()` → `adapter._connected` else `adapter._data_socket.connected`; then `_data_adapter_stale()` → `adapter.is_stale(threshold=60)` | Fyers `FyersDataAdapter` has **no `is_stale` method** (grep: only `is_connected`) → `_data_adapter_stale` returns `False` always → **STALE can never be reported for Fyers** |
| `data_adapter` connected | `FyersDataSocketWrapper.connected` = `self._socket is not None and not self._reconnecting` (`data_socket.py:126-132`) | During reconnect backoff `_reconnecting=True` → reports DISCONNECTED while the supervisor is actively retrying. No CONNECTING distinction |
| `trading_adapter` | only `token_expired` when `_token_health_provider()` is False; else `healthy` | **Socket/connection never checked.** `FyersTradingAdapter.is_connected()` exists (`trading_adapter.py:128`) but is never called |
| `intelligence` | `disconnected` when engines missing, else `healthy` | N/A |
| `storage` | hardcoded `healthy` | N/A |

### 1.2 REST surface — two endpoints, two "connected" meanings

- **`GET /api/health`** (`terminal/api/health_router.py:66-81`) → `HealthProjection.get()`.
  The pip's source. `data_adapter` status = real socket state.
- **`GET /auth/status`** (`terminal/api/auth_router.py:92-107`):
  ```python
  token_valid = store.is_token_valid() if store.access_token else False
  connected = token_valid and bool(store.access_token)
  ```
  → `connected` here means **credentials exist and the token is not expired**. It says
  nothing about whether any socket is up. This is the cred chip's source.

### 1.3 Header.svelte — three independent widgets, local `$state`

`src/shettyxtreme/terminal/web/src/components/Header.svelte`

**State (all local `$state`, no shared store):**
- `health: HealthResponse | null` — 30s poll of `/api/health` (line 50, 110)
- `session: Session | null` — same poll of `/api/health/session` (line 51, 111)
- `credStatus: AuthStatus | null` — 30s poll of `/auth/status` (line 52, 122)

**Three widgets rendered from three sources:**

1. **Connection pip** (`pipState()` lines 163-202) — derives locally:
   ```ts
   type PipState = "live" | "stale" | "disconnected" | "expired" | "unknown";
   ```
   Maps backend `status` → rank via `statusRank()` (`token_expired`=4, `down/disconnected`=3,
   `stale/degraded`=2, `healthy`=1), takes the worst of the broker components
   (`data_adapter`, `trading_adapter`, `dhan_data`, `dhan_trading`). Labels: LIVE / STALE /
   DISCONNECTED / EXPIRED / "…". **Note the vocabulary drift: backend says `token_expired`,
   frontend labels it "EXPIRED".**
2. **Cred chip** (lines 284-298) — `credStatus.connected` → `CONNECTED` (ok), else
   `has_token && !token_valid` → `REAUTH` (warn), else → `SETUP` (mute).
3. **Session** (lines 277-282) — `session.status` (market open/closed/pre_open/post_close).
   This one is fine — it is market hours, not connectivity — but it sits next to the other
   two and compounds the visual noise.

**The contradiction in one line:** pip says `DISCONNECTED` (data socket dead) while the
cred chip says `CONNECTED` (token valid). Both are "correct" under their own definitions —
the header just never reconciles them.

### 1.4 WebSocket client — tracks state, emits nothing

`src/shettyxtreme/terminal/web/src/lib/ws.ts`

- Module-level state: `socket`, `stopped`, `reconnectAttempt`, `keepAlive`, `retryTimer`.
- `onopen` resets the attempt counter, starts pings, sends subscribe. `onclose` schedules
  backoff reconnect. **Neither dispatches any message to handlers** — there is no
  `"connection"` / `"status"` topic, and `dispatch()` is only called from `onmessage`.
- No exported getter for socket state (`stopped`/`socket` are module-private).
- **Consequence:** the browser WS can drop and the UI has no idea. The LTP hero freezes
  silently while the pip (fed by REST, not the WS) still pulses LIVE. `App.svelte:155`
  calls `connect()` once; nothing else observes it.

### 1.5 EventBus — the push infrastructure exists but is unused by health

- `Topic.SYSTEM_STATUS` (`core/event_bus/event_bus.py:34`) is published by the Fyers order
  socket on close/error (`terminal/api/terminal_init.py:225-244`). **Only `AlertProjection`
  consumes it** (`projections.py:233`) — HealthProjection ignores it.
- `Topic.CREDENTIAL_HEALTH_CHANGED` (`event_bus.py:40`) is published every 60s by
  `TokenHealthMonitor` (`auth/health_monitor.py:80`) with status `HEALTHY / EXPIRING_SOON /
  EXPIRED / UNKNOWN`. **No UI consumer exists.** This is a ready-made EXPIRED event source.
- `ws_bridge.broadcast()` (`terminal/api/ws_bridge.py`) is the push channel — used by every
  other projection, never by health.

---

## 2. What is causing the confusion

1. **Two definitions of "connected" collide in one header.**
   `/auth/status.connected` = token validity; `HealthProjection.data_adapter` = live socket.
   The pip and the cred chip can contradict each other indefinitely (and will: a socket drop
   doesn't invalidate the token, so DISCONNECTED pip + CONNECTED cred chip is the *normal*
   failure state).

2. **No state machine — statuses are ad-hoc derivations.**
   Backend `get()` recomputes per-component booleans on demand; frontend `pipState()` maps
   ranks locally. Nothing models the requested
   `DISCONNECTED → CONNECTING → CONNECTED → STALE → EXPIRED → DISCONNECTED` lifecycle.
   **CONNECTING does not exist in any layer** — the Fyers data socket's `_reconnecting`
   flag and `ws.ts`'s `reconnectAttempt` both represent it, but both collapse to DISCONNECTED
   at the UI.

3. **Health is pull-only (30s REST poll); socket drops are never pushed.**
   The backend publishes `SYSTEM_STATUS` on socket death but HealthProjection doesn't
   subscribe; the frontend WS client doesn't emit state. The pip can be up to 30s stale, and
   a reconnect that succeeds between polls is invisible (pip shows DISCONNECTED until the
   next poll heals it).

4. **STALE is dead code.**
   `_data_adapter_stale()` depends on `adapter.is_stale`, which `FyersDataAdapter` doesn't
   implement → returns `False` always. No component can ever enter STALE.

5. **Trading adapter connectivity is never measured.**
   Only token expiry is checked; `FyersTradingAdapter.is_connected()` is never called, so a
   dead trading socket still reads `healthy`.

6. **Vocabulary drift: `token_expired` (backend) vs `EXPIRED` (pip label) vs
   `EXPIRING_SOON`/`EXPIRED` (TokenHealthMonitor).** Three different names for the same
   domain concept across three surfaces.

7. **The browser WS's own health is invisible.**
   The pip answers "is the *backend* healthy?" not "is *this tab's* live feed up?" — a dead
   local WS freezes data with a green LIVE pip. This is the "connected but frozen" report.

8. **Every consumer polls separately.** Header polls health + auth + session; SettingsView
   and SetupWizard poll `authStatus()` independently (`SettingsView.svelte:70`,
   `SetupWizard.svelte:29`). No shared front-end connection store.

---

## 3. Proposed fix approach — one state machine, one source of truth

### 3.1 Backend: a real stateful HealthProjection (event-driven)

Give `HealthProjection` a stored `_state` field and make it subscribe to the EventBus:

- **Inputs (events):**
  - `SYSTEM_STATUS` → socket connected / closed / error / reconnecting (publish
    `CONNECTING` while `_reconnecting` is true — the Fyers data socket already exposes
    `restart_attempts` and `connected`, `data_socket.py:126-144`).
  - `CREDENTIAL_HEALTH_CHANGED` → EXPIRED / EXPIRING_SOON (already published by
    `TokenHealthMonitor`).
  - `MARKET_DATA_TICK` → heartbeat: mark last-tick time (feeds STALE after a threshold,
    mirroring the panel-level STALE chips).
- **State machine (single enum, both layers agree on names):**
  `DISCONNECTED → CONNECTING → CONNECTED → STALE → EXPIRED → DISCONNECTED`
  (EXPIRED supersedes; token re-auth returns to CONNECTING).
- **Output:** `/api/health` returns the machine state + per-component detail; push a
  `"connection"` broadcast via `ws_bridge.broadcast()` on every transition so the UI is
  event-driven, not polled.
- Fix `_data_adapter_stale()`: either implement `is_stale` on `FyersDataAdapter` (track
  last-tick timestamp in the tick callback) or switch staleness to tick-activity-based.
- Check `FyersTradingAdapter.is_connected()` in the trading component.

Reuse: `Topic.SYSTEM_STATUS` + `Topic.CREDENTIAL_HEALTH_CHANGED` already exist;
`AlertProjection` already demonstrates the subscribe-pattern; `ws_bridge.broadcast()` is the
push channel; `_data_adapter_connected()` is the adapter-introspection seed.

### 3.2 Frontend: one connection store, remove local derivation

- New `lib/connection.ts` — a single Svelte 5 `$state` store holding
  `{ state: PipState, detail: string }`, fed by:
  1. a new `onMessage("connection", ...)` handler in `ws.ts` (server-pushed transitions), and
  2. the existing `/api/health` poll as a fallback/backfill.
- `ws.ts`: emit local state via the handler registry on `onopen`/`onclose`/`onerror` (e.g.
  dispatch a synthetic `"connection"` event to registered handlers, or add
  `onConnectionChange(cb)`); expose `isConnected()` for debugging.
- `Header.svelte`: replace `health`-derived `pipState()` with a read of the store; keep the
  cred chip but reconcile it against the machine (e.g. cred chip shows CONNECTED only when
  the machine is CONNECTED **and** token valid; REAUTH when EXPIRED).
- Drop Header's local `health`/`session` `$state` duplication where the store covers it;
  SettingsView/SetupWizard can keep their own auth polls (settings is a config surface, not
  the status chrome) — or migrate to the store for consistency.

Reuse: `Header.svelte`'s `pipState()`/`statusRank()` is the seed of the front-end machine;
`ws.ts`'s `onMessage` registry already supports adding a topic; `ws_bridge`/`ws_manager`
already broadcast topic-framed JSON.

### 3.3 Definition of done for the fix

- A single `state` value renders identically in pip + cred chip (no contradictions possible).
- CONNECTING is observable during reconnect (both the Fyers socket backoff and `ws.ts`
  backoff surface it).
- STALE is reachable (tick-based staleness for Fyers).
- EXPIRED transitions arrive via `CREDENTIAL_HEALTH_CHANGED` (or token provider), not a
  30s poll.
- A dropped browser WS visibly degrades the pip (LIVE → DISCONNECTED/CONNECTING) instead of
  silently freezing the hero.
- No file exceeds 1000 lines; full suite + `svelte-check` pass per AGENTS.md gates.

---

## 4. Evidence index (file:line)

| Concern | Location |
|---|---|
| HealthProjection, no state, pull-only | `src/shettyxtreme/terminal/projections.py:349-473` |
| `subscribe()` stores bus, no handlers | `projections.py:360-361` |
| `_data_adapter_connected` (socket introspection) | `projections.py:315-329` |
| `_data_adapter_stale` (relies on absent `is_stale`) | `projections.py:332-344` |
| Fyers data socket `connected`/`_reconnecting` | `src/shettyxtreme/integration/fyers/data_socket.py:126-144` |
| Fyers data adapter has `is_connected`, no `is_stale` | `src/shettyxtreme/integration/fyers/data_adapter.py:123-124` |
| Trading adapter `is_connected` never checked by health | `src/shettyxtreme/integration/fyers/trading_adapter.py:128` |
| `/api/health` endpoint | `src/shettyxtreme/terminal/api/health_router.py:66-81` |
| `/auth/status` → `connected = token_valid and has token` | `src/shettyxtreme/terminal/api/auth_router.py:92-107` |
| Header local `$state` + 30s polls | `src/shettyxtreme/terminal/web/src/components/Header.svelte:50-126` |
| pipState/statusRank local derivation | `Header.svelte:163-202` |
| Cred chip CONNECTED/REAUTH/SETUP | `Header.svelte:284-298` |
| WS client: state tracked, never emitted | `src/shettyxtreme/terminal/web/src/lib/ws.ts:35-141` |
| App calls `connect()` once, no observation | `src/shettyxtreme/terminal/web/src/App.svelte:155` |
| SYSTEM_STATUS published (order socket) | `src/shettyxtreme/terminal/api/terminal_init.py:225-244` |
| SYSTEM_STATUS consumed only by AlertProjection | `projections.py:233` |
| CREDENTIAL_HEALTH_CHANGED published 60s | `src/shettyxtreme/auth/health_monitor.py:68-87` |
| Topics available | `src/shettyxtreme/core/event_bus/event_bus.py:24-45` |
| Push channel | `src/shettyxtreme/terminal/api/ws_bridge.py:26-39` |
| Independent auth polls elsewhere | `SettingsView.svelte:70`, `SetupWizard.svelte:29` |
