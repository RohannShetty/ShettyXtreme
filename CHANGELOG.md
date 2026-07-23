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

## [2026-07-23] - Projection Wiring + Test Suite Overhaul

### Added
- **Projections**: Wired all 6 projection classes (Watchlist, Position, Risk, Alert, Intelligence, Health) into FastAPI lifespan, subscribed to EventBus topics.
- **Router Wiring**: All 5 routers (watchlist, intelligence, execution, scanner, health) now read from `app.state` projections instead of in-memory stubs.
- **Health Endpoint**: Now checks real EventBus state and adapter references via `HealthProjection`.

### Fixed
- **QuantLib**: Changed module-level `ImportError` raise to lazy guard — `QuantLibPricer` is importable without QuantLib installed, raises only on instantiation.
- **Signal Serialization**: `outcome_tracker.py` now serializes `SignalDirection` via `.value` instead of `asdict()`; deserialization handles both `"up"` and `"SignalDirection.UP"` formats.
- **Analytics**: Removed stale reference to deprecated `Signal.D` / `Signal.P` fields.
- **Test Suite**:
  - Fixed `test_api.py` fixture — uses `asyncio.create_task` for EventBus (was blocking with `await`).
  - Fixed lambda closure bug in `test_signal_engine.py` (3 tests).
  - Fixed `Signal(...)` construction in 8 test files (removed D/P/G kwargs).
  - Fixed `test_dhan_data_adapter.py` — `api_key` → `access_token`.
  - Fixed expiry selection tests — QuantLibPricer instantiation fallback.
  - Fixed option chain test — updated expected arg names to match adapter.
- **Feature Engine**: Resolved `TypeError: Any cannot be instantiated` by using proxy objects for indicators during tests.
- **Test Suite**: Cleaned up `__pycache__` directories.
