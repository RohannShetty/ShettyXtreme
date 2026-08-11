# Section 11 — Fyers Integration

> First-party Fyers integration per ADR-008 (2026-08-05, replaces the Dhan-era D8). Auth is OAuth2 authorization-code (app_id + secret_id + single daily access token); REST is raw `httpx` with a token-bucket throttle; order updates arrive over the JSON order WebSocket (replacing Dhan postback webhooks); market data uses the supervised HSM data-socket wrapper. All Fyers-specific logic is isolated in `integration/fyers/`; everything else speaks `core/interfaces` Protocols. Evidence: `docs/references/` Fyers briefs + mission plan `docs/superpowers/plans/2026-08-04-fyers-migration-audit-cockpit.md`. This file replaces `11-dhan-integration.md` (archived with ADR-007).

## 1. Auth / session realities (D8, per ADR-008)

| Reality | Consequence |
|---|---|
| OAuth2 authorization-code: `GET /api/v3/generate-authcode` → browser login → callback `auth_code` (single-use) → `POST /api/v3/validate-authcode` with `appIdHash = sha256(app_id:secret_id)` → `access_token` | **FyersOAuthHelper** implements the flow; the access token is exchanged immediately at the callback (`/auth/fyers/callback`) |
| Token TTL unpublished (community "~6 AM IST" unverifiable); a `refresh_token` is returned but its refresh endpoint is **undocumented / possibly discontinued** | **Daily interactive re-auth is the reliable path.** `GET /profile` probe is the liveness source of truth; the stored expiry is a heuristic schedule |
| Expiry errors: REST -8/-15/-16/-17 or HTTP 401; data socket 11001/-99; order socket 403 handshake | Transport classifies all of these as `FyersTokenExpired` → health monitor surfaces an EXPIRED state; no silent mid-session refresh |
| **403 / -373** = app lacks the Market-Data entitlement (the Dhan 806 twin) | Surfaced as `FyersDataEntitlementError` in setup/health — never papered over |
| No sandbox (`uat-api.fyers.in` dead) | Real account + OBSERVER-first + small notionals; pre-market probe gates ingestion (R7) |

## 2. Order placement flows

- **REST:** `POST /orders/sync` (place), `PATCH /orders/sync` (modify), `DELETE /orders/sync` (cancel), `GET /orders` (book). Wire values: `type` 1=LIMIT 2=MARKET 3=SL-M 4=SL-L; `productType` CNC/INTRADAY/MARGIN/MTF; `side` 1/-1; `validity` DAY/IOC. Enums live in `integration/fyers/mappings.py`.
- **Fills:** the **order WebSocket** (`wss://socket.fyers.in/trade/v3`, JSON, `SUB_ORD` channels orders/trades) replaces Dhan postback webhooks → `ORDER_UPDATED` events with real symbol/side (fill fidelity improves). `postback_router.py` owns the parsing + EventBus bridge; the legacy HTTP POST path is retained for the migration window.
- **Lifecycle:** all mutations go through `execution/ExecutionEngine` semi-auto approval (D10) and the event bus. OBSERVER-first: the platform proposes, the human approves.
- **Fail-safe:** never auto-retry order placement (duplicate-risk). The kill switch blocks placement and is checked by the risk engine on every gate evaluation.
- **CO/BO deprecated 2026-08-02** → `stopLoss`/`takeProfit` params. SEBI algo regs in effect since 2026-04-01 — re-check `/mandatory-regulatory-changes` before go-live (R8).

## 3. Positions / holdings / tradebook / margin

| Data | Source | Notes |
|---|---|---|
| Positions | `GET /positions` (netPositions) | mapped to `Position`; m2m from `unrealized_profit`/`pl` |
| Holdings | `GET /holdings` | equity delivery book, low frequency |
| Tradebook | `GET /tradebook` | reconciliation input for `learning/OutcomeTracker` |
| Margin | `GET /funds` (fund_limit array) | `get_margin()` → available/utilized/total; risk projection init UNKNOWN (never a fake 500000.0) |

## 4. Live data handling

| Aspect | Value |
|---|---|
| Data socket | `wss://socket.fyers.in/hsm/v1-5/prod` — **HSM binary protocol**; wrapped by a supervisor thread around the SDK's `FyersDataSocket` (per §9 Q2 hybrid: raw REST + raw order WS + supervised SDK data socket) |
| Subscriptions | `SymbolUpdate` (also DepthUpdate, CommentryUpdate); ≤5000 symbols/conn; 10s heartbeat |
| Bars | Fyers has no server-side bar subscription → the data adapter aggregates bars client-side from ticks (`BarAggregator`, `_util.py`) |
| Token expiry mid-feed | SDK error codes `11001`/`-99` → `FyersTokenExpired` → fatal error + error callback; a fresh token + reconnect are required |
| Entitlement | `FyersDataEntitlementError` propagates from subscribe so the caller can gate on it; history reads degrade to empty lists |

## 5. Historical data usage

- `/data/history`: minute resolutions capped at **100 days/request**, daily at **366** — ranges are chunked (`_util.chunk_date_range`); `oi_flag=1` appends OI.
- `/data/quotes` (≤50 symbols) for OHLC + LTP; `/data/options-chain-v3` (greeks, ≤50 strikes) for the chain.
- REST responses cached in DuckDB (`data/shetty_ts.db`): backfill once, refresh incrementally.
- Option-chain snapshots cached with TTL + freshness checks.

## 6. Resilience: fail-closed trading, fail-open data

| Surface | Policy |
|---|---|
| Trading (orders, positions, funds) | **Fail-closed** — cannot trade → block execution, surface warning; credential health events via `TokenHealthMonitor` |
| Market data (feed, quotes) | **Fail-open with staleness indicator** — show stale data with an explicit staleness badge; never block trading purely on data age |
| Token expiry | **STALE-freeze, never zeros** — the cockpit shows an honest EXPIRED/STALE state; LIVE gated on session validity; D10 no-auto-restore |
| Silent stalls | **Watchdog**: feed staleness detector + heartbeat; a stalled feed triggers reconnect policy or health-state transition (never silence) |
| Rate limits | Token-bucket ~8/s on the REST transport (200/min limit; >3 minute-cap breaches/day = all-day block) + honor `Retry-After` |

## 7. API abstraction (adapters implement core Protocols)

`FyersTradingAdapter` and `FyersDataAdapter` implement the `core/interfaces` Protocols (`OrderExecutor`, `AccountInfo`, `MarketDataStream`, `DataProvider`). Nothing above `integration/` knows Fyers exists — configuration selects the broker, and intelligence/UI never see broker names (per [Section 05 — System Boundaries](05-system-boundaries.md)). Zero Protocol changes were required for the migration (Q3 verdict).

## 8. Symbol resolution (the -300 gotcha)

Fyers ticker format: equity `NSE:SBIN-EQ`, index `NSE:NIFTY50-INDEX`, futures `NSE:NIFTY24OCTFUT` (monthly) / `NSE:NIFTY24O08FUT` (weekly), options `NSE:NIFTY24OCT25000CE` (monthly) / `NSE:NIFTY24O0825000CE` (weekly). **Weekly month codes `1-9/O/N/D` are the #1 `-300` gotcha** — the instrument master + resolver (`integration/fyers/symbols.py` + `instrument_master.py`) is the single source of truth; symbols are validated by exact master lookup, never hand-constructed. The daily master downloads from `public.fyers.in/sym_details/<MASTER>_sym_master.json`.

## 9. Multi-broker later (Phase 4, optional)

- A new broker = one new `integration/<broker>/` package implementing the same Protocols + capability registry. **Zero changes to core, intelligence, execution, learning, or UI.**
- **Fyers is now the reference implementation** — most polished, most tested, benchmark for any new adapter's behavior.
- Broker-specific quirks (Fyers rate limits, HSM data socket, daily token expiry) remain inside `integration/fyers/`; no general mechanism inherits Fyers assumptions.

Cross-references: [Section 04 — India-First Scope](04-india-first-scope.md) (session realities), [Section 05 — System Boundaries](05-system-boundaries.md) (integration layer, pin table), [Section 06 — Proposed Architecture](06-proposed-architecture.md) (event flow), [Section 07 — Update-Resilient Design](07-update-resilient-design.md) (version-gated upgrades). ADR-008 records the migration decision + risk register.
