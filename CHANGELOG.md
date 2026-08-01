# ShettyXtreme Changelog

## [2026-08-01] — v0.8.0: Phase 3B Research Workspace (AI Research Layer)

Suite: **599 passed / 0 failed / 3 skipped** (was 563). DeepSeek-backed briefer harness, per D3 research-layer only — no LLM output touches signal/gate/execution.

### Added
- **Briefer harness** (`research/`): `BriefProvider` protocol with `DeepSeekProvider` (httpx, OpenAI-compatible endpoint, JSON-output mode, non-thinking, `deepseek-v4-flash` default) and `SimulatedProvider` (deterministic test double with failure injection). `provider.py` is the only LLM-touching module (D3 wall).
- **3 briefer lenses** (`research/lenses.py`, declarative registry): `oi_iv_flow`, `directional_momentum`, `tail_risk` — each mirroring a live shadow-voter philosophy.
- **Context digest** (`research/digest.py`): as-of snapshot from injectable sources with `[SOURCE: name]` provenance; missing data renders `[UNSOURCED]`, never fabricated.
- **`ResearchBrief`** (`research/briefs.py`): strict pydantic contract — unknown-field rejection, enum/length caps, harness-owned `brief_id`/`lens`/`as_of`/`status`; injected instructions cannot survive the channel.
- **Orchestrator** (`research/orchestrator.py`): concurrent per-lens runs, reject-retry-once then fail, per-briefer token caps + timeouts, partial results on failure — never auto-advances.
- **Sqlite store** (`research/store.py`): append-only decisions (second decision → 409), expiry computed at read time, `outcome` stub for later briefer scoring.
- **Endpoints** (`/api/research/*`): `run`, `lenses`, `briefs` (list/get), `approve`/`reject`; 503 without `DEEPSEEK_API_KEY`, 400 unknown lens, never 500 on failed briefers or missing DBs.
- **Smoke script** (`scripts/research_smoke.py`): env-gated manual DeepSeek run (exit 2 without key; never called from tests).

### Security
- `DEEPSEEK_API_KEY` env-only, read at call time, never logged.

### Known
- Briefer outcome scoring (`outcome` WIN/LOSS stub exists), read-only data tools/MCP, critic model pass, terminal panel + WS broadcast, scheduled runs — deferred to 3C per spec §5.

## [2026-08-01] — v0.7.1: Phase 3A Advanced Intelligence

Suite: **563 passed / 0 failed / 3 skipped** (was 527). All deterministic/statistical — no LLM surface (D3).

### Added
- **Session-aware shadow graduation**: `ShadowManager` gate counts ≥20 distinct tracked sessions (market days; NULL dates excluded) with hit rate > 0.55; correctness is direction-aware per the approved spec (sign agreement AND trade WIN); `graduate()` atomically persists then promotes the shadow into the live voter registry (idempotent); `graduation_status()` for the terminal.
- **Synthetic session simulator** (`tests/wave6/session_simulator.py`): deterministic end-to-end graduation tests (good voter graduates at 21 sessions; poor voter and 19-session cases never do) — real graduation happens automatically once ≥20 real OBSERVER sessions accumulate.
- **Calibration → sizing**: `learning/sizing.py` `CalibratedSizing` maps the fitted calibration curve to a position-size multiplier (clamped 0.25×–2×, inactive until reliable); strategy hints now carry `quantity`.
- **Signal path wiring**: correlation block caps applied before weighting (correlated voter groups can't dominate conviction); `Signal` carries real participation-normalized D/P/G via `ConvictionEngine` (projection + `/signal` endpoint now show them, not zeros).
- **Walkforward depth**: per-voter directional hit rates + per-regime win rates in the report (premium/cost/TP-SL-EOD evaluation as before).
- **Learning endpoints**: `GET /api/learning/calibration` (curve points + reliability) and `GET /api/learning/shadows` (per-shadow sessions/hit-rate/graduated) — never 500 on missing DBs.

### Fixed
- Phase-2 deferred minors: `strike_price`/`drv_option_type` alias keys on the strategy-hint path; endpoint-level 503 tests for the 806 entitlement conversion; dead `_fetch_chain` wrapper removed; `on_regime_changed` dataclass-payload test.
- `ShadowManager` module docstring now reflects graduation (was stale).

### Changed
- Shadow-voter correctness semantics finalized per spec §3.1.4 (user decision): a vote is correct only when it agrees with the live trade direction AND the trade won — a direction-echoing voter whose trades lose cannot graduate.

### Known
- Graduated shadow voters are 3-arg `ShadowFn`s registered in a 1-arg-typed registry that `SignalEngine` does not consume yet — reconcile with an adapter when registry→engine wiring lands (deferred integration note).
- Live shadow-voter activation with real data is pending ≥20 real OBSERVER sessions (machinery proven with synthetic sessions; no fake claims).

## [2026-08-01] — v0.7.0: v2 Blueprint + Phase 2 Pipeline Completion

This release ships the full v2 architecture (Phases 0-2 of the delivery roadmap): a 20-section blueprint with binding decisions D1-D12, a DESIGN.md design contract, an OpenAlgo vendoring pipeline, the two previously-stubbed intelligence endpoints, Dhan data-feed and credential corrections, and the Svelte+Vite terminal. Suite: **527 passed / 0 failed / 3 skipped** (was 495 / 4).

### Added
- **Blueprint v2 + decisions**: 20-section architecture at `docs/architecture/v2/` (ARCHITECTURE_V2.md master + `sections/`), DESIGN.md design contract (token system: price-up red `#f6525c` / price-down green `#2ebd85`, JetBrains Mono numerals), ADR-002..007, v1 docs archived to `docs/architecture/v1/`.
- **OpenAlgo vendoring pipeline (D1/D2)**: `scripts/sync_vendor.py` + `vendor/openalgo/` (10 origin-stamped files, AGPL-3.0, byte-idempotent re-sync); zero `import openalgo` in `src/` (grep-gated); 7 reference briefs at `docs/references/`.
- **Intelligence endpoints (D6)**: `GET /api/intelligence/options` (chain + pure-Python greeks enrichment) and `GET /api/intelligence/strategy-hint` (regime/signal → strike EV selection) replace the two 501 stubs; new modules `intelligence/hints/strategy_hints.py`, `intelligence/conviction/conviction_engine.py` (D/P/G per blueprint §14); `VoterRegistry` fully implemented (register/names/count/get + `@voter` decorator + `get_registry()`).
- **Svelte + Vite terminal (D9)**: `src/shettyxtreme/terminal/web/` (Svelte 5, Vite 6, TypeScript) built to `terminal/static/` and served by FastAPI; cockpit panels per DESIGN.md (watchlist rail, chain grid, strategy hints, positions/risk strip, logs/alerts drawer, session controls with kill switch `Ctrl+Shift+K` and LIVE confirmation); hash routes `#/`, `#/setup`, `#/settings`; WebSocket tick channel; `svelte-check` gate (0 errors).
- **Credential fallback (D8)**: optional encrypted `data_access_token` slot + PIN/TOTP `generateAccessToken` flow (`DhanOAuthHelper.generate_access_token`); 806 surfaced as Data-API entitlement ("subscribe to Data APIs") on REST failure dicts, WS flag, health endpoint, and a visible terminal strip.
- **`run.py` CLI (D10)**: `--mode OBSERVER|PAPER|LIVE` (OBSERVER default), `--no-browser`, `--port`; LIVE requires a typed confirmation prompt.

### Fixed
- **Dhan WS feed request codes**: v2 subscription codes now 15/17/21 (was invalid v1 2/8) — `DhanDataAdapter.subscribe_ticks`/`subscribe_bars`; stale protocol docstring corrected.
- **OBSERVER default (D10)**: mode file never auto-restores LIVE (per-session confirmation, `confirm=true` required); `test_execution_mode_default` made deterministic.
- **`test_matches_builtin_black76`**: relative 1% tolerance with the QuantLib calendar-convention delta documented (env-pinned, no silent skip).
- **Strategy-hint starvation**: `IntelligenceProjection.on_signal_v2` now accepts `Signal` dataclass events (projection updates in production).
- **OAuth callback → SPA**: redirects to `/static/?...​#/setup` instead of the deleted `setup.html`; status banner on the setup view.
- **Landmines**: removed stale conftest fixtures (`openalgo_adapter`, `dhan_adapter` importing nonexistent modules), empty dirs (`execution/lifecycle`, `execution/position_tracker`, `tests/risk`, `tests/integration`), dead `core/errors/` package.
- **Changelog 2026-07-31's "Known" failures** (`test_get_options`, `test_get_strategy_hint`, `test_execution_mode_default`) are resolved by this release.

### Changed
- Runtime mode semantics: LIVE is an explicit per-session action with confirmation (API + CLI + terminal dialog); PAPER/OBSERVER persist.
- Test suite: 495 passing → 527 passing (4 known failures fixed, ~36 net new tests).

### Known
- Dhan `/optionchain` response key names unverified against a live API (no live credentials in this environment) — the router handles `strike`/`strike_price`, `option_type`/`drv_option_type`, spot aliases defensively; verify with a recorded fixture once live credentials are available (OPEN QUESTION, blueprint §02 precedent).

## [2026-07-31] — Graphify Knowledge-Graph Integration

### Added
- **graphify codebase graph**: AST-based knowledge graph at `graphify-out/` (2441 nodes / 4617 edges / 154 communities) with god-nodes, community structure, and cross-file relationship queries. No LLM dependency (Tasks 4-5 semantic extraction skipped: the `openai` backend requires an API key that the free/auth-free options can't satisfy).
- **Post-commit freshness hook**: automatically rebuilds the graph after every commit (verified live).
- **Impact-analysis workflow**: `graphify affected` / `query --dfs` / `path` / `explain` + `save-result`/`reflect` feedback loop, documented in `AGENTS.md`.
- **Export artifacts**: wiki (`graphify-out/wiki/`, 153 articles), D3 tree (`GRAPH_TREE.html`), call-flow Mermaid HTML, `graph.svg`. Benchmark: 27.7x token reduction vs naive full-corpus reads.
- **opencode integration**: tracked MCP entry + bash-prompt hook via `.opencode/plugins/graphify.js`.

### Changed
- **AGENTS.md**: documents the graphify rules + impact workflow for agent sessions.

### Known (pre-existing, not introduced here)
- 3 pytest failures unrelated to this upgrade (`test_execution_mode_default` expects OBSERVER vs LIVE default; `test_get_options`/`test_get_strategy_hint` hit 501 Not Implemented) — identical at baseline `dd3ef59`.


### Fixed
- **WatchlistProjection / GapDetector**: Both subscribed to `Topic.MARKET_DATA_TICK` but expected dict data while `StreamManager` publishes `Tick` dataclass objects. Added `isinstance(d, Tick)` guard at entry — converts attributes to dict. `change_pct` now derived from `(ltp - close) / close`.
- **Dashboard staleness (`—` placeholders)**: `fetchJSON` added `AbortController` 5s timeout so hanging fetches don't block the page. `refreshAll()` changed from `Promise.all` to `Promise.allSettled` — one render failure no longer blocks the other 9. Added console diagnostics for every refresh cycle.
- **`.gitignore`**: Added `data/` to prevent accidental commit of runtime SQLite databases.

### Added
- **Terminal test suite**: 46 tests across `test_projections.py`, `test_scanner_data.py`, `test_ws_bridge.py`, `test_mode_persistence.py`, `test_integration.py` — includes Tick dataclass coverage for both `WatchlistProjection` and `GapDetector`.

### Changed
- **EventBus**: Logging improvements for handler exceptions.
- **StreamManager**: Improved tick subscription and broadcasting.
- **Module wiring**: `bus_bridge.py` (regime + risk), `ws_bridge.py`, `scanner_data.py` — wired into FastAPI lifespan.
- **Router consolidation**: auth, intelligence, execution, scanner, settings routers updated.

## [2026-07-30] - OAuth Consent Flow Fix: `consentAppId` + HTTP Method

### Fixed
- **Dhan OAuth Callback**: Removed `consentAppId` flow check (`pop_consent_flow`) that always failed — Dhan's callback only sends `tokenId`, never `consentAppId`. The CSRF-like flow check blocked every OAuth consent with `error=unknown_flow`.
- **consume_consent HTTP Method**: Changed `client.get()` → `client.post()` to match Dhan API spec (`POST https://auth.dhan.co/app/consumeApp-consent`).
- **Tests**: Removed `test_dhan_callback_unknown_flow` (dead path); updated `test_dhan_callback_success` to omit `consentAppId`; fixed consume_consent tests to mock `client.post` instead of `client.get`.

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
