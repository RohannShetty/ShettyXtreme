# ADR-008: Fyers Migration — Replace Dhan as the Primary Broker

## Status
Accepted (2026-08-05). Phase 1 of the Fyers migration; supersedes ADR-007 (Dhan credentials) and amends frozen rules FR-002/FR-003 (`.projectos/identity/frozen-rules.md`) and BOUNDARY-003 (`.projectos/governance/boundaries.json`).

## Context
Dhan was the first-party broker (D8, ADR-007). The mission-plan audit (`docs/superpowers/plans/2026-08-04-fyers-migration-audit-cockpit.md`) re-examined the broker layer and found Dhan's SDK (dhanhq 2.2.0) to be a source of recurring operational pain — a blocking feed loop, no clean token lifecycle, and webhook-based postbacks with NULL symbol/side on fills. Fyers was researched as the replacement (primary-source verified 2026-08-04):

- **Auth:** OAuth2 authorization-code flow. `GET /api/v3/generate-authcode` → browser login → callback `auth_code` (single-use, short-lived) → `POST /api/v3/validate-authcode` with `appIdHash = sha256(app_id:secret_id)` → `access_token`. A `refresh_token` is returned but the refresh endpoint is **undocumented / possibly discontinued** — treat daily interactive re-auth as the reliable path.
- **Token TTL unpublished.** Community "~6 AM IST" claims are unverifiable. Design for daily re-auth; liveness via `GET /profile` probe. Expiry errors: REST -8/-15/-16/-17 or HTTP 401; data socket 11001/-99; order socket 403 handshake.
- **Error mapping:** Dhan 806 (data entitlement) → Fyers **HTTP 403 / -373**. Dhan 807 (silent renew) → Fyers interactive re-login.
- **No sandbox** (`uat-api.fyers.in` dead) → real account + OBSERVER mode + small notionals.
- **Rate limits:** 10 req/s · 200/min · 100k/day; order ops 10/s; minute-cap breach >3×/day = blocked all day. Token-bucket throttle (~8/s) mandatory.
- **REST:** `api-t1.fyers.in/api/v3` — profile/funds/holdings/positions/tradebook/orders; `POST /orders/sync`; `PATCH/DELETE /orders/sync`. CO/BO deprecated 2026-08-02 → `stopLoss`/`takeProfit` params. SEBI algo regs in effect since 2026-04-01.
- **Data API:** `/data/history` (minute ≤100 days/req; daily ≤366 days; `oi_flag=1`), `/data/quotes` (≤50 symbols), `/data/depth`, `/data/options-chain-v3` (greeks).
- **WS:** data socket `wss://socket.fyers.in/hsm/v1-5/prod` (HSM binary protocol, 5000 symbols/conn, 10s heartbeat); order socket `wss://socket.fyers.in/trade/v3` (JSON, `SUB_ORD`; replaces Dhan postback webhooks — fill fidelity improves).
- **Symbols:** `NSE:SBIN-EQ`, `NSE:NIFTY50-INDEX`, `NSE:NIFTY20OCTFUT`, weeklies use month codes `1-9/O/N/D` — the #1 `-300` gotcha. Daily master `public.fyers.in/sym_details/<MASTER>_sym_master.json` → exact-match lookup, never hand-construct.
- **SDK `fyers-apiv3` 3.1.15** (MIT): sync/threading model, singleton data socket, junk deps → `--no-deps` + pinning if used. Per §9 Q2, the migration uses **raw httpx + websockets** for REST and order WS, with a **supervised SDK data-socket wrapper** (HSM protocol reimplementation not worth the risk).

## Decision
1. **Fyers replaces Dhan** as the primary broker. Dhan SDK usage, `integration/dhan/`, and the Dhan postback webhook path are deleted.
2. **Auth model:** broker-discriminated encrypted credential store (`app_id` + `secret_id` + single `access_token`), OAuth2 authorization-code wizard flow with an immediate auth-code exchange, no JWT parsing, no PIN/TOTP, no data-token fallback. 60s health cadence + pre-market probe; no auto-browser-redirect mid-session; token-expired surfaces as a visible STALE/EXPIRED state, never zeros.
3. **Contract mapping (Fyers ↔ internal Protocols):** zero changes to the `core/interfaces` Protocols. `integration/fyers/trading_adapter.py` implements `OrderExecutor` + `AccountInfo`; `integration/fyers/data_adapter.py` implements `MarketDataStream` + `DataProvider`. Symbol resolution maps internal names → Fyers tickers (`integration/fyers/symbols.py` + `instrument_master.py`), validated by exact master lookup.
4. **Fills:** order socket JSON frames → `ORDER_UPDATED` events (replaces Dhan postback webhooks).
5. **Risks & mitigations:**
   | Risk | Mitigation |
   |---|---|
   | Rate limits (200/min; 3 strikes = day block) | Token-bucket ~8/s on `FyersHTTPClient` (day one); WS for ticks, never polling; honor `Retry-After` |
   | WS reconnect semantics differ | Standalone async WS client + supervised data-socket wrapper with a reconnect test matrix (token-expiry-mid-feed, network drop, server disconnect, 403-on-reconnect = re-auth trigger) |
   | Token expiry mid-session, no silent refresh | Session-valid gate before LIVE; visible EXPIRED state + STALE freeze (never zeros); PAPER default; D10 no-auto-restore |
   | No sandbox | OBSERVER-first + dry-run tooling + small notionals; pre-market probe gates ingestion |
   | Symbol-format cascade (weekly `-300` gotcha) | Instrument master + resolver FIRST with an internal↔Fyers round-trip gate; exact-match lookup |
   | SEBI regulatory drift | Re-check `/mandatory-regulatory-changes` before go-live; this ADR records the 2026-08 state |

## Consequences
- `integration/dhan/` deleted; `auth/dhan_oauth.py` deleted; `src/` is Dhan-free (grep-gated).
- Setup wizard becomes the Fyers OAuth flow; Settings/Header copy de-Dhaned.
- Config: `broker: fyers`; `default_watchlist.yaml` holds internal symbols only.
- Version bumped to 0.11.0 across the 5 drifted files (README/CHANGELOG/architecture updated).
- Dhan history retained only in ADR-007 and this record's context; no code carries Dhan assumptions.
