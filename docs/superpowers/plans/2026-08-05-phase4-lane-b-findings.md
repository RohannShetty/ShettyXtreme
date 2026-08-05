# Phase 4 Lane B — Integration Fixes: F-INT-011 + F-INT-009

**Date:** 2026-08-05
**Scope:** Phase 4 Lane B (quick wins after Phase 3 cockpit redesign) — 2 integration items, both Fyers.
**Status:** Complete — both fixes implemented with regression tests.

---

## Deliverables

| Item | File | Change |
|---|---|---|
| F-INT-011 | `src/shettyxtreme/integration/fyers/trading_adapter.py` | Account endpoints no longer swallow fatal `FyersError`s: token expiry raises, the -373 data-entitlement error raises with endpoint context, everything else still degrades to `[]`/`{}` |
| F-INT-009 | `src/shettyxtreme/integration/fyers/session.py` | `is_valid()` treats an unknown expiry (`None`) as expired → the LIVE session-validity gate now forces re-auth instead of waving an unverifiable token through |
| — | `tests/integration/test_fyers_trading_adapter.py` | Replaced the obsolete "token expiry → `[]`" test with a 15-case `TestAccountErrorClassification` suite |
| — | `tests/integration/test_fyers_session.py` | Updated unknown-expiry tests to the honest semantics + F-INT-009 regression |
| — | `tests/integration/test_fyers_data_adapter.py` | Fixture now carries a provable expiry; added `test_is_available_false_when_expiry_unknown` |
| — | `tests/execution/test_mode_router.py` | End-to-end LIVE-gate regression: real `FyersTradingAdapter` + unknown-expiry session → placement rejected with "re-auth required" |

No source change to `mode_router.py` was required: it already probes the adapter's
`is_session_valid()` and rejects on `False` with the "token expired — re-auth
required" message, so making `is_valid()` honest is sufficient to gate LIVE.

---

## 1. F-INT-011 — Classify FyersErrors on account endpoints

### 1.1 The bug

Every account endpoint (`get_positions`, `get_holdings`, `get_order_book`,
`get_trade_book`, `get_margin`) wrapped its REST call in a bare
`except FyersError → return []/{}`. The transport taxonomy
(`client.py`) classifies HTTP 401 / codes -8/-15/-16/-17 as
`FyersTokenExpired` and HTTP 403 / code -373 as `FyersDataEntitlementError`
(the Dhan-806 twin) — but all three types are `FyersError` subclasses, so a
dead token or a missing data entitlement looked exactly like "empty account".

Consequences: the cockpit rendered an empty positions/holdings/margin view while
the token was dead, and the operator had no signal that the app had lost the
entitlement to read account data at all.

### 1.2 The fix

New static helper `_raise_fatal_account_error(exc, endpoint)`:

- `FyersDataEntitlementError` → re-raise **with endpoint context**:
  `f"{message} — GET /positions (code -373)"` (chain preserved via `from exc`).
- `FyersTokenExpired` → re-raise as-is so upstream re-auth gates fire.
- anything else (`FyersRateLimitError`, `FyersAPIError`) → no-op, endpoint
  degrades to `[]`/`{}` as before.

Upstream callers are exception-safe already: the margin poller wraps in
`try/except Exception` (publishes nothing → margin stays UNKNOWN), and the
positions REST endpoint reads a projection, not the adapter directly. Raising
surfaces the failure in logs instead of silently masking it.

### 1.3 Regression tests

`TestAccountErrorClassification` (15 cases, parametrized over all five account
endpoints):

- token expiry → `pytest.raises(FyersTokenExpired)` for every endpoint
- -373 → `pytest.raises(FyersDataEntitlementError)`, `code == -373`, and the
  endpoint path appears in the message
- `FyersAPIError` (transient) → still degrades to the empty payload

The old `test_get_positions_returns_empty` (asserted `[]` on token expiry) was
removed — it codified the masked behavior this finding is about.

---

## 2. F-INT-009 — Honest session-validity gate for unknown expiry

### 2.1 The bug

`FyersSession.is_valid()` returned `True` when `token_expiry is None`. Fyers
does not publish a TTL, so unknown-expiry sessions are common (stale/legacy
stores). Because the LIVE gate (`mode_router.py` → adapter `is_session_valid()`
→ `session.is_valid()`) is driven entirely by this cheap check, an unknown
expiry made the gate a no-op: an unverifiable token could reach the wire.

### 2.2 The fix (chosen option: treat unknown as expired)

`is_valid()` now returns `False` when `token_expiry is None` — a token that
cannot be proven live is treated as expired (force re-auth). Rationale:

- The auth flow **always** records the heuristic expiry
  (`fyers_oauth.py: _default_token_expiry()`, next ~6 AM IST) on login, so
  unknown expiry only arises for stale/legacy sessions — exactly the ones that
  must re-auth.
- It is the only option that actually gates LIVE; "log warning + allow" keeps
  the no-op the finding describes.
- Consistent with the architecture contract (`11-fyers-integration.md`):
  "Token expiry → STALE-freeze, never zeros; LIVE gated on session validity".

### 2.3 Behavior consequences (intended, honest)

- `mode_router` LIVE placement/modify/cancel → rejected "token expired — re-auth
  required" for unknown expiry.
- `data_adapter.is_available()` → `False` for unknown expiry (a session that
  cannot be proven live is not "available").
- `app.py _token_health` → reports unhealthy for unknown expiry.

### 2.4 Regression tests

- `test_fyers_session.py::test_unknown_expiry_is_treated_as_expired` — the core
  regression (was `test_unknown_expiry_cannot_be_proven_expired`, asserted the
  old masked behavior).
- `test_round_trip_without_expiry` → a persisted session with no expiry loads as
  invalid.
- `test_fyers_data_adapter.py::test_is_available_false_when_expiry_unknown`.
- `test_mode_router.py::test_live_place_blocked_when_session_expiry_unknown` —
  end-to-end through the **real** `FyersTradingAdapter`: LIVE placement with an
  unknown-expiry session is rejected with "re-auth required".
- `test_fyers_trading_adapter.py::test_is_connected_delegates_to_session` —
  updated: unknown expiry → not connected.

---

## 3. Verification

| Gate | Result |
|---|---|
| `tests/integration/test_fyers_session.py` + `test_fyers_trading_adapter.py` + `test_fyers_data_adapter.py` + `test_mode_router.py` | **80 passed** (stable across runs) |
| Full suite `pytest tests/ -q` (4 runs sampled) | 1036–1037 passed; **4–11 failures, all pre-existing, all in other lanes' WIP** (see §4) |
| New regression tests | 1 (F-INT-009 core) + 15 (F-INT-011) + 1 end-to-end gate + 1 data-availability + updates |
| Syntax/import gate | `ast.parse` clean; no new imports of `openalgo`; no file over 1000 lines |

### 3.1 Failure provenance (verified, not assumed)

With **only my six files stashed** (clean baseline, other lanes' WIP intact),
the full suite still fails: **7 failed + 2 errors** (`test_paper_trading`,
`test_proposal_flow`, `test_auth_router`). With my changes restored the same
set of files fails (4–11 depending on run order). My files never appear in any
failure across four full-suite runs.

## 4. Pre-existing failures from concurrent lanes (out of scope)

The working tree carries uncommitted WIP from other Phase 4 lanes; the failing
tests belong to their files, not mine:

| Test | Root cause (other lane's WIP) |
|---|---|
| `test_paper_trading.py::test_market_order_fills` / `test_market_order_rejected_without_ltp` | `paper_trading.py` (F-EXEC-004 fix in progress) now rejects MARKET orders without LTP; the test file was not updated in lockstep — fails on baseline too |
| `test_proposal_flow.py::test_approve_paper_routes_to_paper_engine` | Cascade of the paper MARKET-order rejection → approval endpoint 400 |
| `test_auth_router.py::test_fyers_callback_*` | `auth_router.py` (F-AUTH-002 CSRF state cookie added) — callback tests not all cookie-aware; failure set shuffles per run order |
| `test_postback_router.py::test_postback_*` | `postback_router.py` (F-TERM-007 auth added) — some tests not updated; appeared in run 1 only (order-dependent) |

These are the responsibility of the owning lanes. Lane B's gate
("1012+ passed, 0 failed") cannot be green until those lanes land, but the
evidence above shows Lane B introduces zero failures.

## 5. Files touched (Lane B only)

- `src/shettyxtreme/integration/fyers/trading_adapter.py`
- `src/shettyxtreme/integration/fyers/session.py`
- `tests/integration/test_fyers_trading_adapter.py`
- `tests/integration/test_fyers_session.py`
- `tests/integration/test_fyers_data_adapter.py`
- `tests/execution/test_mode_router.py`
- `docs/superpowers/plans/2026-08-05-phase4-lane-b-findings.md` (this report)
