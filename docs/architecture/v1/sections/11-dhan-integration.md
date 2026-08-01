# Section 11: DHAN INTEGRATION STRATEGY

### Dhan API Split: Trading vs Data

| Aspect | Trading APIs | Data APIs |
|--------|-------------|-----------|
| **Purpose** | Live trading and account operations | Market data for analysis and research |
| **Endpoints** | Orders, positions, holdings, tradebook, funds, EDIS | Live market feed (WS), historical OHLC (REST), OI data |
| **Auth** | OAuth consent flow → access token | SK_M_`{clientId}` API key, expiry-based token (~3:00 AM IST) |
| **Rate limits** | Trading-specific limits | Data-specific limits |
| **Failover** | Fail-closed (can't trade → block execution, surface warning) | Fail-open (data fails → show stale data with staleness indicator) |
| **Caching** | Never cache (always fresh) | Aggressively cache (bars, option chain snapshots) with TTL + freshness checks |
| **WebSocket** | Order update WS (status changes, fills) | Market feed WS (ticks, quotes, depth) — binary protocol with codes 2/4/5/8/41/51 |
| **Error handling** | Never auto-retry order placement (risk duplicates). Log, surface, human decides. | Retry with backoff for data subscriptions. Reconnect WS on disconnect. |

### Dhan Trading Adapter Design

- Order placement (standard: Market/Limit/SL/SL-M, Dhan-specific: Super Orders, Forever Orders, Conditional Orders)
- Position conversion (MIS → NRML)
- EDIS flow (equity delivery, isolated)
- Auth: OAuth consent flow with auto-refresh (DhanHQ-py has no auto-refresh — we build it)
- Funds/margin: Direct from Dhan for precision

### Dhan Data Adapter Design

- Live market feed: Dhan Data API WebSocket (binary, codes 2/4/5/8/41/51)
- **Separate subscription/credentials** (error 806 if using Trading creds)
- Historical OHLC: REST API, cached in DuckDB
- OI/PCR: Direct from Dhan Data API (more granular), normalized by time-of-day percentile
- Fail-open with staleness indicator: if data fails, show staleness, don't block trading unless beyond freshness threshold
- Health check watchdog for silent-stall detection

### How to Support More Brokers Later Without Degrading Dhan-First Experience

- Broker adapters implement `OrderExecutor`, `MarketDataStream`, `AccountInfo`, `HistoricalDataProvider` protocols
- Dhan adapter is the reference implementation — most polished, most tested
- New broker = new adapter implementation, zero changes to core/intelligence
- Config selects active broker; intelligence and UI don't know which broker is active
- Broker-specific capabilities (Super Orders, position conversion) exposed as optional interface methods; UI enables/disables based on capability discovery

---

