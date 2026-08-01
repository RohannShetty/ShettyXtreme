# BRIEF: DhanHQ-py Upstream vs Our Pinned 2.2.0

**Status:** Research brief · **Date:** 2026-08-01 · **Owner:** ShettyXtreme platform team
**Purpose:** Version delta, auth reality check, feed protocol, historical/option-chain endpoints, and upgrade recommendations for our `dhanhq` pin.
**Sources read:** Upstream mirror `references/upstream/dhanhq-py` (git main, shallow-cloned then deepened: HEAD `1670f81`, 2026-07-07) and local SDK mirror `D:\DhanHQ-py-2.2.0` (matches PyPI `dhanhq==2.2.0`, published 2026-04-24). Also PyPI JSON metadata for `dhanhq`, and our own adapters `src/shettyxtreme/integration/dhan/{trading,data}_adapter.py`.

---

## 1. Version Delta: upstream (2.3.0rc1+) vs our 2.2.0

**Our pin:** `pyproject.toml` declares `dhanhq>=0.1.0` (very loose). Working tree against the SDK assumes 2.2.0 semantics (`D:\DhanHQ-py-2.2.0` = PyPI 2.2.0, sdist 44814 bytes, uploaded 2026-04-24).

**Upstream state:** `main` is **2.3.0rc1** (setup.py `VERSION = '2.3.0rc1'`, PEP 440 pre-release; requires `pip install --pre` or explicit pin) + 1 post-release commit. Git log between v2.2.0 (`ff2ea96`) and HEAD:

| Commit | Date | What |
|---|---|---|
| `06c830c` | 2026-04-24 | v2.2.0 - default (matches PyPI release) |
| `958d339` | 2026-05-23 | Avoid deprecated UTC timestamp conversion in feeds |
| `1abc247` | 2026-07-07 | Release v2.3.0-rc1: Conditional Orders, Global Stocks, P&L Exit |
| `1670f81` | 2026-07-07 | Merge PR #137 (fix-133 utcfromtimestamp deprecation) |

**Full diffstat 2.2.0 -> HEAD:** 29 files, +1349/-155. Key changes:

### New modules (additive, no impact on our paths)
- `_conditional_order.py` (89 lines): alert-based conditional orders — `place/get/modify/cancel_conditional_order` hitting `/alerts/orders` (+ `/alerts/orders/{id}`). NEW feature.
- `_global_stocks.py` (200 lines): US stocks — `place_global_order`, order list/by id, modify, trades, holdings, fund limit, market status, charge/margin estimates. NEW feature.
- `global_stocks_feed.py` (381 lines): separate WebSocket feed for US stocks at `wss://global-stocks-api-feed.dhan.co/`, JSON subscribe with `requestCode` 15/17 (trade/OHLC), binary packets with own MsgCode set (1/3/29/32/33/36/50). NEW feature, unrelated to our NSE feed.

### Behavior changes that touch files we use
- `marketfeed.py`: only substantive change is `utc_time()` from deprecated `datetime.utcfromtimestamp()` to `datetime.fromtimestamp(epoch, timezone.utc)` (Python 3.12 deprecation fix; same for `fulldepth.py`). Dead `on_connection_opened` removed. No protocol change.
- `fulldepth.py`: `on_ticks` callback support; `asyncio.get_event_loop()` -> `new_event_loop()`; fixed disconnect-code unpack index (was `[0][5]` out of range on a 10-byte `<BHBIH` packet, now `[0][4]`); `get_instrument_data` now returns a list of results instead of None.
- `_order.py` (`place_order`/`modify_order`): NEW `amo_time` param (`'OPEN' | 'OPEN_30' | 'OPEN_60'`), validated only when `after_market_order=True`, sent as `amoTime` only for AMO orders. Backwards compatible (default `'OPEN'`, param already existed in 2.2.0 signature — 2.2.0 just never forwarded it; upstream now sends it).
- `_portfolio.py`: NEW `exit_all_positions()` (DELETE `/positions`).
- `_funds.py`: NEW `margin_calculator_multi()` (POST `/margincalculator/multi`).
- `_trader_control.py`: NEW `set_pnl_exit` / `get_pnl_exit` / `stop_pnl_exit` (POST/GET/DELETE `/pnlExit`).
- `_security.py`: NEW `GLOBAL_STOCKS_CSV_URL` + `fetch_global_security_list()`. Existing `fetch_security_list` unchanged.
- `_forever_order.py`: **BREAKING (minor):** removed `symbol`/`tradingSymbol` params from `place_forever`. We do not use forever orders.
- `dhanhq.py` / `__init__.py`: dhanhq class now also inherits `ConditionalOrder` and `GlobalStocks`; new `INX = 'INX_EQ'` exchange constant; exports `ConditionalOrder`, `GlobalStocks`, `GlobalStocksFeed`.
- `setup.py`: version 2.3.0rc1, `python_requires='>=3.10'`, Dev Status classifier Beta. Dependencies unchanged (`pandas`, `requests`, `websockets`, `pyOpenSSL`).
- `LICENSE`: Copyright 2025 -> 2026. Still MIT.

**Auth, token endpoints, feed protocol, historical data, option chain: IDENTICAL between 2.2.0 and upstream** (`auth.py`, `dhan_context.py`, `dhan_http.py`, `_historical_data.py`, `_option_chain.py`, `_market_feed.py`, `orderupdate.py` all byte-identical modulo copyright headers).

**PyPI reality:** latest published stable = **2.2.0** (2026-04-24); `2.3.0rc1` is a pre-release (2026-07-07). A `dhanhq>=0.1.0` pin will NOT pull rc1 without `--pre`, so our runtime is effectively frozen at 2.2.0 today.

---

## 2. Auth Reality Check (2.2.0 == upstream)

Three flows exist, all in `auth.py` (`DhanLogin`), unchanged since our pin:

1. **OAuth consent flow (app-level, partner/self):** `generate_login_session(app_id, app_secret)` -> POST `https://auth.dhan.co/app/generate-consent`, opens browser, returns `consentAppId`; then `consume_token_id(token_id, app_id, app_secret)` -> GET `auth.dhan.co/app/consumeApp-consent?tokenId=...` returns access token. Requires app credentials.
2. **PIN + TOTP flow (self/primary credential):** `generate_token(pin, totp)` -> POST `https://auth.dhan.co/app/generateAccessToken?dhanClientId=...&pin=...&totp=...` (query params, no app_id/app_secret). Returns `accessToken`. This is our primary (and fallback-data) path.
3. **Token renewal:** `renew_token(access_token)` -> GET `https://api.dhan.co/v2/RenewToken` with `access-token` + `dhanClientId` headers. NOTE: this is a client-side helper only — the SDK does NOT auto-renew anywhere.

**One token for both trading REST and api-feed.dhan.co WS: CONFIRMED.** `DhanContext(client_id, access_token)` builds one `DhanHTTP` (header `access-token` + `client-id`, base `https://api.dhan.co/v2`) and passes the SAME token to `MarketFeed`, which in v2 connects to `wss://api-feed.dhan.co?version=2&token={access_token}&clientId={client_id}&authType=2`. No separate data token exists in the SDK.

**Implication for our single-primary + fallback model:** The SDK itself has no notion of "trading token" vs "data token". Our adapter split (trading vs data credentials) is a *product/entitlement* decision at Dhan's side (error 806 on the WS feed = the client's Data API subscription entitlement), not an SDK constraint. Our model maps cleanly:
- Primary: OAuth/PIN-TOTP `accessToken` for `DhanTradingAdapter` REST.
- Fallback data: a second `generate_token(pin, totp)` token (own entitlement) for `DhanDataAdapter`.
- If we ever need it, `DhanLogin.renew_token()` exists and is unchanged; nothing in 2.3.0rc1 alters these flows or endpoint URLs.

---

## 3. Feed Protocol (2.2.0 == upstream; what DhanDataAdapter must handle)

From `marketfeed.py` (unchanged between versions except the UTC fix):

- **Endpoint:** `wss://api-feed.dhan.co` ; v2 = `?version=2&token=<access_token>&clientId=<client_id>&authType=2`. v1 (binary auth packet, request code 11) still supported but discouraged; we use v2.
- **Subscription request codes (v2 JSON):** `Ticker=15`, `Quote=17`, `Full=21`. `Depth=19` is v1-only — v2 rejects it (`validate_and_process_tuples` raises ValueError if type not in [15,17,21]).
- **Message shape:** `{"RequestCode": int, "InstrumentCount": n, "InstrumentList": [{"ExchangeSegment": "NSE_EQ", "SecurityId": "1333"}]}` — batched 100 per message.
- **Unsubscribe:** same shape with `RequestCode + 1` (16/18/22); SDK also supports `subscribe_symbols`/`unsubscribe_symbols` live on an open socket.
- **Disconnect:** v2 sends `{"RequestCode": 12}` then a binary header packet, then closes.
- **Server disconnect/error packet:** first byte `50`; unpack `<BHBIH` (10 bytes); code at index 4:
  - `805` — active websocket connections exceeded
  - `806` — **Subscribe to Data APIs to continue** (our entitlement error)
  - `807` — access token expired
  - `808` — invalid client ID
  - `809` — authentication failed
  `server_disconnection()` prints a message and calls `on_close` — the SDK does NOT raise, does NOT distinguish 806 from transient drops, and does NOT stop the reconnect loop.
- **Reconnection behavior:** `_run_async()` loops: if ws closed, `await asyncio.sleep(1)` then `connect()` again. `connect()` re-subscribes all instruments. There is NO exponential backoff, NO cap on retries, NO error-code-aware retry policy. On 806, the SDK would reconnect+resubscribe forever every ~1s, hitting the entitlement wall each time.
- **Inbound binary parse:** first byte dispatch: 2=ticker, 3=depth, 4=quote, 5=OI, 6=prev close, 7=status, 8=full, 50=disconnect. (Note: our `data_adapter.py` docstring lists "41=OHLC, 51=market depth" — those codes do not exist in this SDK; the comment is stale.)
- **IMPORTANT adapter-side mismatch:** our `DhanDataAdapter.subscribe_ticks/subscribe_bars` build instrument tuples with `FEED_CODE_TICKER=2` and `FEED_CODE_FULL_QUOTE=8` as the *request* code, but v2 only accepts 15/17/21. This would raise `ValueError("Invalid request mode for v2...")` inside `validate_and_process_tuples` at runtime. The unit tests mock `MarketFeed` entirely, so this has not surfaced. MUST be fixed: use `MarketFeed.Ticker=15` / `MarketFeed.Full=21` (or Quote=17).

**What DhanDataAdapter must handle (beyond the SDK):**
1. Map 806 to "Data-API entitlement missing" state; STOP reconnecting (SDK will loop otherwise) and surface a health/status error.
2. 807 (token expired) -> trigger our token refresh path (SessionHealth-style), not blind reconnect.
3. Backoff + jitter on reconnect for 805/transient drops; resubscribe is handled by `connect()` but only if we call it.
4. Distinguish server-initiated close (codes 805-809, first byte 50) from local close so we don't treat entitlement failures as flapping.

---

## 4. Historical Data + Option Chain (no changes vs 2.2.0)

Byte-identical files upstream vs our pin:
- `_historical_data.py`: `intraday_minute_data` (POST `/charts/intraday`, intervals 1/5/15/25/60, `oi` flag), `historical_daily_data` (POST `/charts/historical`, `expiry_code` 0-3), `expired_options_data` (POST `/charts/rollingoption`, validations on interval/expiry_flag/drv_option_type/required_data). No rate-limit handling, no pagination params in the SDK.
- `_option_chain.py`: `option_chain` (POST `/optionchain`, payload `UnderlyingScrip`/`UnderlyingSeg`/`Expiry`) and `expiry_list` (POST `/optionchain/expirylist`). Unchanged.
- `_market_feed.py` REST endpoints: `ticker_data` (POST `/marketfeed/ltp`), `ohlc_data` (POST `/marketfeed/ohlc`), `quote_data` (POST `/marketfeed/quote`). Unchanged.

Rate limits / pagination are NOT documented in the SDK code or README (Dhan enforces server-side; `get_trade_history` in `_statement.py` does take a `page_number`, but that's outside our current adapter usage). Nothing in 2.3.0rc1 touches these surfaces, so no adapter changes needed here on upgrade.

---

## 5. Recommendations

**License: CONFIRMED MIT.** `LICENSE` = MIT License, Copyright (c) 2026 Dhan; setup.py `license='MIT LICENSE'`. Safe to vendor/upgrade.

**Bump recommendation: DO NOT bump yet — stay pinned at 2.2.0 stable.**
- Upstream `main` is only `2.3.0rc1` (pre-release). Our `dhanhq>=0.1.0` pin already resolves to 2.2.0 for normal installs; keep it that way.
- 2.3.0rc1's only change touching our surfaces is the Python 3.12 `utcfromtimestamp` deprecation fix — nice-to-have but not urgent (we run >=3.11; warning appears only on 3.12+).
- When `2.3.0` stable ships, upgrading is LOW RISK for us: feed protocol, auth, historical, option chain, REST market feed are all unchanged. The only breaking change (`place_forever` signature) does not affect us.
- Recommend tightening the pin to `dhanhq>=2.2.0,<2.3.0` (or `==2.2.0`) in `pyproject.toml` so future pre-releases/rcs can never sneak in, and add a comment that the mirror at `D:\DhanHQ-py-2.2.0` is the reference implementation.

**Upstream changes that MUST trigger adapter updates (watch list):**
1. Any change to `marketfeed.py` request codes / WS URL / authType scheme (currently stable since v2.1.0).
2. Any change to disconnect packet format or 806/807 semantics (we key entitlement detection off these).
3. `DhanHTTP` response envelope changes (`status`/`remarks`/`data` dict shape) — our adapters parse `result["data"]` and `result.get("status")` directly.
4. `auth.py` token flow changes (generateAccessToken / RenewToken / consent URLs) — our SessionHealth + fallback logic depends on them.
5. `_historical_data.py` / `_option_chain.py` payload or endpoint changes (unchanged for 2 versions now).

---

## 6. Gaps the SDK Still Has (we own these in our adapters)

1. **No auto token refresh.** `DhanLogin.renew_token()` exists but nothing calls it; `DhanHTTP` sends whatever token it was constructed with, forever. Tokens expire ~3AM IST daily. -> `SessionHealth` (trading) and our data-side token handling must keep doing this. (Note: `SessionHealth._init_context` currently rebuilds DhanContext with the SAME stored token — a true refresh requires calling `DhanLogin.renew_token`/`generate_token` to obtain a NEW token; worth tightening.)
2. **No retry / no backoff on REST.** `DhanHTTP._send_request` catches ALL exceptions and returns `{'status':'failure','remarks':str(e)}` — no retries, no 429/5xx handling, no timeouts beyond the 60s default. -> our adapters must wrap calls with their own retry policy.
3. **No reconnect policy on the feed.** 1-second blind reconnect loop; no backoff/jitter; no error-code classification; on 806/807 it loops forever. -> DhanDataAdapter must own disconnect-code handling (see section 3) and cap/backoff reconnects.
4. **No rate-limit awareness or pagination helpers** for historical/option-chain/trade-history calls. -> our polling/backfill code must self-throttle.
5. **No staleness/heartbeat detection** on the feed — `MarketFeed` has no ping/watchdog. -> our 30s staleness detector in `DhanDataAdapter` is the right layer.
6. **Thread/event-loop friction:** `MarketFeed` creates its own `asyncio.new_event_loop()` and runs blocking `run_forever()`; callbacks fire on that loop. Our adapter bridges via `run_in_executor` — keep that bridge, don't call `get_data()` from the asyncio loop thread directly.
7. **Stale docstring in our adapter:** feed-code comment (41/51) doesn't match the SDK; fix alongside the request-code bug (15/17/21) noted in section 3.

---

**Bottom line:** Stay on 2.2.0; 2.3.0rc1 changes nothing in our integration surface except the 3.12 deprecation fix. The real work is adapter-side: correct our WS request codes (2/8 -> 15/21), add disconnect-code-aware reconnect policy (especially 806 entitlement), and keep owning token refresh, retry, and staleness.

---

## 7. Adapter Surface Mapping (what our code touches in the SDK)

Exact call sites in our tree and the SDK symbols they depend on — this is the upgrade test matrix for any future bump:

| Our file | SDK imports | SDK symbols used | 2.3.0rc1 impact |
|---|---|---|---|
| `integration/dhan/trading_adapter.py` | `DhanContext`, `dhanhq` | `DhanContext`, `dhanhq.place_order`, `modify_order`, `cancel_order`, `get_order_by_id`, `get_positions`, `get_holdings`, `ticker_data`, `get_order_list`, `get_trade_book`, `get_fund_limits`, `generate_tpin`, `edis_inquiry`, `convert_position` | None (all unchanged) |
| `integration/dhan/data_adapter.py` | `DhanContext`, `MarketFeed`, `dhanhq` | `MarketFeed(dhan_context, instruments, version="v2", callbacks)`, `run_forever`, `disconnect`, `unsubscribe_symbols`, `intraday_minute_data`, `historical_daily_data`, `ohlc_data`, `ticker_data`, `option_chain` | None in SDK; **adapter bug**: request codes 2/8 invalid for v2 (see section 3) |
| `integration/instrument_master.py` | `dhanhq` | `fetch_security_list()` | None (method unchanged; `fetch_global_security_list` is additive) |

All SDK symbols above are present in 2.2.0 with identical signatures (verified by file diff), so the upgrade test matrix is empty for 2.3.0rc1.

---

## 8. SessionHealth / Token Lifetime Notes (current gaps in OUR code, grounded in SDK behavior)

- `DhanLogin.renew_token(access_token)` -> GET `https://api.dhan.co/v2/RenewToken` (headers `access-token`, `dhanClientId`). Response contains a new token usable immediately. The SDK never calls this automatically.
- `DhanHTTP` holds `self.access_token` in the header dict at construction time; replacing the token requires building a new `DhanHTTP`/`DhanContext` (exactly what `SessionHealth._init_context` does). But note `SessionHealth` re-inits with the SAME stored token — if that token is already expired, re-init alone cannot heal it; the wrapper must call `DhanLogin.renew_token` (or `generate_token`) to mint a fresh token first. This is a real gap to close in `SessionHealth.refresh()`.
- Feed 807 ("Access Token is expired") arrives over the WS, not REST — our data adapter's `_on_error`/`_on_close` path must be able to trigger the same renewal flow (currently it only logs).

---

## 9. Historical Context: How We Got to 2.2.0 (for pinning decisions)

PyPI release history (relevant to our `>=0.1.0` pin and why loose pins are dangerous here):

- **1.x (2022-2024):** original SDK layout — `dhanhq('client_id','access_token')` constructor, no `DhanContext`.
- **2.0.0 (2024-10):** major rework; `DhanContext` introduced; imports/constants moved (`marketfeed.NSE` -> `MarketFeed.NSE`). Breaking vs 1.x.
- **2.1.0 (2025-03):** **YANKED** from PyPI with reason "Breaking changes" — 20-level depth, modular restructure, `DhanContext`-only construction. Another breaking wave vs 2.0.x.
- **2.2.0 (2026-04-24):** current stable; 200-level full depth, expired options data, Super Orders, IP management. This is what our mirror and working tree assume.
- **2.3.0rc1 (2026-07-07):** pre-release only; features enumerated in section 1. NOT installed by default even with `>=0.1.0`.

Lesson: Dhan has a track record of breaking changes + one yanked release. A `>=0.1.0` upper bound of `<2.3.0` (or exact `==2.2.0`) is strongly advised to prevent a future 2.3.0 stable from silently changing behavior under us.

---

## 10. Action Checklist (ordered)

1. [ ] Pin `dhanhq>=2.2.0,<2.3.0` in `pyproject.toml` (currently `>=0.1.0`).
2. [ ] Fix `DhanDataAdapter` request codes: `FEED_CODE_TICKER 2 -> 15`, `FEED_CODE_FULL_QUOTE 8 -> 21` (use `MarketFeed.Ticker`/`MarketFeed.Full` constants), and correct the stale 41/51 docstring comment.
3. [ ] Add disconnect-code-aware handling in `DhanDataAdapter`: map 806 -> entitlement error + STOP reconnect loop; 807 -> trigger token renewal; 805/transient -> backoff with jitter (SDK reconnects every 1s blindly).
4. [ ] Upgrade `SessionHealth.refresh()` to actually call `DhanLogin.renew_token` (mint new token) before rebuilding `DhanContext`, and wire data-adapter 807 handling to the same renewal path.
5. [ ] Re-verify after any future 2.3.0 stable release: diff `auth.py`, `marketfeed.py`, `dhan_http.py`, `_historical_data.py`, `_option_chain.py` against 2.2.0 before bumping (these are our contract files).
