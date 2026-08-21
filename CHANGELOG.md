# ShettyXtreme Changelog

## v0.16.0 — Complete Frontend + Backend API Refactor (2026-08-13)

Suite: **1823 passed / 0 failed / 1 skipped** (was 1629 at Phase 2, 1012 at v0.12.0 baseline). Full-stack refactor: foundation, critical fixes, intelligence, and execution.

### Phase 1: Foundation (Consolidate + Extend)
- Added 8 missing shadcn-svelte primitives (alert, popover, switch, slider, sheet, progress, radio-group, collapsible)
- Introduced `/api/v2` namespace with versioned API contracts
- Migrated legacy Svelte stores to Svelte 5 runes
- Extracted App.svelte shell into modular router + layout components
- Version alignment across all files to 0.16.0

### Phase 2: Critical Features
- Fixed watchlist STALE state bug — seeded `lastSeenMs` from REST hydration timestamp, stamped `timestamp` on backend hydration, fixed tick-race condition
- Fixed option chain stale-expiry bug — cleared stale expiry on symbol change, stashed pre-load ticks in `pendingTicks`, added stale-response guard + 5s `live` recompute
- Fixed log drawer toggle — header button now drives `dockLogsTick` → `RightDockTabs` Logs tab activation; removed `display:none` gating
- Fixed SERP dropdown transparency — replaced hand-rolled list with portaled shadcn Popover (`z-50`), fixed invalid `var(--surface)` → `--canvas-raised`/`--surface-elevated`, removed 200ms blur hack
- Redesigned Research & Knowledge panels — shadcn Card/Tabs/ScrollArea/Badge, status/category filtering, skeleton loading, responsive container queries, design-token compliant

### Phase 3: Intelligence Features

#### Backend (3A)
- Scanner infrastructure: 11 scanners operational, configurable thresholds, WS alerts
- Hints → Proposals: one-click generation, accuracy tracking
- Analytics history: IV rank, PCR, max pain, regime time-series + export
- Greeks history: portfolio greeks recording

#### Frontend (3B)
- Scanner Panel: threshold config, WS alerts, history view
- Hints Panel: proposal generation, accuracy stats
- Analytics Panel: IV rank/PCR/max pain/regime charts, export
- Greeks Panel: greeks history charts, risk metrics

#### Integration (3C)
- Cross-panel integration
- Performance & UX polish

### Phase 4: Execution Features

#### Backend
- Order cancellation/export endpoints (`POST /api/execution/orders/{order_id}/cancel`, `GET /api/execution/orders/export?format=csv|json&days=30`)
- Position close/history endpoints (`POST /api/execution/positions/{symbol}/close`, `GET /api/execution/positions/history?days=30` via `TradeLedger` FIFO pairing)
- WebSocket topics: `proposal` (`created|approved|rejected|expired`) and `order` (`placed|filled|rejected|cancelled`) via `ProposalProjection`/`OrderWSProjection`
- Live P&L tracking — `PositionProjection` tick subscription + `LivePnlTracker` debounce (1s time gate + 1% noise gate), 5s broker sync loop
- Scanner→Proposal bridge — severity gate, scanner-type allowlist, per-(scanner,symbol) cooldown dedup (900s), `scanner_proposal_bridge` config (disabled by default), OBSERVER-first safety
- Durable proposal history — `_load_approvals()` restores ALL statuses (PENDING/APPROVED/REJECTED/EXPIRED), `pending_approvals` table as history, stale PENDING expiry on next listing

#### Frontend
- ProposalQueue: WS updates (subscribe `proposal` topic, lifecycle toasts, polling removed), history view (Active | History tabs, `status=APPROVED&REJECTED&EXPIRED` + date filters)
- RiskHeatmap: stress drill-down (Collapsible rows, per-position P&L table with impact bars, Indian convention coloring)
- OrderHistory: cancel (OPEN/PARTIALLY_FILLED → confirm Dialog → `POST .../cancel`), export (CSV/JSON + 7/30/90d → `Content-Disposition` download), WS updates (`order` topic + 10s polling fallback)
- PositionsRiskStrip: close (per-position close button → confirm Dialog → `POST .../close`), history (Open | History tabs, `GET .../history`), live P&L (WS `position` topic, 150ms row flash, JetBrains Mono numerals)

## [2026-08-12] — v0.15.0: Color Convention Toggle (P5 EXTERNAL)

Suite: **TBD passed / 0 failed / 0 skipped**. Price color convention is now configurable: **international (green=up, red=down) is the new default**; Indian (red=up, green=down) remains the legacy opt-in. Operators who never chose a convention will see flipped colors on upgrade — switch back in Settings with one click.

### Added
- **Color convention toggle** (`data-convention` attribute on `<html>`): two conventions — `international` (green=up, red=down, new default) and `indian` (red=up, green=down, legacy). Persisted via `sx-convention` localStorage + backend `SettingsStore`.
- **Backend endpoints**: `GET/PUT /api/settings/color-convention` (mirrors theme endpoints); WS broadcast to connected clients.
- **Settings UI**: segmented control "Price colors: Indian / International" in SettingsView, mirroring the Theme card.
- **Decoupled non-directional usages**: CE/PE badges, BUY/SELL badges, SL/TGT levels, FILLED status badge all use convention-independent tokens.

### Changed
- **BREAKING (visual)**: existing operators who never chose a convention see **international** colors (green=up, red=down) instead of Indian. Switch back to Indian in Settings → Price colors.
- `DESIGN.md` + `AGENTS.md` amended: convention is configurable, international is default.
- `RiskHeatmap.svelte`: hardcoded `rgba(246,82,92)`/`rgba(46,189,133)` replaced with CSS token-driven values.
- `OrderHistory.svelte`: FILLED badge changed from `price-down` to `success` (fixes existing DESIGN.md violation).

## [2026-08-06] — v0.14.0: Dashboard Redesign + Options Chain Fix

Suite: **1244 passed / 0 failed / 0 skipped** (was 1051 at v0.13.0). Dashboard overhaul: tabbed right dock eliminates overlapping frames, modern panel styling with subtle depth. Fixed options chain 500 error when expiry is empty.

### Added
- **Tabbed right dock** (`RightDockTabs.svelte`): replaces the stacked panels (ProposalQueue + ResearchPanel + KnowledgePanel + LogDrawer) with three tabs — Proposals, Research, Logs. Fixes the overlapping frames issue.
- **Modern panel styling**: 8px border-radius, subtle `box-shadow: 0 1px 3px rgba(0,0,0,0.4)` on rail, center, and right-dock panels. Keeps DESIGN.md constraints (flat color-block elevation, no gradients).
- **Redesigned dashboard plan** (`docs/superpowers/plans/2026-08-06-dashboard-redesign.md`).

### Fixed
- **Options chain 500 error**: `_expiry_epoch("")` raised `ValueError` when the frontend sent an empty `expiry` query parameter. Now omits the `timestamp` param when expiry is empty — Fyers returns the nearest expiry by default.
- Removed orphaned `.dock-stack` CSS rule from App.svelte (svelte-check warning).

### Changed
- **OPERATOR_MANUAL.md** updated: all Dhan references replaced with Fyers, connection instructions rewritten for Fyers App ID/Secret ID flow, error explanations updated.

## [2026-08-05] — v0.13.0: Phase 3 Cockpit Redesign + Phase 4 Lane A Quick Wins

Suite: **1051 passed / 0 failed / 0 skipped** (was 1016 at Lane A start). Phase 3: full cockpit UI redesign (commit `516b60d`) — pure black `#0a0a0a`/white palette with warm amber accent (Indian price convention preserved: red=up `#f6525c`, green=down `#2ebd85`), live WS streaming + keyboard nav across all panels. Phase 4 Lane A: six execution/security quick wins with regression tests.

### Added (Phase 3 cockpit redesign)
- Shell layout with right-col overlay drawer <1440px, header LTP hero, styled positions/risk strip (S1).
- Watchlist STALE chips + tick flash, ChainGrid live WS streaming + keyboard navigation (S2).
- ProposalQueue OBSERVER prominence + LIVE typed-confirm, ModeSwitcher `Ctrl+M` (S4).
- Scanner/Hints/Analytics regime badges + conviction levels + STALE chips (S5).
- Research/Knowledge/Settings/Logs toggle switches + keyboard nav (S6).

### Fixed (Phase 4 Lane A quick wins)
- **F-TERM-007**: legacy `POST /api/postback/dhan` now requires `Authorization: Bearer <stored Fyers access token>` — arbitrary unauthenticated payloads can no longer mint `ORDER_UPDATED` events into the ledger (401 without/with wrong token).
- **F-AUTH-002**: OAuth login CSRF closed — `start_auth` persists the `state` in an HttpOnly, Lax-samesite cookie scoped to the callback path; `fyers_callback` rejects missing/mismatched state with 400 before exchanging the auth code.
- **F-EXEC-004**: paper MARKET orders now fill at the last LTP from the data feed instead of `order.price` (0.0); without an LTP the order is rejected honestly — no more poisoned paper P&L / learning data.
- **F-CORE-003**: `PaperTradingEngine.get_pnl()` no longer raises `AttributeError` on the first fill (`Fill` carries no `pnl` field — guarded with `getattr`).
- **F-TERM-006**: weekday before 09:15 now reports "Market opens at 09:15 today" instead of "opens tomorrow".
- **F-KNOW-005**: `pair_fills` re-queues partial-fill remainders (FIFO preserved) instead of dropping them — a 30-qty close against a 75-qty entry leaves 45 queued for the next fill.
- **Version drift**: all five version files aligned to 0.13.0 (`__init__.py`, `app.py`, `pyproject.toml`, frontend `package.json`, `CHANGELOG.md`).

### Known
- Frontend bundle unchanged this release — the Phase 3 redesign bundle was committed in `516b60d`; Phase 4 Lane A is backend-only.

## [2026-08-05] — v0.12.0: Fyers Migration (Phase 1)

Suite: **1059 passed / 0 failed / 0 skipped**. Broker migration: Dhan → **Fyers** (ADR-008). `integration/dhan/` and `auth/dhan_oauth.py` deleted; `src/` is Dhan-free (grep-gated: zero `dhanhq`/`DhanTrading`/`DhanData` matches). Frozen rules FR-002/FR-003 and BOUNDARY-003 amended; ADR-007 superseded by ADR-008; ARCHITECTURE_V2 §11 rewritten as Fyers Integration.

### Added
- **Fyers REST transport** (`integration/fyers/client.py`): raw `httpx`, token-bucket throttle (~8/s), `Retry-After` backoff, error taxonomy (`FyersTokenExpired` on 401/-8/-15/-16/-17, `FyersDataEntitlementError` on 403/-373, `FyersRateLimitError` on 429).
- **Fyers session** (`session.py`): daily token lifecycle, `GET /profile` liveness probe, persist/load through the Fernet credential store.
- **Symbol resolver + instrument master** (`symbols.py`, `instrument_master.py`): internal names ↔ Fyers tickers with the weekly month-code (`1-9/O/N/D`) handling, exact-match master validation (the `-300` gotcha gate), public master download → SQLite.
- **Fyers order socket** (`ws_client.py`): JSON order WS (`SUB_ORD`), 10s heartbeat, exponential backoff, 403-handshake → re-auth trigger — replaces Dhan postback webhooks; `postback_router.py` now bridges order-socket frames to `ORDER_UPDATED` (legacy HTTP path kept for the migration window).
- **Fyers data socket** (`data_socket.py`): supervised SDK HSM socket wrapper with restart backoff; token-expiry codes 11001/-99 surfaced as `FyersTokenExpired`.
- **Fyers adapters** (`trading_adapter.py`, `data_adapter.py`): implement `OrderExecutor`/`AccountInfo`/`MarketDataStream`/`DataProvider` (zero Protocol changes); history chunking (≤100d/req intraday, ≤366d daily), client-side bar aggregation, options chain with greeks.
- **Fyers auth**: `auth/fyers_oauth.py` OAuth2 authorization-code helper, broker-discriminated credential store (`app_id`/`secret_id`), `/auth/fyers/callback` exchange, 60s health monitor + pre-market probe, validator → `/profile`.
- **Terminal wiring**: `terminal_init.py` builds the Fyers adapter stack, bridges ticks onto the EventBus, and subscribes the order socket; routers de-Dhaned (market, watchlist, intelligence).
- **Fyers instrument-master tests**: `tests/integration/` — client, session, symbols, instrument master, mappings, WS client, data socket, and adapter unit tests (mock transport, no network).

### Removed
- `integration/dhan/` (trading + data adapters), `auth/dhan_oauth.py`, Dhan wire-format tests (`test_dhan_trading_adapter.py`, `test_dhan_data_adapter.py`), shared Dhan `integration/instrument_master.py`, `dhanhq` dependency, `tests/terminal/conftest.py` dhanhq mock.

### Fixed
- `stream_manager.py` Dhan feed coupling removed; the market-data bridge now runs through the Fyers data adapter.
- `configs/default_watchlist.yaml` holds internal symbols (was Dhan numeric security IDs).
- Version drift resolved: all five version files at 0.11.0.

### Known
- Fyers token TTL is unpublished — daily interactive re-auth is the reliable path; the pre-market `/profile` probe is authoritative.
- Data socket relies on the `fyers-apiv3` SDK (HSM protocol) — pinned with `--no-deps`; REST + order WS are raw and SDK-free.
- No Fyers sandbox — real account, OBSERVER-first, small notionals.

## [2026-08-02] — v0.11.0: Trades Ledger + Knowledge v2 + Hygiene Wave

Suite: **732 passed / 0 failed / 0 skipped** (was 703). Three tracks: the trades-ledger recording track that unblocks net-EV scoring (ticket 06), knowledge v2 (operator notes + tag refinement), and the deferred-minors hygiene wave.

### Added
- **Trades ledger** (`execution/ledger.py`): sqlite `TradeLedger` — idempotent fills on `(order_id, source)`, FIFO opposite-side `pair_fills` (long and short, partial remainders dropped with a noted follow-up), `per_session_summary` (fills/gross notional/realized PnL).
- **Ledger recording** (`execution/ledger_recorder.py`): subscribes `ORDER_FILLED` (paper, full order details) and `ORDER_UPDATED` (Dhan postbacks, status-gated FILLED/TRADED/COMPLETE with `filled_quantity>0`; symbol/side recorded NULL). Wired in lifespan → `app.state.trade_ledger` + `app.state.current_session_id`.
- **Ledger API**: `GET /api/analytics/ledger` (fills + per-session aggregates); scorecard gains `fills` and `net_ev_per_session` metrics (`available:false` until closed fill pairs exist — honesty convention; cost = `_COST_PER_FILL` 25.0 = brokerage 20 + slippage 5, matching strategy_hints defaults). AnalyticsPanel renders them via the generic metric cards — no frontend change.
- **Knowledge v2**: `knowledge/notes.py` operator-note ingest (kind `operator_note`, status `proposed`, heuristic-tagged, human-activated via the existing gate — D12 imports core only); `POST /api/knowledge/notes`; symbol aliases (`SYMBOL_ALIASES`: BANK/BNF→BANKNIFTY, FIN→FINNIFTY, MIDCAP→MIDCPNIFTY, NIFTYNEXT50→NIFTYNXT50) + deterministic `(kind, tag)` tag ordering; KnowledgePanel note composer (DESIGN.md tokens, svelte-check 0 errors, bundle committed).

### Fixed (hygiene wave)
- `sqlite3.connect(..., timeout=5.0)` on all four stores (research, knowledge, sessions, execution-approvals) — kills the scheduler-tick ↔ manual-run contention on `data/research.db`.
- Research router tests: module-global snapshot/restore fixture (no cross-test `RESEARCH_DB_PATH`/`_ORCHESTRATOR` leakage).
- `.gitignore` now un-ignores `__init__.py` (`!**/__init__.py` after `_*.py`) — no more force-add workaround.
- `regime_at_decision` normalized to lowercase enum values at decide time (projection can carry the uppercase enum name).
- `AlertProjection` suppresses duplicate alerts within a 30s window (scanner alert spam).
- `chain_snapshot` research tool now renders watchlist LTP/change via `ProjectionDataSource.chain_summary`; `options_posture` stays `[UNSOURCED]` honestly.

### Known
- `pair_fills` drops partial-fill remainders (not re-queued) — follow-up noted before live usage.
- Postback fills carry NULL symbol/side (unknowable at the postback surface) — excluded from pairing by the `symbol IS NOT NULL` guard, so they never contribute spurious realized PnL until symbol resolution ships.
- Deferred minors retained: polyline-vs-step chart (documented deliberate deviation), read-endpoint DB auto-create (consistent with ResearchStore pattern), `test_knowledge_api` module-state teardown.

### Cleanup
- Removed dead code: stale pre-Svelte React scaffold (root `terminal/ui/`), empty `PLAN 2307.md`, 7 one-off doc-generator scripts (kept `sync_vendor.py` + `research_smoke.py`), empty packages `risk/`/`plugins/`/`observability/` (real RiskEngine lives in `intelligence/risk/`), `print("hello")` stub `options/spreads/spread_analyzer.py`, empty `experiments/` dir.
- Archived two superseded handoffs into `docs/superpowers/handoffs/` (`2026-07-23-session-record.md`, `2026-07-30-credential-consolidation.md`).
- Smoke-verified: `run.py --mode OBSERVER` boots clean — `/api/health` 200 (Dhan down = expired token, re-auth at `#/settings`), scorecard shows 13 logged sessions, ledger/knowledge/research endpoints live.

## [2026-08-01] — v0.10.0: Phase 4 Knowledge Layer (D12) + Analytics Dashboards

Suite: **703 passed / 0 failed / 0 skipped** (was 655). D12 knowledge layer v1 — FTS5 document store for decided research briefs, heuristic tagger, human-gated activation wired to a `knowledge_search` research tool — plus scorecard-core dashboards with a recording track (SessionLog + regime-at-decision). All decisions from the Phase 4 wayfinder map (`.scratch/phase4-knowledge-dashboards/`); multi-broker and backtest depth DECIDED-DEFER.

### Added
- **Knowledge store** (`knowledge/store.py`): sqlite3 + FTS5 (stdlib, verified compiled in) — `docs`/`tags`/FTS5 external-content tables with sync triggers, `bm25` ranking + `snippet()`, tag/status filters, idempotent ingest by `source_ref`, idempotent activation. Zero new deps.
- **Lexicons** (`core/knowledge/lexicons.py`): curated NSE symbols + regime terms (mapped to lowercase `Regime` enum values) + risk-theme lexicon + symbol stopwords; pure data, no shettyxtreme imports.
- **Heuristic tagger** (`knowledge/tagger.py`): symbols/regimes/risk themes at word boundaries, phrase-first matching, dedup, 50-tag cap. No LLM anywhere in knowledge/ (D3).
- **Ingest contract** (`knowledge/ingest.py`): decided briefs only (approved/rejected with `decided_at`), protocol-decoupled (`ResearchBriefLike` — knowledge/ never imports research/), duplicate counting.
- **Knowledge API** (`/api/knowledge/*`): `search` (FTS5), `docs`, `status`, `sync` (the only research↔knowledge meeting point), `docs/{id}/activate`; WS topic `knowledge` (`activated` event); `KnowledgePanel.svelte` (search → review → activate → sync).
- **Research tool wiring**: `knowledge_search` tool + `DataSource.knowledge_summary` — activated knowledge becomes a mid-run research source (`[UNSOURCED]` fallback intact).
- **Recording track**: `learning/sessions.py` `SessionLog` (sessions written at lifespan start/stop); `ResearchBrief.regime_at_decision` (harness-owned, recorded at decide time from the intelligence projection, surfaced on responses).
- **Analytics API** (`/api/analytics/*`): `scorecard` (sessions/decisions/win-rate/avg-confidence + per-regime rows + calibration passthrough; `available:false` + honest notes; never 500) and `sessions`; `AnalyticsPanel.svelte` — scorecard cards, plain-SVG calibration step-chart (zero charting deps, XSS-safe numeric interpolation), per-regime bars.
- **api.ts**: knowledge + analytics types, `postBody` reuse; both panels mounted in the terminal.

### Security
- D12 import gate enforced + tested: `knowledge/` imports core ONLY (verified by review); FTS5 MATCH queries quoted (no injection surface); SVG interpolates numbers only; no LLM output in the knowledge/analytics path.

### Known
- `chain_snapshot`/`options_posture` tools still render `[UNSOURCED]` (Phase-4 renderers pending — knowledge_search now covers the archive path).
- Read endpoints auto-create their DB files on first read (consistent with the ResearchStore pattern; `_fit_calibration` keeps its exists() guard).
- Scorecard metrics other than calibration stay `available: false` until real sessions/outcomes accumulate; net-EV-per-session + cost analysis deferred (no trades ledger exists — ticket 06 recorded).
- Calibration chart renders as a polyline (documented deviation from "step chart" — reads better with few points).
- Regime strings stored verbatim at decide time (runtime path already lowercase enum values; future normalization noted).
- Wayfinder map fully resolved (8/8 tickets); multi-broker + backtest depth deferred with triggers recorded.

## [2026-08-01] — v0.9.0: Phase 3C Research Workspace Full Surface

Suite: **655 passed / 0 failed / 0 skipped** (was 612). Read-only data tools with mid-run function calling, env-config scheduler, richer terminal research panel with WS live updates, brief outcome scoring + `decided_at`. Also shipped: the hygiene wave (3 recurring skips fixed — suite is now permanently 0-skipped; registry→engine shadow wiring; 3A deferred minors).

### Added
- **Read-only tool registry** (`research/tools.py`): 4 tools (`chain_snapshot`, `regime_snapshot`, `scanner_alerts`, `options_posture`) — single source for both function-calling and `GET /api/research/tools`; injectable `DataSource` protocol (research/ never imports terminal/); missing data renders `[UNSOURCED]`, never fabricated.
- **Provider v2** (`research/provider.py`): `generate()` returns `ProviderResponse {content, tool_calls}` and accepts `tools` + `history`; DeepSeek parses OpenAI-format `tool_calls`; `SimulatedProvider` gains scriptable tool-call flows. Deliberate interface bump — all wave8 provider tests migrated.
- **Bounded tool loop** (`research/orchestrator.py`): ≤3 tool calls per lens (`MAX_TOOL_CALLS`), budget exceeded → per-lens error (never auto-advance), tool failures recover as `TOOL ERROR:` results, retries rebuild a fresh conversation; `on_brief` callback enables WS broadcast; no-tools path byte-identical to 3B.
- **Scheduler** (`research/scheduler.py`): env-config only (`RESEARCH_SCHEDULE_ENABLED`/`INTERVAL_MINUTES`/`LENSES`/`TOOLS`), default off, not started without `DEEPSEEK_API_KEY`, tick failures logged and never crash the app; `GET /api/research/scheduler` status.
- **Scoring + decided_at**: `ResearchBrief.decided_at` (harness-owned, not model-authorable) surfaced on every response; `POST /api/research/briefs/{id}/outcome` (`WIN`|`LOSS`; 400 invalid, 404 unknown, 409 on undecided); `GET /api/research/scoring` per-lens aggregates (total/decided/with_outcome/win_rate/avg_confidence, empty DB → `[]`).
- **Terminal panel + WS**: `ResearchPanel.svelte` + `ResearchBriefDetail.svelte` (run bar with lens/tool selection, filterable brief list, detail view with evidence + `[UNSOURCED]` flags, approve/reject card); WS topic `research` (`new_brief`/`decision`) via `init_research(broadcast_fn)`; `ProjectionDataSource` wires live regime/alerts into tools.
- **api.ts**: `postBody<T>` + typed research models.

### Security
- No test calls the real DeepSeek API (transport stubbed where the call-time key path is exercised); key env-only, read at call time, never logged; tools are read-only — no order tool exists in the registry.

### Known
- `chain_snapshot`/`options_posture` render `[UNSOURCED]` in real runs until Phase-4 renderers exist (honest best-effort per spec).
- Two sqlite connections to `data/research.db` (scheduled tick + manual run) can contend — degrades to per-lens `persist failed`, never a crash; a `timeout=` on connect is a future hardening.
- Live smoke validated: 3-lens run + `/run` with tools + real function-calling contract (`chain_snapshot(NIFTY)` parsed). DeepSeek `json_object` mode requires the word "json" in the prompt — all lens prompts satisfy this; ad-hoc prompts must too.
- Critic model pass deferred until order intents exist (unchanged).

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
