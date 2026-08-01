# Section 4: INDIA-FIRST SCOPE

### NSE/BSE Market Reality

| Aspect | Indian Reality |
|--------|---------------|
| **Instruments** | Equities (EQ), Futures (FUT), Options (OPT), Indices (NIFTY, BANKNIFTY, FINNIFTY, MIDCAPNIFTY) |
| **Expiry** | Weekly on Thursdays, monthly on last Thursday. Expiry day volatility and rollover dynamics are central to options workflow |
| **Sessions** | Pre-open 9:00-9:15 IST, Regular 9:15-15:30 IST, Post-close 15:30-16:00 |
| **Settlement** | T+1 equities, T+1 F&O (daily MTM) |
| **Order types** | LIMIT, MARKET, SL, SL-M, AMO, CO (Cover), BO (Bracket), IOC |
| **Dhan-specific** | Super Orders (multi-leg coordinated), Forever Orders, Conditional Orders — NOT in OpenAlgo |

### Where Indian-Market Specialization is First-Class

1. **Instrument master** — NSE/BSE scrip codes, series, expiry calendar with holiday awareness
2. **Options chain** — Weekly/monthly expiry, strike ladder, Greeks
3. **Market status** — Session state machine (pre-open, live, post-close, holiday)
4. **Calendar** — Trading holidays, expiry schedule, result season
5. **Margin models** — SPAN, VAR, ELM based on Indian clearing corp rules
6. **PCR/OI** — Time-of-day normalized, expiry-aware

### Where Multi-Asset Should Be Generic

1. Event bus — instrument-agnostic message passing
2. Storage model — time-series data stores for any instrument
3. Plugin system — new asset classes added via plugins
4. Signal engine — indicator computation on normalized data
5. Risk models — position sizing and exposure limits (market-agnostic parameters)

### Dhan-Specific Considerations

**Strengths we exploit:**
- No minimum balance requirements
- Competitive brokerage (₹0 on delivery, low on intraday/F&O)
- Good API documentation and SDK support
- WebSocket support for live data
- Support for all major order types including AMO
- Position conversion between intraday and delivery
- Super Orders, Forever Orders, Conditional Orders (Dhan-unique)

**Constraints we must handle:**
- Dual credentials: Trading credentials ≠ Data API credentials (error 806 if mixed)
- Token refresh requirements (access tokens expire ~3AM IST, DhanHQ-py has no auto-refresh)
- Rate limits on API calls (per endpoint, per second)
- Historical data availability (limited duration for intraday)
- Positions response does NOT include LTP — separate `multiquote` call required
- WebSocket: DhanFeed for live data — binary protocol, separate from REST

---

