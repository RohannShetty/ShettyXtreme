# BRIEF: OpenAlgo Upstream (marketcalls/openalgo) — Vendoring Reference

Date of research: 2026-08-01
Mirror: `D:\ShettyXtreme\references\upstream\openalgo` (shallow clone, 1 commit, 2026-07-31)
Local contaminated copy: `D:\OpenAlgo` (openalgoUI v2.0.1.4, main @ 2026-06-30)
Vendor target: `vendor/openalgo/` (does NOT exist yet — this brief defines what to pull)

---

## 1. Version + State

| Item | Value |
|---|---|
| Current upstream version | **2.0.1.7** (`pyproject.toml` line 4, `utils/version.py`) |
| Released | 2026-07-28 (GitHub release tag `openalgo-charts-indicators-drawing-tools`) |
| Local copy version | **2.0.1.4** (same file locations; `D:\OpenAlgo` main @ 2026-06-30) |
| Gap | 3 minor releases: 2.0.1.5, 2.0.1.6, 2.0.1.7 (~215 commits, 28 days) |
| Python target | 3.12+ (pyproject `target-version = "py312"`), package manager `uv` |

### Notable changes 2.0.1.4 -> 2.0.1.7 (relevant to us)

**v2.0.1.5 (2026-07-10, 49 commits) — "Reliability Release"**
- ZeroMQ bus fan-in fix (SUB binds, PUBs connect) — restores live ticks under gunicorn+eventlet. Broker-agnostic plumbing change; relevant if we adopt the ZMQ proxy layer.
- Multi-session login audit (#1591): `upsert_auth` teardown gated on real token change; 3 AM rollover revoke guard; throttled `last_seen` heartbeat. Touches `database/auth_db.py`, `blueprints/auth.py`.
- New Arbitrage tool (`services/arbitrage_service.py`, `blueprints/arbitrage.py`) — futures calendar-spread scanner.
- Dhan: no functional change in 2.0.1.5 itself (Dhan fixes were in 2.0.1.6).

**v2.0.1.6 (2026-07-24, 119 commits) — "Broker & Reliability Release"**
- **New broker: HDFC Sky** (`broker/hdfcsky/` — 24 files: plugin.json, api/, mapping/, streaming/ incl. protobuf). OpenAlgo now supports 35 brokers.
- **Dhan: SL-M protective-limit hardening** (`55b3e2027`, `828f8d23e`, `943e39912`) — SL-M orders converted to protective `STOP_LOSS` limit orders under Dhan's live MPP (market-protection-percent) regime. Lives in `broker/dhan/mapping/transform_data.py` (+ `utils/mpp_slab.py`). **This is a must-vendor change.**
- Dhan live order-update payload parsing fixed for camelCase field names → new `broker/dhan/streaming/dhan_order_adapter.py`.
- Real-time order-update streaming extended: IIFL Capital + Upstox order feeds; new `websocket_proxy/order_adapter.py` base class; `services/order_update_service.py`; ZMQ publisher warm-up at boot; "trigger pending" promoted to first-class order-update status.
- Sandbox: "trigger pending" order status, F&O expiry settlement, event-driven MTM.
- Per-broker order adapters added across ~15 brokers (`broker/*/streaming/*_order_adapter.py`).

**v2.0.1.7 (2026-07-28, 47 commits) — "Charting Terminal & Workspace Hardening"**
- Kotak live order-update WebSocket feed; IIFL XTS feed-token refresh; `blueprints/postback.py` (new); `portfolio/` analytics package (14 files); `restx_api/portfolio.py`; `database/strategy_book_db.py`.
- Repo-wide logging/timeout hardening: missing HTTP timeouts added, stray `print()` -> centralized logging (`utils/logging.py`).
- No DB schema changes in 2.0.1.7.

### Dir-level diff (mirror 2.0.1.7 vs local 2.0.1.4), Python files only

| Dir | new | changed | gone |
|---|---|---|---|
| services/ | 6 | 14 | 0 |
| utils/ | 3 | 6 | 0 |
| websocket_proxy/ | 1 | 3 | 0 |
| database/ | 1 | 4 | 0 |
| broker/dhan/ | 1 | 2 | 0 |
| broker/fyers/ | 2 | 4 | 0 |
| broker/zerodha/ | 1 | 3 | 0 |
| restx_api/ | 1 | 1 | 0 |
| sandbox/ | 0 | 7 | 0 |
| blueprints/ | 1 | 9 | 0 |
| events/ | 0 | 2 | 0 |
| subscribers/ | 2 | 2 | 0 |

Dhan-specific: `api/funds.py` changed (5.0K -> 5.5K), `mapping/transform_data.py` changed (5.5K -> 11.6K, the SL-M work), `streaming/dhan_order_adapter.py` NEW (7.3K).

---

## 2. FILE MAP

### (a) Order validation

- **`utils/constants.py`** (4.8 KB) — THE single source of truth. Defines `VALID_EXCHANGES` (14 exchanges incl. NSE_INDEX/BSE_INDEX/MCX_INDEX/GLOBAL_INDEX/CRYPTO), `VALID_PRODUCT_TYPES` (`CNC`/`NRML`/`MIS`), `VALID_PRICE_TYPES` (`MARKET`/`LIMIT`/`SL`/`SL-M`), `VALID_ACTIONS` (`BUY`/`SELL`), `FNO_EXCHANGES`, `CRYPTO_EXCHANGES`, `REQUIRED_*_FIELDS` for place/cancel/modify/smart/close orders, defaults. **Zero imports — fully self-contained.**
- **`services/place_order_service.py`** (12.6 KB) — `validate_order_data()` checks missing mandatory fields, exchange/action/price-type/product-type membership against `utils.constants`, then deserializes via `restx_api/schemas.OrderSchema` (marshmallow, `validate.OneOf(VALID_EXCHANGES)`).
- **`services/basket_order_service.py`** `validate_order()` (16.3 KB), `services/place_smart_order_service.py` `validate_smart_order()` (12.8 KB), `services/place_options_order_service.py` (15.9 KB) — same pattern, all importing from `utils.constants`.
- **`restx_api/schemas.py`** — marshmallow schemas with `OneOf(VALID_EXCHANGES)` validators; wraps constants into API-level validation.
- **`sandbox/order_manager.py`** (line ~1287) — same validation duplicated for sandbox engine, also imports `VALID_EXCHANGES` from `utils.constants`.
- **`utils/api_analyzer.py`** (24.6 KB) — analyze-mode validation reusing the same constants.

### (b) Dhan broker adapter (`broker/dhan/`, 18 files, ~215 KB total)

- **`broker/dhan/plugin.json`** — `supported_exchanges: [NSE, BSE, NFO, BFO, CDS, BCD, MCX, NSE_INDEX, BSE_INDEX]`, `broker_type: IN_stock`, `leverage_config: false`.
- **`broker/dhan/api/auth_api.py`** (7.2 KB) — `generate_consent()` (Dhan OAuth consent flow, client_id extracted from `BROKER_API_KEY` `client_id:::api_key` format), `get_login_url()`, `get_access_token()`, `authenticate_broker()` — the entry point every broker plugin exposes. Imports: httpx, `utils.httpx_client`, `broker.dhan.api.baseurl`.
- **`broker/dhan/api/baseurl.py`** (0.5 KB) — `BASE_URL`, `get_url()`.
- **`broker/dhan/api/order_api.py`** (17.3 KB) — `place_order`/`modify_order`/`cancel_order`/`cancel_all_orders`/`get_order_book` etc., with `transform_data()` mapping applied; auth token via `database.auth_db`, symbol conversion via `database.token_db`.
- **`broker/dhan/api/data.py`** (54.0 KB) — `BrokerData` class: quotes/multiquotes, history, option chain, depth, search, instruments; per-endpoint rate limiter (`_apply_rate_limit`). Imports: httpx, jwt, pandas.
- **`broker/dhan/api/funds.py`** (5.5 KB) — funds/margin endpoints.
- **`broker/dhan/api/margin_api.py`** (10.1 KB), **`api/gtt_api.py`** (11.4 KB) — margin calc + GTT orders.
- **`broker/dhan/mapping/transform_data.py`** (11.6 KB) — **critical**: `transform_data()` maps OpenAlgo order dict -> Dhan payload; **SL-M -> protective STOP_LOSS limit** via `_slm_protected_price()` + `utils.mpp_slab`; tick snapping (`_snap_to_tick`); `map_exchange`, `map_exchange_type`. Imports: `database.token_db`, `utils.mpp_slab`, `utils.logging`.
- **`broker/dhan/mapping/order_data.py`** (15.8 KB) — order/tradebook/position/holdings -> OpenAlgo format (`map_order_data`, `transform_order_data`, `transform_positions_data`, `transform_holdings_data`).
- **`broker/dhan/mapping/gtt_data.py`** (8.4 KB), **`mapping/margin_data.py`** (3.8 KB).
- **`broker/dhan/streaming/dhan_adapter.py`** (46.7 KB) — `DhanAdapter(BaseBrokerWebSocketAdapter)` market-data WS: connect/auth/subscribe, tick normalization via `DhanCapabilityRegistry`/`DhanExchangeMapper` (`dhan_mapping.py`), ZMQ publish, heartbeat, reconnect.
- **`broker/dhan/streaming/dhan_websocket.py`** (35.8 KB) — raw Dhan WS protocol client.
- **`broker/dhan/streaming/dhan_mapping.py`** (5.3 KB) — capability registry + exchange mapper.
- **`broker/dhan/streaming/dhan_order_adapter.py`** (7.3 KB) — **NEW in 2.0.1.6**: live order/trade-update WS adapter, `class DhanOrderAdapter(BaseOrderUpdateAdapter)`; uses `websocket_proxy.order_adapter`.
- **`broker/dhan/database/master_contract_db.py`** (15.1 KB) — master-contract CSV download/store.
- **`broker/dhan/streaming/__init__.py`** (0.3 KB) — adapter registration for the broker factory.

### (c) Broker adapter registration pattern

- **`utils/plugin_loader.py`** (4.9 KB) — startup scan of `broker/*/plugin.json`: `load_broker_capabilities()` reads `supported_exchanges`/`broker_type`/`leverage_config` into an in-memory dict; `load_broker_auth_functions()` returns `_LazyBrokerAuthDict` that imports `broker.<name>.api.auth_api.authenticate_broker` **lazily** on first access (avoids importing all 30 broker SDKs at startup, ~3.5s saving). Discovery is: directory name == broker name; auth entry point == `authenticate_broker` in `api/auth_api.py`; order entry point == functions in `api/order_api.py` imported dynamically via `importlib.import_module(f"broker.{broker_name}.api.order_api")` (see `services/place_order_service.import_broker_module`). Streaming adapters registered in `websocket_proxy/broker_factory.py` keyed `{broker}_{user_id}`.
- Frontend/gating: `VALID_BROKERS` env var filters which plugins load at startup (server-side list in `app.py`/`blueprints/auth.py`).

### (d) Options Tools

All services consume `get_option_chain()` from `services/option_chain_service.py` as their data backbone.

| Tool | Service (backend math) | Blueprint (HTTP) | Size |
|---|---|---|---|
| Option Chain | `services/option_chain_service.py` (`get_option_chain`) | (in `blueprints/options.py` family) | 24.5 KB |
| Option Greeks | `services/option_greeks_service.py` (`calculate_greeks` — Black-76, forward-based per 2.0.1.4) | | 37.6 KB |
| IV Smile | `services/iv_smile_service.py` (`get_iv_smile_data`) | `blueprints/ivsmile.py` | 6.5 KB |
| Max Pain | `services/oi_tracker_service.py` (`calculate_max_pain`) | `blueprints/oi_tracker.py` | 12.6 KB |
| GEX | `services/gex_service.py` (`get_gex_data`) | `blueprints/gex.py` | 6.9 KB |
| Vol Surface | `services/vol_surface_service.py` (`get_vol_surface_data`) | `blueprints/vol_surface.py` | 9.4 KB |
| Gamma Density | `services/gamma_density_service.py` | | 13.6 KB |
| OI Profile / OI Range | `services/oi_profile_service.py` | | 13.3 KB |
| Synthetic Future | `services/synthetic_future_service.py` | | 6.8 KB |
| Option Symbol parsing | `services/option_symbol_service.py` | | 29.1 KB |
| Arbitrage (calendar spread) | `services/arbitrage_service.py` (2.0.1.5+) | `blueprints/arbitrage.py` | 7.9 KB |

Dependency chain of the options stack: `option_greeks_service` and `option_symbol_service` are near self-contained (imports: `utils.constants`, `utils.logging`, stdlib only). `option_chain_service` pulls in `database.auth_db`, `database.symbol` (SymToken), `database.token_db_enhanced`, `services.option_symbol_service`, `services.quotes_service` — heavier (DB + broker quotes). `iv_smile`/`gex`/`oi_tracker`/`vol_surface`/`gamma_density` all depend on `option_chain_service` + `option_greeks_service`.

---


---

## 2b. Dhan Adapter Deep-Dive (what we are actually absorbing)

### Auth flow (`api/auth_api.py`, 172 lines)
1. `generate_consent(dhan_client_id)` — POST `https://auth.dhan.co/app/generate-consent?client_id=...` with `app_id`/`app_secret` headers from `BROKER_API_KEY`/`BROKER_API_SECRET` env vars. Supports `BROKER_API_KEY` in `client_id:::api_key` format (client id split off with `:::`).
2. `get_login_url(consent_app_id)` — browser login redirect.
3. `get_access_token(request_token)` — exchanges the consent request token for the access token.
4. `authenticate_broker(auth_code, api_key, api_secret, ...)` — the standard entry point consumed by the auth layer; returns `(token, user_id, error)`. Token format: Dhan returns an access token plus a `feedToken` (separate token required for the market-data WebSocket, stored via `database.auth_db` as `feed_token`).

Key detail: Dhan uses two tokens — `access_token` (REST orders) and `feedToken` (WebSocket market data + order updates). Both are persisted and refreshed on the daily ~3 AM IST broker-token rollover, which is why `database/auth_db.py` has the multi-session teardown-gating logic from 2.0.1.5.

### Order mapping (`mapping/transform_data.py`, 11.6 KB — the file with the most Dhan-specific business logic)
- `map_exchange` / `map_exchange_type`: OpenAlgo exchange -> Dhan `NSE`/`BSE`/`NFO`/`BFO`/`CDS`/`BCD`/`MCX` (+ `INDICES` for index quotes).
- `transform_data(data, token)`: builds the Dhan order payload:
  - `price_type` mapping: `MARKET -> MARKET`, `LIMIT -> LIMIT`, `SL -> STOP_LOSS` (limit+trigger), `SL-M -> STOP_LOSS` with a **derived protective limit price** (`_slm_protected_price`) because Dhan's live MPP (market-protection-percent) regime rejects bare SL-M orders (fix shipped in 2.0.1.6, issue #1647).
  - `_snap_to_tick(value, tick, direction)`: rounds the protective limit to the instrument tick size, always on the safe side of the trigger.
  - Product mapping `CNC/NRML/MIS -> CNC/NORMAL/INTRAday`; disclosed quantity handling; order type override for `DRIP`/`AMO` (after-market) where supported.
- `transform_modify_order_data(data)`: same protective conversion applied on modify (also 2.0.1.6).
- Imports: `database.token_db.get_symbol_info` (SymToken lookup for tick size), `utils.mpp_slab` (MPP slab percentages by instrument type), `utils.logging`.

### Order API (`api/order_api.py`, 17.3 KB)
`place_order(order_data, access_token)`, `modify_order`, `cancel_order`, `cancel_all_orders`, `get_order_book`, `get_trade_book`, `get_positions`. All call `transform_data()` first, then POST to `https://api.dhan.co/orders/...`. Symbol conversion via `database.token_db.get_br_symbol` (OpenAlgo symbol -> Dhan `symbol/exchange/security_id`). Order statistics + positions mapping live in `mapping/order_data.py`.

### REST data (`api/data.py`, 54 KB — `BrokerData`)
`get_quotes` (LTP, snapshot, depth), `get_multiquotes`, `get_history` (intraday 1m/5m/15m + daily), `get_option_chain`, `get_search`, `get_instruments`, `get_oi` — each with a per-endpoint rate limiter (`_apply_rate_limit`, thread-safe, category-keyed: orders/quotes/history/option-chain have separate budgets). Uses `jwt` for feed-token signing on some endpoints and `pandas` for history CSV/DataFrame assembly.

### Streaming (`streaming/`, ~95 KB total)
- `dhan_adapter.py`: `DhanAdapter(BaseBrokerWebSocketAdapter)` — subscribes via `DhanWebSocket`, normalizes ticks (`DhanCapabilityRegistry` marks per-exchange capabilities like depth support), publishes normalized JSON to the ZMQ bus (`_connect_to_zmq_bus`), heartbeat + reconnect with backoff. `MAX_SYMBOLS_PER_WEBSOCKET` (1000) x `MAX_WEBSOCKET_CONNECTIONS` (3) = 3000-symbol cap.
- `dhan_websocket.py`: raw WS client (auth with feedToken, subscribe/unsubscribe frames, parse).
- `dhan_order_adapter.py` (NEW 2.0.1.6): `DhanOrderAdapter(BaseOrderUpdateAdapter)` — connects to Dhan's order-update WebSocket, normalizes camelCase fields (the 2.0.1.6 parse fix), emits `order_update` events on the shared event bus.

---

## 2c. File-level diff 2.0.1.4 -> 2.0.1.7 (mirror vs local, areas we care about)

| File | 2.0.1.4 size | 2.0.1.7 size | What changed (from release notes) |
|---|---|---|---|
| `broker/dhan/api/funds.py` | 5.0 KB | 5.5 KB | funds endpoint updates |
| `broker/dhan/mapping/transform_data.py` | 5.5 KB | 11.6 KB | SL-M -> protective STOP_LOSS conversion (place + modify), tick snapping, MPP integration (#1647) |
| `broker/dhan/streaming/dhan_order_adapter.py` | — | 7.3 KB | NEW: live order-update WS adapter |
| `utils/constants.py` | — | 4.8 KB | +`MCX_INDEX`, `GLOBAL_INDEX`, `CRYPTO` exchanges; `INSTRUMENT_PERPFUT`; crypto broker set |
| `utils/httpx_client.py` | — | 7.6 KB | shared timeout'd client (2.0.1.7 hardening) |
| `utils/logging.py` | — | 21.3 KB | centralized JSON logging (print() sweep in 2.0.1.7) |
| `websocket_proxy/order_adapter.py` | — | 17.8 KB | NEW: `BaseOrderUpdateAdapter` + `to_openalgo_symbol` |
| `websocket_proxy/base_adapter.py` | — | 23.1 KB | ZMQ fan-in fix (SUB binds, PUBs connect, 2.0.1.5) |
| `services/order_update_service.py` | — | 10.6 KB | NEW: order-update routing/normalization |
| `services/arbitrage_service.py` | — | 7.9 KB | NEW: calendar-spread scanner (2.0.1.5) |
| `sandbox/order_manager.py` | — | changed | trigger-pending status (2.0.1.6), MPP-aware fills |
| `database/auth_db.py` | — | changed | multi-session teardown gating + rollover guard (2.0.1.5) |

(Sizes marked "—" for 2.0.1.4 mean the file did not exist then; the local copy at `D:\OpenAlgo` is the 2.0.1.4 reference tree.)

## 3. VENDORING CANDIDATES TABLE

Proposed dest root: `vendor/openalgo/`. Priorities: **A** = must-vendor (Dhan-first platform core), **B** = high value, **C** = optional/later.

| # | Source path in mirror | Proposed dest | Size | What it provides | Dependencies (imports inside) | Priority |
|---|---|---|---|---|---|---|
| 1 | `utils/constants.py` | `vendor/openalgo/utils/constants.py` | 4.8 KB | All order constants: exchanges, product/price types, actions, required fields | none (stdlib only) | **A** |
| 2 | `broker/dhan/plugin.json` | `vendor/openalgo/broker/dhan/plugin.json` | 0.4 KB | Broker metadata/capabilities for discovery | none | **A** |
| 3 | `broker/dhan/api/baseurl.py` | `vendor/openalgo/broker/dhan/api/baseurl.py` | 0.5 KB | Dhan API base URL + url builder | none | **A** |
| 4 | `broker/dhan/api/auth_api.py` | `vendor/openalgo/broker/dhan/api/auth_api.py` | 7.2 KB | Consent flow + access token + `authenticate_broker` | httpx; `utils/httpx_client.py` (#6); `baseurl` (#3) | **A** |
| 5 | `broker/dhan/mapping/transform_data.py` | `vendor/openalgo/broker/dhan/mapping/transform_data.py` | 11.6 KB | Order mapping + **SL-M protective-limit conversion** (2.0.1.6 fix) + tick snapping | `database/token_db.py` (#8); `utils/mpp_slab.py` (#7); `utils/logging.py` (#9) | **A** |
| 6 | `utils/httpx_client.py` | `vendor/openalgo/utils/httpx_client.py` | 7.6 KB | Shared HTTP client w/ timeouts + retry (fixes missing-timeout class of bugs) | httpx; `utils/logging.py` (#9) | **A** |
| 7 | `utils/mpp_slab.py` | `vendor/openalgo/utils/mpp_slab.py` | 8.9 KB | MPP slab table: protective price calc, tick rounding — needed by Dhan SL-M and HDFC Sky | `utils/logging.py` (#9) | **A** |
| 8 | `database/token_db.py` | `vendor/openalgo/database/token_db.py` | 2.0 KB | `get_symbol/get_token/get_br_symbol/get_oa_symbol` — symbol <-> token mapping API used by every Dhan file | `database/symbol.py` (SymToken model, 14.7 KB) | **A** (pull both) |
| 9 | `utils/logging.py` | `vendor/openalgo/utils/logging.py` | 21.3 KB | `get_logger()` centralized JSON logging (2.0.1.7 hardened) | stdlib only | **A** |
| 10 | `broker/dhan/api/order_api.py` | `vendor/openalgo/broker/dhan/api/order_api.py` | 17.3 KB | place/modify/cancel/orderbook/tradebook | httpx; `transform_data` (#5); `database/auth_db.py` (**48.9 KB — big**); `token_db` (#8); `httpx_client` (#6) | **A** |

**Next-tier (B — high value, worth pulling in phase 2):**

| # | Source path | Proposed dest | Size | What it provides | Dependencies | Priority |
|---|---|---|---|---|---|---|
| 11 | `broker/dhan/api/data.py` | `vendor/openalgo/broker/dhan/api/data.py` | 54.0 KB | Quotes/history/option-chain/depth — REST data layer | httpx, jwt, pandas; `token_db`; `httpx_client`; `transform_data` | **B** |
| 12 | `broker/dhan/streaming/dhan_order_adapter.py` | `vendor/openalgo/broker/dhan/streaming/` | 7.3 KB | Live order/trade-update WS (new 2.0.1.6) | `websocket_proxy/order_adapter.py` (17.8 KB); `utils/event_bus.py`; `database/auth_db.py` | **B** |
| 13 | `services/option_greeks_service.py` | `vendor/openalgo/services/option_greeks_service.py` | 37.6 KB | Black-76 forward-based greeks — most self-contained options-math file | `utils/constants.py` (#1); `utils/logging.py` (#9); stdlib | **B** |
| 14 | `broker/dhan/mapping/order_data.py` | `vendor/openalgo/broker/dhan/mapping/` | 15.8 KB | Order/trade/position/holdings -> OpenAlgo format | `token_db`; `transform_data`; `logging` | **B** |
| 15 | `utils/plugin_loader.py` | `vendor/openalgo/utils/plugin_loader.py` | 4.9 KB | plugin.json discovery + lazy auth import pattern (drop-in registration pattern) | Flask `current_app` (**server coupling — needs shimming**); `utils/logging.py` | **B** |
| 16 | `broker/dhan/streaming/dhan_adapter.py` + `dhan_websocket.py` + `dhan_mapping.py` + `websocket_proxy/base_adapter.py` + `websocket_proxy/mapping.py` | `vendor/openalgo/broker/dhan/streaming/` + `vendor/openalgo/websocket_proxy/` | ~110 KB | Full market-data streaming pipeline | zmq; `websocket` pkg; `database/symbol.py`, `token_db`; `utils/logging` — base_adapter is cleanly separable (imports zmq + logging only) | **B** (phase 2) |

**Skip (server/Flask/React/ZMQ/DB code — do NOT vendor):**
- `app.py`, `blueprints/*` (Flask routes incl. options blueprints — we re-expose our own API), `frontend/` (React 19 + dist), `restx_api/` (Flask-RESTX), `database/auth_db.py` + all other `database/*.py` except `token_db`/`symbol` (SQLAlchemy models + Fernet token store — we have our own), `sandbox/`, `websocket_proxy/server.py` (93 KB ZMQ+SocketIO server), `websocket_proxy/connection_manager.py` (46.5 KB), `services/place_order_service.py` and all order *services (Flask session/events coupling), `services/option_chain_service.py` (DB + quotes service chain — heavier than value for now), `portfolio/`, `strategies/`, `events/`, `mcp/`, `okf/`, `docs/`, `test/`, `audit/`.

Note: several `database/*.py` deps (auth_db 48.9 KB) are entangled with Flask-SQLAlchemy/ScopedSession patterns; our vendor scope should treat the DB layer as ours, not theirs — keep `token_db.py` + `symbol.py` (SymToken dataclass) since the Dhan files import them, and adapt.

---

## 4. License Confirmation

- **File:** `License.md` = full text of **GNU AFFERO GENERAL PUBLIC LICENSE, Version 3 (AGPL-3.0)**, 19 November 2007. No dual license, no additional permissions (no `plugin.json`-style per-broker licensing found in-tree).
- **Private-use absorption implications (no distribution):**
  - AGPL s13 ("Remote Network Interaction") applies when the *modified* program is **made available to users over a network**. A private, internal, single-tenant platform (our ShettyXtreme execution engine, Dhan-only, self-hosted, no public multi-user SaaS offering) is **not** "conveying" under s0/s4 and does not trigger the source-offering obligation in practice — this is the standard private-use AGPL reading. **If we ever expose the modified code as a public network service, AGPL-13 requires offering Corresponding Source to those users.**
  - "Private-use absorption" (vendoring without distribution): acceptable under s2 ("You may make, run and propagate covered works that you do not convey, without conditions"). No obligation to publish our platform as long as we never distribute/convey it.
  - **Required housekeeping:** keep AGPL notices intact on every vendored file (s4: keep all license notices; s5a: prominent notice that the work is modified + date). Ship `vendor/openalgo/LICENSE` (AGPL-3.0 text) with our repo.
  - **Do NOT** link the vendored AGPL code into a distributed proprietary product, and do not claim our modifications as proprietary within the vendored files — that is the boundary. If we later distribute ShettyXtreme, the vendored subtree and any derivative must stay AGPL-3.0.
- Conclusion: vendoring for private/internal use is fine; flag for legal review only if the platform is ever distributed or offered as a public network service.

---

## 5. Upstream Velocity

- **Release cadence (recent):** 2.0.1.4 (2026-06-30) -> 2.0.1.5 (07-10) -> 2.0.1.6 (07-24) -> 2.0.1.7 (07-28). **~3 releases/month, roughly 1 per 1-2 weeks**, 47-119 commits each (~215 commits in 28 days ≈ 7-8 commits/day upstream).
- **Latest release:** v2.0.1.7, published 2026-07-28 (tag `openalgo-charts-indicators-drawing-tools`), 47 commits.
- **Project state:** very active (single-maintainer + community; 35 brokers; daily commits; CI builds frontend dist into main). Broker fixes land continuously (Dhan specifically got SL-M work in 2.0.1.6 — expect more Dhan fixes; note branch `dhan-data-rate-limit-split` existed upstream).
- **Cadence recommendation:** monthly diff-review against the mirror, aligned to release notes (`docs/releases/version-2.0.1.X-released.md` ship in-tree — read those first). Watch specifically: (1) `broker/dhan/*` (2.0.1.6 touched 3 files), (2) `utils/mpp_slab.py` + `transform_data.py` (protective-limit math), (3) `websocket_proxy/order_adapter.py` + per-broker order adapters (order-update streaming is an active area), (4) `utils/logging.py`/`httpx_client.py` (reliability hardening). Because the mirror is a shallow 1-commit clone, `git fetch --unshallow` (or re-clone with `--depth=...`) is required before any meaningful `git log` diff; otherwise diff trees file-by-file as done here.

---

## APPENDIX: Key absolute paths (mirror root = `D:\ShettyXtreme\references\upstream\openalgo`)

- Order constants: `utils\constants.py`
- Dhan plugin: `broker\dhan\plugin.json`
- Dhan auth: `broker\dhan\api\auth_api.py`, `broker\dhan\api\baseurl.py`
- Dhan order mapping: `broker\dhan\mapping\transform_data.py`, `broker\dhan\mapping\order_data.py`
- Dhan order API: `broker\dhan\api\order_api.py`, `broker\dhan\api\data.py`, `broker\dhan\api\funds.py`, `broker\dhan\api\margin_api.py`, `broker\dhan\api\gtt_api.py`
- Dhan streaming: `broker\dhan\streaming\dhan_adapter.py`, `dhan_websocket.py`, `dhan_mapping.py`, `dhan_order_adapter.py`
- Registration: `utils\plugin_loader.py`; lazy auth dict pattern in same file
- Options tools: `services\option_greeks_service.py`, `option_chain_service.py`, `iv_smile_service.py`, `oi_tracker_service.py`, `gex_service.py`, `vol_surface_service.py`, `gamma_density_service.py`, `option_symbol_service.py`; blueprints `blueprints\ivsmile.py`, `gex.py`, `vol_surface.py`, `arbitrage.py`
- Shared deps: `utils\mpp_slab.py`, `utils\httpx_client.py`, `utils\logging.py`, `database\token_db.py`, `database\symbol.py`
- Release notes: `docs\releases\version-2.0.1.{5,6,7}-released.md`

