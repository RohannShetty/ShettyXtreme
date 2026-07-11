# Section 7: Feature Map

## By Phase

### MVP Features
- Watchlists with live prices
- Market internals (indices, A/D, P/C ratio)
- Option chain explorer with Greeks
- Price breakout scanner
- Gap scanner (overnight + intraday)
- Position viewer (read-only)
- Portfolio summary (P&L, exposure)
- Log viewer
- Connection status

### Phase 2 Features
- Full execution cockpit (order placement via OpenAlgo)
- Risk dashboard (delta, beta, VaR, stress)
- Backtest engine
- Historical price viewer with indicators
- Options strategy assistant (payoff, breakeven)
- IV rank/percentile viewer
- Trade journal with auto-capture
- Technical price alerts
- Signal generator (simple)
- Plugin manager

### Phase 3 Features
- Regime-aware signal engine
- Multi-scanner composite
- Options spread analyzer
- Rolling suggestions for options
- Auto-trailing stop loss
- Signal-based auto-execution
- Portfolio correlation matrix
- Decision audit trail
- Performance analytics (Sharpe, Sortino, win rate)
- Strategy comparison tool

### Optional/Experimental
- Pattern recognition (chart patterns)
- AI-assisted trade recommendations
- Community plugin marketplace
- Cloud/SaaS deployment mode
- Multi-user/collaboration features

### Execution Layer Updates (informed by Fincept analysis)

| Feature | Phase | Description |
|---------|-------|-------------|
| Paper trading engine | MVP | Full simulated portfolio with orders, positions, P&L (dataclass models) |
| Exchange daemon worker | Phase 2 | Persistent subprocess for fast broker API calls (eliminates startup overhead) |
| Algo trading engine | Phase 3 | Strategy scheduling, risk checks, execution hooks, multi-strategy coord |
| Unified backtesting facade | Phase 2 | Single interface over vectorbt, backtesting.py, custom engines |
| CLI analytics convention | Phase 2 | JSON stdin/stdout convention for analytics modules (from Fincept pattern) |
