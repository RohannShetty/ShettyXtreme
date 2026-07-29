# ShettyXtreme Changelog

## [2026-07-30] - Credential Consolidation: Dual → Single Dhan Credential

### Changed
- **CredentialStore**: Merged 10 dual fields (trading + data) → 6 single fields (`client_id`, `api_key`, `api_secret`, `access_token`, `token_expiry`, `client_name`)
- **Migration**: Auto-migrates old dual-format `credentials.enc` on first load
- **Validator**: `validate_trading()`/`validate_data()` → single `validate_credentials()`
- **ConfigManager**: Removed `DHAN_TRADING_CLIENT_ID`, `DHAN_DATA_*` env override fields
- **AuthRouter**: Collapsed 9 dual endpoints → 6 single endpoints; removed `/trading`/`/data` path suffixes
- **DhanOAuth**: Removed `state="trading"` parameter; `_consent_flows` dict → set
- **HealthMonitor**: Removed `trading_status`/`data_status` dual tracking → single `status`
- **Setup Wizard**: 4-step → 3-step; single credential input; single OAuth connect button

### Removed
- Dual credential paths: OAuth consent flow now uses one consent for both trading + market data
- Stale test files and test cases referencing dual endpoints

### Added
- Migration test: verifies old `trading_*`/`data_*` `credentials.enc` is transparently migrated

## [2026-07-29] - OAuth Redirect Flow + LSP/Git Hygiene

### Added
- **LSP Config**: `.vscode/settings.json` targeting `.venv\Scripts\python.exe` (Python 3.11), `typeCheckingMode=basic`
- **Project Standards**: `.python-version`, `.editorconfig`, `[tool.pyright]` in `pyproject.toml`

### Fixed
- **OAuth Consent Flow**: Replaced `window.open`+polling with direct redirect in `setup.html` — no more wasted consents, no two-tab confusion
- **Credential Validation**: `validator.py` now uses lightweight format-only checks instead of calling Dhan's `generate-consent` (which consumed consent slots per validation attempt)
- **Save-Before-Validate**: `setup.html` steps 1 and 2 now test credentials first, save only after successful validation
- **Error Handling**: `auth_router.py` raises `HTTPException(502)` when `generate_consent` returns `None` instead of failing silently
- **Dead Code**: Removed unused `ClientIdBody` model, stale polling functions, and `connectingOverlay3` from setup wizard
- **Tests**: Updated 5 validator tests to match new format-only validation behavior

### Changed
- **Graphify**: Refreshed knowledge graph — 2441 nodes, 4534 edges, 147 communities

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
