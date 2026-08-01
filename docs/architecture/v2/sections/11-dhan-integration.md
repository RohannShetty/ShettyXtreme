# Section 11 — Dhan Integration

> First-party Dhan integration per D8 and corrected fact 2: single-primary credential model with an optional data fallback token, DhanHQ-py pinned 2.2.0 (corrected fact 5), all Dhan-specific logic isolated in `integration/dhan/`, everything else speaking `core/interfaces` Protocols. Evidence: `docs/references/BRIEF-dhanhq-upstream.md`. Rewrites `docs/architecture/v1/sections/11-dhan-integration.md` (v1's trading/data credential split and WS codes 2/8/41/51 were wrong — corrected here).

## 1. Auth / session realities (D8)

| Reality | Consequence |
|---|---|
| One `DhanContext(client_id, access_token)` serves trading REST + `api-feed.dhan.co` WS + historical (DhanHQ-py 2.2.0 design) | **Single-primary model**: one credential drives everything; no separate "trading token" exists in the SDK (corrects v1) |
| Two ways to mint a token: OAuth consent (`generate_login_session`/`consume_token_id`, app-level) and PIN + TOTP (`generate_token`, self/primary) | `auth/DhanOAuthHelper` implements consent as primary; PIN/TOTP `generateAccessToken` flow provisions the **optional `data_access_token` fallback slot** if the feed rejects the consent token |
| Tokens expire ~3 AM IST daily | SessionHealth pre-open refresh (09:00 IST pre-market) is mandatory, not best-effort |
| SDK has **no auto-refresh**; `DhanLogin.renew_token(access_token)` exists but nothing calls it | `SessionHealth` owns the refresh: it must call `renew_token` (or `generate_token`) to mint a **new** token, then rebuild `DhanContext` — rebuilding with the same stored token cannot heal an expired one (documented gap, closed in Phase 2) |
| **806** = "Subscribe to Data APIs to continue" → Data-API **entitlement/subscription** error, not credential mixing | Corrected fact 1: the fix for 806 is a data-subscription entitlement (or the fallback token slot), never "use trading creds for data" |

## 2. Order placement flows

- **Standard:** `place_order` / `modify_order` / `cancel_order` / `cancel_all_orders`; orderbook + tradebook reads for reconciliation. Every placement runs through the vendored mapping: OpenAlgo order dict → Dhan payload, including **SL-M → protective STOP_LOSS conversion** (`mapping/transform_data.py`, 2.0.1.6 MPP fix) and tick snapping — never reimplemented by hand ([Section 10 — OpenAlgo Utilization](10-openalgo-utilization.md)).
- **Lifecycle:** order → trigger-pending → filled/partial/rejected; live order-update WebSocket (order_update adapter) keeps the book current; all mutations go through `execution/ExecutionEngine` semi-auto approval (D10) and the event bus.
- **Fail-safe:** **never auto-retry order placement** (duplicate-risk). Failures log, surface, and the operator decides. The **kill switch** blocks the execution service from placing orders and is checked by the risk engine on every gate evaluation, not just at startup.

## 3. Positions / holdings / tradebook

| Data | Source | Notes |
|---|---|---|
| Positions | REST `get_positions` | **Positions lack LTP** — enrich with a `multiquote` call for live P&L; cache quotes against the position list on the terminal's refresh cadence (verified: src/shettyxtreme/integration/dhan/trading_adapter.py get_positions_with_ltp) |
| Holdings | REST `get_holdings` | Equity delivery book, low frequency |
| Tradebook | REST `get_trade_book` + order-update WS | Reconciliation input for `learning/OutcomeTracker` (immutable `execution_attempts`) |

## 4. Live data handling (feed protocol v2 — corrected codes)

| Aspect | Value |
|---|---|
| Subscription request codes (v2 JSON) | **15 = Ticker, 17 = Quote, 21 = Full**; 19 (Depth) is v1-only and rejected by v2 |
| Unsubscribe | Same message shape with **request code + 1** (16/18/22); `unsubscribe_symbols` live on the socket |
| Disconnect | v2 sends `{"RequestCode": 12}` + binary header packet, then closes |
| Server error packet (first byte 50, `<BHBIH`, code at index 4) | **805** connections exceeded · **806** entitlement (stop + surface) · **807** token expired (trigger renewal) · **808** invalid client ID · **809** auth failed |
| **Latent bug to fix (Phase 2)** | `DhanDataAdapter` passes request codes 2/8 (response codes) — v2 raises `ValueError` at runtime; unit tests mock the feed so it never surfaced. Fix: use `MarketFeed.Ticker=15` / `MarketFeed.Quote=17` / `MarketFeed.Full=21`, and correct the stale 41/51 docstring |
| Reconnect policy (SDK blind-loops 1 s forever) | Ours: map 806 → stop reconnect + entitlement health state; 807 → renewal path; 805/transient → backoff + jitter; distinguish server-initiated (first byte 50) from local close |

## 5. Historical data usage

- `intraday_minute_data` (1/5/15/25/60 intervals), `historical_daily_data`, `option_chain`/`expiry_list` — all unchanged between 2.2.0 and upstream 2.3.0rc1 (byte-identical; corrected fact 5).
- **REST responses cached in DuckDB** (`data/shetty_ts.db`): backfill once, refresh incrementally; self-throttle because the SDK has no rate-limit/pagination helpers.
- Option-chain snapshots cached with TTL + freshness checks; the feed (`get_option_chain` on the data adapter) refreshes the live surface.

## 6. Resilience: fail-closed trading, fail-open data

| Surface | Policy |
|---|---|
| Trading (orders, positions, funds) | **Fail-closed** — cannot trade → block execution, surface warning; credential health events via `TokenHealthMonitor` |
| Market data (feed, quotes) | **Fail-open with staleness indicator** — show stale data with an explicit staleness badge; never block trading purely on data age, but surface it in the cockpit |
| Silent stalls | **Watchdog**: 30 s feed staleness detector + heartbeat; a stalled feed triggers reconnect policy or health-state transition (never silence) |
| SessionHealth | Pre-open refresh, `renew_token` minting (Phase 2), 807-driven renewal from the data side |

## 7. API abstraction (adapters implement core Protocols)

`DhanTradingAdapter` and `DhanDataAdapter` implement the `core/interfaces` Protocols (`OrderExecutor`, `MarketDataStream`, `AccountInfo`, `BrokerGateway`, `DataProvider`). Nothing above `integration/` knows Dhan exists — configuration selects the broker, and intelligence/UI never see broker names (per [Section 05 — System Boundaries](05-system-boundaries.md)).

## 8. Broker-specific capabilities via discovery

Dhan-only features are exposed through optional interface methods gated by **capability discovery** (plugin.json-style registry, pattern adapted from OpenAlgo): the UI enables/disables surfaces based on advertised capabilities, never on hardcoded broker identity.

| Capability | Notes |
|---|---|
| Super Orders | Large-order types available on Dhan 2.2.0 |
| Forever Orders | `place_forever` (note: 2.3.0rc1 drops its `symbol` param — we don't use it; another reason to stay pinned, corrected fact 5) |
| Conditional Orders | Alert-based `/alerts/orders` (2.3.0rc1 module; gated behind the upgrade, not in 2.2.0) |
| Position conversion | MIS → NRML (`convert_position`) |
| EDIS | Delivery e-holdings flow (isolated) |
| AMO | After-market orders |

## 9. Multi-broker later (Phase 4, optional) without degrading Dhan-first

- A new broker = one new `integration/<broker>/` package implementing the same Protocols + capability registry. **Zero changes to core, intelligence, execution, learning, or UI.**
- **Dhan stays the reference implementation** — most polished, most tested, benchmark for any new adapter's behavior.
- Dhan-specific quirks (SL-M protective conversion, 806 handling, token rollover) remain inside `integration/dhan/`; no general mechanism inherits Dhan assumptions.
- Risk: broker-agnostic over-abstraction is explicitly **not** a Phase-2 goal (per pack: avoid overbuilding; Phase 4 only if it pays).

Cross-references: [Section 04 — India-First Scope](04-india-first-scope.md) (session realities), [Section 05 — System Boundaries](05-system-boundaries.md) (integration layer, pin table), [Section 06 — Proposed Architecture](06-proposed-architecture.md) (event flow), [Section 07 — Update-Resilient Design](07-update-resilient-design.md) (version-gated upgrades), [Section 10 — OpenAlgo Utilization](10-openalgo-utilization.md) (vendored Dhan mapping).
