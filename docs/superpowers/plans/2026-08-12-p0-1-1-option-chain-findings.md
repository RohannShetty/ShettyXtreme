# P0-1.1 Findings — Option Chain Completely Blank (ShettyXtreme v0.14.0)

**Date:** 2026-08-12 · **Severity:** P0 blocker · **Status:** Root cause identified — see "Fix approach"

## TL;DR

The blank chain is **not** a symbol-resolution problem and **not** an instrument-master problem
(NIFTY/BANKNIFTY/FINNIFTY all resolve correctly against a healthy, fresh master). It is a
**two-layer silent-error-propagation defect** layered on top of an upstream Fyers data failure
(most likely missing Data-API entitlement, Fyers 403/-373 — the Dhan-806 twin):

1. **`FyersDataAdapter.get_option_chain()`** catches *every* `FyersError` — including
   `FyersDataEntitlementError` (403/-373), `FyersTokenExpired`, `FyersRateLimitError`,
   `FyersAPIError` — and returns `{}` (`data_adapter.py:442-444`).
2. **`intelligence_router._fetch_chain_with_spot()`** then sees `result.get("s") != "ok"`
   and silently returns `([], None)` (`intelligence_router.py:188-189`). Its `entitlement is True`
   503 branch is **dead code for Fyers** — the adapter never returns that key.
3. The router returns **200 `{"underlying":"NIFTY","expiry":"","contracts":[]}`** →
   `ChainGrid.svelte:228` sets `contracts = []` → grid renders "No chain data" with **no error text**.

Runtime evidence (see §6) shows the v0.14.0 release also shipped a **500 crash** on this exact
endpoint (`ValueError: expiry is required for the options chain`) — every request 500'd. That
specific crash was fixed post-release in commit `d92243f`, but **without a regression test**, and
the silent-empty swallows remain, so the endpoint now degrades a Fyers failure into a 200-empty
(i.e. the "completely blank" symptom the P0 describes).

---

## 1. Frontend trace — `ChainGrid.svelte`

**File:** `src/shettyxtreme/terminal/web/src/components/ChainGrid.svelte`

| Line | What |
|------|------|
| 21–34 | `Contract` type: `strike, option_type, ltp, iv, delta, gamma, theta, vega, oi, volume, bid, ask` |
| 36–40 | `OptionsResponse` type: `{ underlying: string; expiry: string; contracts: Contract[] }` |
| 50 | `REFRESH_MS = 15_000` — quiet 15 s poll |
| 215–216 | **The call:** `get<OptionsResponse>(\`/api/intelligence/options?symbol=${sym}&expiry=${exp}\`)` |
| 227–228 | `contracts = resp.contracts ?? []` — **an empty/absent `contracts` array renders a blank grid** |
| 229–238 | Resolved-expiry convergence loop — fires only if `resp.expiry` is truthy (it never is, see §2 defect D2) |
| 244–256 | `refreshSilently()` — the 15 s poll **swallows all errors** (line 253 `catch {}`) |
| 355–357 | Error text rendered only when `load()` itself throws (non-2xx) |
| 424–426 | Empty state: `No chain data. Check the symbol or start the data pipeline.` |

**Supporting:** `src/shettyxtreme/terminal/web/src/lib/api.ts:54-56` — `request()` throws only on
`!resp.ok`; a **200 with empty contracts is indistinguishable from success** and renders blank.

**Frontend expectation:** `contracts: Contract[]` with ≥1 row. It never shows the backend's
failure because the backend never fails loudly — it returns 200-empty.

---

## 2. Backend router trace — `GET /api/intelligence/options`

**File:** `src/shettyxtreme/terminal/api/intelligence_router.py`

| Line | What |
|------|------|
| 345–367 | `get_options()` handler |
| 352–359 | Calls `_fetch_chain_with_spot(request.app.state.data_adapter, symbol, expiry)`; catches only `DataEntitlementError` → 503 and `DataAdapterUnavailable` → 503 |
| 181–185 | `_fetch_chain_with_spot` → `await adapter.get_option_chain(underlying=symbol, expiry=expiry or "", strike_count=50)` |
| 186–187 | `if result.get("entitlement") is True: raise DataEntitlementError(...)` — **dead path for Fyers** (adapter never emits `entitlement`); only exercised by test fakes (`EntitledAdapter`, `_FakeAdapter`) |
| 188–189 | **`if result.get("s") != "ok": return [], None`** — converts any non-ok body (incl. `s:"error"` with Fyers' `code`/`message`) into a silent empty chain |
| 190–194 | `s=="ok"` → `option_chain` list + spot |
| 360 | `_enrich_chain(chain, spot, tte=...)` — pure-Python greeks, guarded (`iv > 0 and strike > 0`) |
| 363–366 | Caches raw rows in `app.state.options_chain` (feeds research `options_posture`) |
| 367 | `return OptionsChainResponse(underlying=symbol, expiry=expiry or "", contracts=contracts)` |

**Defect D1 (the P0):** line 188-189 silently returns an empty chain on every non-ok Fyers
response. **Defect D2 (secondary):** line 367 echoes the *requested* `expiry` (empty) rather than
the resolved expiry Fyers used — the frontend's convergence loop (ChainGrid.svelte:229-238) and
the expiry dropdown never populate, and the 15 s poll keeps re-requesting "nearest expiry".

**Response model:** `src/shettyxtreme/terminal/api/models.py:51-70` — `OptionsChainItem`
(`strike: float`, ...), `OptionsChainResponse` (`underlying`, `expiry`, `contracts: list = []`).

---

## 3. Fyers adapter trace — `FyersDataAdapter.get_option_chain()`

**File:** `src/shettyxtreme/integration/fyers/data_adapter.py:425-444`

```python
425:    async def get_option_chain(self, underlying: str, expiry: str, strike_count: int = 50) -> dict:
434:        ticker = self._resolve_symbol(underlying, "NSE_FNO")
435:        ts_param = f"&timestamp={_expiry_epoch(expiry)}" if expiry else ""   # ← v0.14.0 guard (d92243f)
436:        try:
437:            return await self._client.get(
438:                f"/data/options-chain-v3?symbol={ticker}"
439:                f"&strikecount={int(strike_count)}"
440:                f"{ts_param}&greeks=1"
441:            )
442:        except FyersError as exc:
443:            logger.warning("Fyers options chain failed for %s: %s", ticker, exc)
444:            return {}        # ← SWALLOWS FyersDataEntitlementError / FyersTokenExpired / rate-limit / API error
```

- **Symbol resolution** (`data_adapter.py:128-151`): `_resolve_symbol("NIFTY", "NSE_FNO")` →
  `master.search("NIFTY")` → first `INDEX` row → `NSE:NIFTY50-INDEX`. Verified against the live
  SQLite master (§4) — **works for NIFTY, BANKNIFTY (`NSE:NIFTYBANK-INDEX`), FINNIFTY
  (`NSE:FINNIFTY-INDEX`), and equities** (e.g. IRCTC → `NSE:IRCTC-EQ`). A bare `NSE:NIFTY50-INDEX`
  ticker (contains `:`) passes through unchanged.
- **Weekly vs monthly expiry:** for the *chain* request the expiry is passed as a raw
  `timestamp=` epoch (`_util.expiry_epoch`, `_util.py:118-136`); weekly/monthly encoding only
  matters in `symbols.to_fyers()` for *individual contract* construction, which the chain path
  never does. No defect here.
- **Empty expiry (the v0.14.0 fix):** `data_adapter.py:435` omits `timestamp` when expiry is
  empty — Fyers returns the nearest expiry. **This guard is correct in the current tree**, but it
  shipped (commit `d92243f`) **without a regression test** (see §7), and the 500 it fixes is
  exactly what server.err shows every request hitting before the commit.
- **403/-373 entitlement:** raised as `FyersDataEntitlementError` by the transport
  (`client.py:228-233`, HTTP 403 or body `code == -373`) — then **swallowed at line 443**.
- **lot_size / strike_interval:** the chain endpoint does **not** query the instrument master for
  lot size or strike interval at all — they are only used by the trading adapter. The master has
  them (NIFTY weekly lot = 65, tick 0.05, §4) but they are irrelevant to this P0.

---

## 4. Instrument-master validation — NOT the failure

**File:** `src/shettyxtreme/integration/fyers/instrument_master.py` (lookup 408-432, search 434-484)
**File:** `src/shettyxtreme/integration/fyers/symbols.py:292-295` (exact-match `-300` gate)

The `-300` exact-match gate (`symbols.py:292-295`, `master.lookup(ticker)` → raises
`SymbolNotFoundError`) applies **only** inside `to_fyers()` for constructed derivative tickers.
The chain path never reaches it: `_resolve_symbol()` short-circuits through `master.search()`
(`data_adapter.py:139-150`) which returns index rows directly. `to_fyers()` is only the fallback
when no master is bound.

Verified against the live DB (`data/fyers_instruments.db`, 163,722 rows, refreshed
`2026-08-11T09:51:58Z`):

```
('NSE:NIFTY50-INDEX',   'NIFTY',     'NSE', 'INDEX', lot=0, tick=0.05)   ✓ search("NIFTY") finds it
('NSE:NIFTYBANK-INDEX', 'BANKNIFTY', 'NSE', 'INDEX', ...)                ✓
('NSE:FINNIFTY-INDEX',  'FINNIFTY',  'NSE', 'INDEX', ...)                ✓
NIFTY weekly options exist: NSE:NIFTY2681129700CE, expiry 2026-08-11, lot 65, tick 0.05
```

**Verdict: the exact-match gate is NOT rejecting valid symbols.** (If the master were empty,
`master.search()` would return `[]` and `to_fyers(..., master=...)` would raise
`SymbolNotFoundError` → unhandled 500 — a real risk to guard against, but not the current state.)

---

## 5. Data entitlement — YES, the adapter swallows it (twice)

The adapter's own docstring (`data_adapter.py:13-15`) promises: "Entitlement ... surfaces as
`FyersDataEntitlementError` from the transport; live-subscribe errors propagate so the caller can
gate on them." **`get_option_chain()` violates that contract** — it catches the error and returns
`{}`. The router's `entitlement is True` branch (`intelligence_router.py:186-187`) was built for
the Dhan adapter and is tested via fakes (`tests/wave3/test_api.py:274-292`,
`tests/terminal/test_options_chain_prime.py:85-92`), but no real Fyers code path ever produces it.

Result: an entitlement-less (or expired-token, or rate-limited) account renders a **completely
blank chain with no error**, exactly matching the P0. The health strip's entitlement surfacing
(`terminal/projections.py:405-418`, `getattr(adapter, "entitlement_error", False)`) also can't
fire — `FyersDataAdapter` has no such attribute.

---

## 6. Runtime evidence (server.err / server.log, 2026-08-06)

```
GET /api/intelligence/options?symbol=NIFTY          → 500 Internal Server Error   (×many)
GET /api/intelligence/options?symbol=NIFTY&expiry=  → 500 Internal Server Error   (×many)
GET /api/intelligence/options?symbol=IRCTC&expiry=  → 500 Internal Server Error
GET /api/intelligence/options?symbol=BANKNIFTY...   → 500 Internal Server Error
GET /api/intelligence/options?symbol=FINNIFTY...    → 500 Internal Server Error

Traceback (most recent call last):
  File "...\intelligence_router.py", line 353, in get_options
    chain, spot = await _fetch_chain_with_spot(
  File "...\intelligence_router.py", line 181, in _fetch_chain_with_spot
    result = await adapter.get_option_chain(
  File "...\integration\fyers\data_adapter.py", line 434, in get_option_chain
    raise ValueError("expiry is required for the options chain")
ValueError: expiry is required for the options chain
```

- The 500s are `_expiry_epoch("")` raised on the frontend's empty `expiry` param — **every**
  symbol, every request. This is the v0.14.0 release regression; fixed in commit `d92243f`
  (2026-08-06 17:42) by the guard at `data_adapter.py:435`, but the server that produced these
  logs ran the pre-fix code.
- `Fyers batch quotes failed (3 symbols): Fyers API error` — `/data/quotes` failing too,
  consistent with a **missing Data-API entitlement** (403/-373, the account-wide gate) rather than
  a chain-specific defect. With the post-fix code, that same failure now surfaces as a 200-empty
  chain — the blank-grid P0.
- Logs are from 08-06; the fix is in the committed tree (clean working tree), so a restart picks
  it up — but the entitlement/error swallowing (§3, §5) is still live code.

---

## 7. Classification

| Question | Answer |
|----------|--------|
| Failure point | **Backend error propagation** (`data_adapter.py:442-444` + `intelligence_router.py:186-189`), preceded by the (now-fixed) `_expiry_epoch("")` 500. Frontend is correct. Symbol resolution is correct. Instrument master is correct. |
| Kind | **Wiring / error-propagation defect**, masking an underlying **data-availability** condition (Fyers Data-API entitlement 403/-373 or expired token — indistinguishable because both are swallowed identically). The original v0.14.0 500 was a **computation** bug (`_expiry_epoch` on empty string). |
| Symptom path | Fyers error → `{}` → `s != "ok"` → `([], None)` → `contracts: []` → 200 → blank grid + "No chain data" + silent 15 s poll retries forever |

---

## 8. Proposed fix approach (algorithm, not code)

1. **Stop swallowing in the adapter.** In `get_option_chain()`, catch `FyersDataEntitlementError`
   (and `FyersTokenExpired`) separately and **re-raise or return `{"entitlement": True, "s":
   "error", "message": ...}`** — the dict shape the router already understands. Only the generic
   `FyersError` remainder may degrade to `{}`/`[]`, and only because the router must stay non-5xx
   for "no adapter" cases.
2. **Never convert a non-ok response into a silent empty chain in the router.** In
   `_fetch_chain_with_spot()`: if `entitlement` is True **or** the body code is `-373` → raise
   `DataEntitlementError` (→ 503, message already exists: `_ENTITLEMENT_MSG`). If `s != "ok"` for
   any other reason → raise a structured error carrying Fyers' `code`/`message` (503 or 502), or
   at minimum log at error level with the body. The **only** legitimate empty chain is
   `s == "ok"` with `option_chain == []`.
3. **Frontend already handles the result:** `load()`'s error path (ChainGrid.svelte:355-357)
   renders the 503 detail text; no frontend change required for the P0. Optionally distinguish
   "no data yet" from "entitlement missing" in the empty-state copy.
4. **Add the missing regression tests:**
   - adapter: `get_option_chain("NIFTY", "")` → URL contains **no** `timestamp=` param (the
     guard that shipped untested in d92243f);
   - adapter raising `FyersDataEntitlementError` → router returns **503 with the entitlement
     detail** (not 200-empty);
   - router with `{"s": "error", "code": -373}` body → 503;
   - router with `{"s": "ok", "option_chain": []}` → 200 empty (the legitimate case).
5. **Fix D2 (chain UX):** have the endpoint return the resolved expiry (or add an `expiries`
   list) so ChainGrid's convergence loop populates the expiry dropdown instead of echoing `""`.
6. **Hardening:** wrap `_resolve_symbol`'s `SymbolNotFoundError` (empty-master case) in the
   router → 503 "unknown symbol / master unavailable" instead of an unhandled 500.

---

## 9. Constructed curl trace

```bash
# 1) Frontend → backend — the request the grid makes on load and every 15 s
curl -i "http://127.0.0.1:8000/api/intelligence/options?symbol=NIFTY&expiry="

#    Pre-fix v0.14.0 runtime (what server.err shows):
#    HTTP/1.1 500 Internal Server Error
#    {"detail":"Internal Server Error"}        ← ValueError: expiry is required for the options chain

#    Current tree, Fyers-side failure (entitlement / token / API error):
#    HTTP/1.1 200 OK
#    {"underlying":"NIFTY","expiry":"","contracts":[]}   ← "completely blank" — error hidden

# 2) Backend → Fyers upstream (what the adapter issues; Authorization is app_id:access_token)
curl -i -H "Authorization: <APP_ID>:<ACCESS_TOKEN>" \
  "https://api-t1.fyers.in/api/v3/data/options-chain-v3?symbol=NSE:NIFTY50-INDEX&strikecount=50&greeks=1"

#    Expected failure modes:
#    HTTP 403 {"s":"error","code":-373,...}     → FyersDataEntitlementError → swallowed at data_adapter.py:443
#    HTTP 200 {"s":"error","code":-373,...}     → FyersDataEntitlementError (client.py:228) → swallowed
#    HTTP 200 {"s":"error","code":-300,...}     → returned dict → router s!="ok" → silent empty
#    HTTP 200 {"s":"ok","option_chain":[...]}   → renders correctly (the only happy path)
```

---

## Appendix — key file:line index

| Component | Location |
|-----------|----------|
| ChainGrid call + render | `terminal/web/src/components/ChainGrid.svelte:216, 228, 355-357, 424-426` |
| `get()` non-2xx handling | `terminal/web/src/lib/api.ts:54-56` |
| `GET /options` handler | `terminal/api/intelligence_router.py:345-367` |
| Silent-empty conversion | `terminal/api/intelligence_router.py:186-189` |
| Dead `entitlement` 503 branch | `terminal/api/intelligence_router.py:186-187` |
| Adapter swallow | `integration/fyers/data_adapter.py:442-444` |
| Empty-expiry guard (v0.14.0 fix) | `integration/fyers/data_adapter.py:435` (commit `d92243f`) |
| Symbol resolution | `integration/fyers/data_adapter.py:128-151` |
| Entitlement classification | `integration/fyers/client.py:216-240` (`-373` at 41, 228) |
| `-300` exact-match gate | `integration/fyers/symbols.py:292-295` |
| Master search/lookup | `integration/fyers/instrument_master.py:408-432, 434-484` |
| `expiry_epoch` (empty raises) | `integration/fyers/_util.py:118-136` (raise at 130) |
| Bootstrap wiring (adapter + master) | `terminal/api/terminal_init.py:136-163`; `instrument_init.py:11-31` |
| Chain prime (startup) | `terminal/api/intelligence_router.py:197-233` |
| Tests pinning the (fake) entitlement contract | `tests/wave3/test_api.py:274-292`; `tests/terminal/test_options_chain_prime.py:85-92, 126-132` |
| Adapter URL test (non-empty expiry only) | `tests/integration/test_fyers_data_adapter.py:523-536` |
