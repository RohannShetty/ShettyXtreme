# Section 3: India-First Scope

## NSE/BSE Market Reality

The Indian market has structural differences from Western markets that our architecture must treat as native, not as special cases:

### Instrument Model
- **Equities** — Cash (delivery) and intraday segments
- **Futures** — Stock futures, index futures
- **Options** — Stock options, index options (weekly/monthly expiries)
- **Indices** — Nifty 50, Bank Nifty, Finnifty, Midcap Nifty, Sensex, and sectoral indices
- **Series** — EQ (equity), FUT (futures), OPT (options), INDICES
- **Trading symbols** — Scrip code + exchange + series + expiry + strike + type

### Expiry Behavior
- Weekly expiries on Thursdays (Nifty, Bank Nifty, Finnifty, Midcap Nifty)
- Monthly expiries on last Thursday of month
- Expiry day volatility and rollover dynamics
- This is central to options workflow design

### Trading Sessions
- Pre-open: 9:00-9:15 IST
- Regular: 9:15-15:30 IST
- Post-close: 15:30-16:00 (margins, positions)
- After Market Orders (AMO) — placed after hours for next-day execution
- No overnight futures trading (unlike US)

### Settlement
- T+1 settlement for equities (transitioned from T+2)
- T+1 for F&O (daily mark-to-market)
- No pattern day trader rule (unlike US)
- Different margin rules (VAR, ELM, MTM)

### Order Types
- LIMIT, MARKET, SL (Stop Loss), SL-M (Stop Loss Market)
- AMO (After Market Order)
- CO (Cover Order — intraday only)
- BO (Bracket Order — intraday only)
- IOC (Immediate or Cancel)

## Dhan-Specific Indian Market Considerations

### Dhan Strengths We Exploit First
- Fast account opening and API activation
- No minimum balance requirements
- Competitive brokerage (₹0 on delivery, low on intraday/F&O)
- Good API documentation and SDK support
- WebSocket support for live data
- Support for all major order types including AMO
- Position conversion between intraday and delivery

### Dhan Constraints We Must Handle
- Rate limits on API calls (per endpoint, per second)
- Token refresh requirements (access tokens expire)
- Market data limitations (certain data only through WebSocket)
- Historical data availability (limited duration for intraday)
- Margin calculation differences from other brokers

## Where India-First is First-Class (Not Generic)

These areas have India-specialized implementations:
1. **Instrument master** — NSE/BSE scrip codes, series, expiry calendar
2. **Options chain** — Weekly/monthly expiry, strike ladder, Greeks
3. **Market status** — Session state machine (pre-open, live, post-close, holiday)
4. **Calendar** — Trading holidays, expiry schedule, result season
5. **Margin models** — SPAN, VAR, ELM based on Indian clearing corp rules
6. **Taxation** — STT, CTT, stamp duty, capital gains (long/short term)
7. **Corporate actions** — Dividends, bonuses, splits, rights issues

## Where Multi-Asset Should Be Generic

These areas should support international assets via the same interfaces:
1. **Event bus** — Instrument-agnostic message passing
2. **Storage model** — Time-series data stores (bars, ticks) for any instrument
3. **Plugin system** — New asset classes added via plugins
4. **Backtesting framework** — Strategy evaluation independent of market
5. **Signal engine** — Indicator computation on normalized data
6. **Risk models** — Position sizing and exposure limits (market-agnostic parameters)
