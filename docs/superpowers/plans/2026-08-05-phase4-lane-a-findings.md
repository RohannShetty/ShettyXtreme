# Phase 4 Lane A — Execution/Security Quick Wins (7 items)

**Date:** 2026-08-05
**Scope:** Phase 4 Lane A (quick wins after Phase 3 cockpit redesign) — 6 execution/security fixes + version alignment.
**Status:** Complete — all fixes implemented with regression tests. Full suite green.

---

## Deliverables

| Item | File | Change |
|---|---|---|
| F-TERM-007 | `src/shettyxtreme/terminal/api/postback_router.py` | Legacy `POST /api/postback/dhan` now requires `Authorization: Bearer <stored Fyers access token>` (401 without/wrong token) |
| F-AUTH-002 | `src/shettyxtreme/terminal/api/auth_router.py` | `start_auth` persists `state` in an HttpOnly/Lax cookie scoped to the callback path; `fyers_callback` rejects missing/mismatched state with 400 before the token exchange; cookie cleared on success (single-use) |
| F-EXEC-004 | `src/shettyxtreme/execution/paper_trading.py` | MARKET orders fill at last LTP from the data feed; no LTP → honest REJECTED (never a 0.0 fill) |
| F-CORE-003 | `src/shettyxtreme/execution/paper_trading.py` | `get_pnl()` no longer raises `AttributeError` on the first fill (`Fill` has no `pnl` field — `getattr` guard) |
| F-TERM-006 | `src/shettyxtreme/terminal/api/health_router.py` | Weekday before 09:15 now reports "Market opens at 09:15 today" instead of "opens tomorrow" |
| F-KNOW-005 | `src/shettyxtreme/execution/ledger.py` | `pair_fills` re-queues partial-fill remainders (FIFO preserved) instead of dropping them |
| Version drift | `__init__.py`, `app.py`, `pyproject.toml`, `web/package.json`, `CHANGELOG.md` | All five version files aligned to **0.13.0**; CHANGELOG entry for Phase 3 + Phase 4 Lane A |
| Wiring | `src/shettyxtreme/terminal/api/app.py` | Lifespan now binds the credential store to `postback_router.set_credential_store(store)` |

Collateral test updates (files whose assertions encoded the *old* buggy behavior):

- `tests/wave7/test_postback_router.py` — existing POST tests pass the bearer header; 4 new F-TERM-007 regressions.
- `tests/wave7/test_auth_router.py` — callback tests run the full start-auth → state → callback flow; 2 new F-AUTH-002 regressions.
- `tests/execution/test_paper_trading.py` — `test_market_order_fills` seeds an LTP first; 3 new regressions (F-EXEC-004 ×2, F-CORE-003 ×1).
- `tests/execution/test_trade_ledger.py` — 2 new F-KNOW-005 regressions.
- `tests/wave7/test_health_router.py` — **new file**, 8 `_get_market_session` cases (F-TERM-006).
- `tests/terminal/test_integration.py::test_oauth_callback_redirects_to_spa` — simulates the state cookie (F-AUTH-002).
- `tests/wave5/test_proposal_flow.py::test_approve_paper_routes_to_paper_engine` — seeds LTP so the paper MARKET fill is verifiable at the real price (F-EXEC-004).

---

## 1. F-TERM-007 — Auth-gate the legacy postback

### 1.1 The bug

`POST /api/postback/dhan` accepted any JSON payload and minted
`ORDER_UPDATED` events with no authentication. The ledger recorder treats
those events as real fills (`ORDER_UPDATED` with `filled_quantity > 0`), so
any process that could reach the port could inject phantom fills into the
paper ledger, P&L, and analytics — with no way to distinguish them from real
order-socket frames.

### 1.2 The fix

New FastAPI dependency `_require_auth` on the route:

- Reads the `Authorization` header; requires the `Bearer <token>` scheme.
- Compares the token against the terminal's own stored Fyers access token
  (`secrets.compare_digest`, constant-time) — the same credential that gates
  trading.
- 401 with a distinct detail for "not configured", "missing bearer token",
  and "invalid bearer token".
- Wired via `dependencies=[Depends(_require_auth)]`; the store reference is
  bound at lifespan (`postback_router.set_credential_store(store)`), so
  post-login token updates are seen live without re-wiring.

The order-socket path (`consume_order_message`) is internal (registered by
`terminal_init` as the Fyers order-WS callback) and is **not** gated.

### 1.3 Regression tests

- `test_postback_requires_auth` — no header → 401 "Missing bearer token".
- `test_postback_rejects_wrong_token` — wrong bearer → 401 "Invalid bearer token".
- `test_postback_rejects_missing_bearer_scheme` — bare token without the scheme → 401.
- `test_postback_401_does_not_publish_event` — a 401 never reaches the EventBus.
- Existing happy-path tests updated to send the valid bearer header.

---

## 2. F-AUTH-002 — Validate the OAuth `state` parameter

### 2.1 The bug

`start_auth` generated a random `state`, put it in the login URL, and returned
it in the response body — but never persisted it. `fyers_callback` accepted
the `state` query param and ignored it. Any callback with an `auth_code` and
`user_id` was exchanged against the terminal's stored app credentials: a
login-CSRF / login-injection vector (an attacker's crafted callback could
bind the terminal to the attacker's Fyers account).

### 2.2 The fix

- `start_auth` now persists the state in a cookie
  (`_fyers_oauth_state`, HttpOnly, `samesite="lax"`, 600 s TTL, scoped to
  `path="/auth/fyers/callback"`) — HttpOnly so page JS can't read it, Lax so
  the broker's cross-site redirect still carries it.
- `fyers_callback` validates before any exchange: cookie missing, `state`
  param missing, or `state != cookie` (constant-time compare) → **400
  "OAuth state mismatch"**. The check sits *before* the `try/except` so the
  400 is not swallowed by the broad exchange-failure handler (a real bug I
  hit while testing — the first implementation raised inside `try` and the
  `except Exception` converted it into a 307 redirect).
- On a successful exchange the cookie is deleted — the state is single-use.

### 2.3 Regression tests

- `test_fyers_callback_state_mismatch_rejected` — wrong state → 400, no token stored.
- `test_fyers_callback_missing_state_rejected` — callback without a prior
  start-auth (no cookie) → 400, no token stored.
- All existing callback success/failure tests now run the full
  credentials-save → start-auth → callback-with-real-state flow.

---

## 3. F-EXEC-004 — Paper MARKET orders fill at LTP, not 0.0

### 3.1 The bug

`_fill_order` used `order.price` as the fill price for every order type. A
MARKET order carries `price=0.0`, so paper MARKET fills recorded
`average_price=0.0` — poisoning paper P&L, position averages, the trade
ledger, and the shadow-learning data derived from them.

### 3.2 The fix

In `_fill_order`, MARKET orders resolve the fill price from the engine's LTP
cache (`_ltp_cache`, populated by `MARKET_DATA_TICK` events):

- LTP present → fill at the LTP; `order.price` is updated to the fill price
  so positions, `ORDER_FILLED`/`POSITION_CHANGED` broadcasts, and the order
  book all record the real price.
- No LTP (or non-positive) → the order is **rejected** with an explicit
  message ("no LTP available for <symbol>") and an `ORDER_REJECTED` event —
  never a fabricated 0.0 fill. Honesty over a fake fill.

Limit/SL fills are untouched (they already carry a real limit/trigger price).

### 3.3 Regression tests

- `test_market_order_fills_at_ltp_not_zero` — with LTP 18450.0, the fill
  records `average_price == 18450.0`, position `buy_avg == 18450.0`,
  `pnl == 0.0` (no phantom P&L), order-book average 18450.0.
- `test_market_order_rejected_without_ltp` — no feed → REJECTED, message
  mentions LTP, no positions, order stays in the book as REJECTED with
  `filled_quantity == 0`.
- `test_market_order_fills` (updated) — seeds the LTP before placing.

---

## 4. F-CORE-003 — Guard `get_pnl()` against the first-fill AttributeError

### 4.1 The bug

`get_pnl()` computed `sum(t.pnl or 0.0 for t in self._fills)`, but `Fill`
has no `pnl` field. With an empty `_fills` the sum is a no-op (0.0), so the
method looked fine — until the **first fill** made `_fills` non-empty, at
which point `t.pnl` raised `AttributeError` and every P&L read (positions
strip, analytics, risk checks) crashed.

### 4.2 The fix

`realised = sum(getattr(t, "pnl", None) or 0.0 for t in self._fills)` —
robust against fills that carry no P&L field. Realised P&L continues to
accumulate via closed-position `pos.pnl` in `_update_positions`, unchanged.

### 4.3 Regression test

- `test_get_pnl_after_first_fill` — fill one MARKET order (LTP seeded), then
  call `get_pnl()`: must not raise, returns a dict with `realised_pnl == 0.0`
  and `total_pnl` present.

---

## 5. F-TERM-006 — Weekday before the open says "today", not "tomorrow"

### 5.1 The bug

`_get_market_session` handled weekend / pre-open (09:00–09:15) / open /
post-close / else "Market opens tomorrow". A weekday *before* 09:00 (e.g.
08:00) fell into the final else branch and reported the market opens
**tomorrow** — wrong by a day.

### 5.2 The fix

A new branch before the tomorrow case: on a weekday (`weekday < 5`) before
the pre-open window (`time_decimal < 9.15`) → `("closed", "Market opens at
09:15 today", today 09:15 IST)`. Times after the close still say tomorrow;
Friday-after-close still jumps to Monday.

### 5.3 Regression tests

New `tests/wave7/test_health_router.py` (pure-function unit tests on
`_get_market_session`, 8 cases): 08:00 and 05:30 weekdays → opens today;
09:05 → pre_open; 10:00 → open; 15:45 → post_close; 17:00 Monday → tomorrow
(Tue); 17:00 Friday → Monday; Saturday 10:00 → Monday.

---

## 6. F-KNOW-005 — Re-queue partial-fill remainders in `pair_fills`

### 6.1 The bug

`pair_fills` FIFO-paired opposite-side fills by popping whole fills:
`qty = min(entry_qty, exit_qty)` consumed **both** fills even when one side
was only partially closed. A 75-qty BUY met by a 30-qty SELL paired 30 and
silently dropped the 45-qty remainder — understating realized P&L and losing
the open-position residue (a noted follow-up since v0.11.0).

### 6.2 The fix

Queues now hold `(fill, remaining_qty)` tuples. Each incoming fill drains
opposite-side queue entries in FIFO order, appending one pair per matched
chunk; when a queue entry's remainder exceeds the matched quantity it stays
**at the head** of the queue with the reduced remaining quantity; when the
incoming fill itself has leftover quantity it is queued (long or short) with
that remainder. NULL-symbol exclusion and cross-symbol isolation are
unchanged.

### 6.3 Regression tests

- `test_pair_fills_requeues_partial_remainders` — 75 BUY, 30 SELL, 45 SELL →
  two pairs (30 @ (110−100), 45 @ (112−100)), second pair's entry is the
  same original BUY.
- `test_pair_fills_remainder_carries_to_next_opposite` — 75 BUY, 100 SELL,
  25 BUY → 75 long close + 25 short close, second pair's entry is the SELL.
- Existing pairing tests (`long_and_short`, `per_session_summary_pairing`,
  NULL-symbol phantom-pair guard) unchanged and still green.

---

## 7. Version drift → 0.13.0

All five version files aligned to **0.13.0**:
`src/shettyxtreme/__init__.py`, `src/shettyxtreme/terminal/api/app.py`
(FastAPI `version=`), `pyproject.toml`, frontend
`src/shettyxtreme/terminal/web/package.json`, and a new `CHANGELOG.md`
v0.13.0 entry (Phase 3 cockpit redesign + Phase 4 Lane A fixes). No tests
(cosmetic), but the suite run double-checks nothing imports a pinned version.

---

## 8. Verification

| Gate | Result |
|---|---|
| Lane-A targeted tests (postback, auth, health, paper, ledger) | **66 passed** |
| Full suite `pytest tests/ -q --tb=short` | **1051 passed / 0 failed / 0 skipped** (baseline at Lane A start: 1016 passed) |
| New regression tests | 4 (F-TERM-007) + 2 (F-AUTH-002) + 3 (F-EXEC-004/F-CORE-003) + 2 (F-KNOW-005) + 8 (F-TERM-006) = **19 new**, all passing |
| `grep -r "import openalgo\|from openalgo" src/` | zero matches (unchanged) |
| File-size gate | no file over 1000 lines (max touched ≈ 277 in `paper_trading.py`) |
| `ast.parse` on all touched source files | clean |

### 8.1 Note on the shared working tree

The tree carries uncommitted WIP from the parallel lanes (B-int, C-intel,
D-front, E-test). Two full-suite failures observed mid-lane were caused by
**my own** behavior changes racing my test updates (Lane B's report lists them
as "other lanes' WIP"): `test_oauth_callback_redirects_to_spa` (state gate
now 400s a stateless callback) and `test_approve_paper_routes_to_paper_engine`
(paper MARKET now rejects without LTP). Both are resolved by the collateral
test updates above — final suite is 1051/0/0 with all lanes' work present.

## 9. Files touched (Lane A only)

- `src/shettyxtreme/terminal/api/postback_router.py`
- `src/shettyxtreme/terminal/api/auth_router.py`
- `src/shettyxtreme/terminal/api/app.py`
- `src/shettyxtreme/terminal/api/health_router.py`
- `src/shettyxtreme/execution/paper_trading.py`
- `src/shettyxtreme/execution/ledger.py`
- `src/shettyxtreme/__init__.py`, `pyproject.toml`, `src/shettyxtreme/terminal/web/package.json`, `CHANGELOG.md`
- `tests/wave7/test_postback_router.py`, `tests/wave7/test_auth_router.py`, `tests/wave7/test_health_router.py` (new)
- `tests/execution/test_paper_trading.py`, `tests/execution/test_trade_ledger.py`
- `tests/terminal/test_integration.py`, `tests/wave5/test_proposal_flow.py`
- `docs/superpowers/plans/2026-08-05-phase4-lane-a-findings.md` (this report)
