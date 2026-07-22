# ShettyXtreme Changelog

## [2026-07-22] - Critical Bug Fixes (Wave 7 Handoff)

### Fixed
- **Shadow Manager**: Corrected backward bearish vote evaluation (`LOSS` -> `WIN` condition).
- **Position Manager**: Corrected trailing stop loss to truly follow price (was fixed at entry price).
- **Paper Trading Engine**:
  - Corrected short position PnL computation preventing silent 0-value returns.
  - Fixed `buy_avg`/`sell_avg` calculation on position direction flips (short <-> long).
- **Execution Engine**: Removed hardcoded "infinite" 1B margin, now uses provider-injected portfolio.
- **Order Validation**: Added missing F&O exchanges (NFO, BFO, MCX, etc.) to valid exchange list.
- **Gap Scanner**: Fixed overnight double-detection bug in scan logic.
- **Analytics**: Fixed meaningless PnL normalization (±1.0) to use actual trade values.
- **Python Conventions**:
  - Replaced deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)`.
  - Fixed `datetime.now()` class-definition time bug in `Order` model using `default_factory`.
  - Fixed naive vs tz-aware datetime comparison in credential validation.
- **Terminal API**:
  - Improved error logging and status codes in `postback_router.py`.
  - Added Exception logging in `event_bus.py` handlers.
- **Data Store**:
  - Fixed `get_bars()` to use half-open interval `[start, end)` semantics (matching standard time-series conventions).
  - Added empty list guard in `write_ticks` to prevent DuckDB errors.
