# 06 — Analytics data plumbing inventory

Type: task
Status: resolved
Blocked by:

## Question

What is actually queryable today for the scorecard-core metrics? Produce a data-source inventory.

Walk the codebase (read-only): which stores/endpoints expose sessions logged, per-session outcomes (net EV, cost), win rate by regime, calibration curve points + reliability. For each scorecard metric: source (module/table/endpoint), fields available, gaps (e.g. cost drag not captured anywhere), and whether a metric is computable with zero new plumbing.

Deliverable: inventory table appended to this ticket under `## Answer` with the gaps flagged — ticket 05 consumes it. Do not modify code.

## Answer

Inventory — walk of `src/` (read-only, verified vs `data/` on disk). Core finding: every scorecard metric has a *library* but **zero runtime plumbing** — OutcomeTracker, ShadowManager, AnalyticsEngine, WalkforwardEvaluator have no callers outside tests + the read-only router; `data/learning.db` / `data/shadow.db` are never created, so all analytics endpoints return empty today.

| Metric | Source (module/table/endpoint) | Fields available | Gaps | Computable today? |
|---|---|---|---|---|
| Sessions logged | `data/shadow.db` → `shadow_sessions` (ShadowManager, `intelligence/signals/shadow_manager.py`) — per-voter rows keyed by `session_date` | session_date, shadow_name, outcome, was_correct, signal_id; `/api/learning/shadows` exposes sessions/evaluated/hit_rate/graduated | Write path never invoked in src/; no session-log table for main decisions; `/api/health/session` is market-open status, not analytics | **No** |
| Per-session outcomes / net EV (cost-aware) | `learning/walkforward.py` (WalkforwardEvaluator): TP1-3/TSL/EOD exit sim × `compute_cost` (LOT_SIZE 75) → total_return, win_rate, avg_win/loss, sharpe, max_dd, cost_adjusted_return, per_voter, per_regime | All aggregates incl. net-of-cost | No runtime caller; results never persisted (no report file/DB); raw PnL per decision not stored | **No** (library only) |
| Win rate by regime | `learning/analytics.py` (AnalyticsEngine: signal_quality_by_regime, win_loss_by_regime); `walkforward.py` per_regime | regime (from `strategy_hint.regime`, defaults RANGE_BOUND), total_signals, win_rate, wins/losses, avg_conviction, avg_ev | No runtime caller, no endpoint; regime attribution relies on strategy_hint recorded at decision time (absent for old data) | **No** (library only) |
| Calibration curve + reliability | `learning/calibration.py` (CalibrationCurve: 10 bins, Wilson CI, reliable >30); `GET /api/learning/calibration` → `{reliable, points[]}` | conviction_bin, actual_win_rate, sample_size, confidence_interval | Endpoint exists and reads `data/learning.db` — but DB is empty (never written); no endpoint for raw decisions | **Yes** (endpoint live, empty data) |
| Trades ledger | **None.** Fills (`execution/paper_trading.py`) and postbacks (`/api/postback/dhan`) only publish ORDER_FILLED/ORDER_UPDATED bus events; `execution_attempts` table exists in learning.db but is never written; `/api/execution/positions` is live Dhan fetch (no history) | Order/Fill/Position dataclasses in `core/data_models/orders.py` | No order/trade/position history store anywhere | **No** |

API surface available to dashboards: `/api/learning/calibration`, `/api/learning/shadows`, `/api/intelligence/{regime,signal,voters,options,strategy-hint}`, `/api/execution/{positions,risk,mode,kill-switch}`, `/api/research/{scoring,briefs}`. No endpoints for sessions, per-session EV, walkforward, or trade history. Other stores: `data/shetty_ts.db` (duckdb bars/ticks), `data/shetty_kv.db` (kv), `data/research.db` — none hold decision/outcome data.

Gaps for ticket 05:
1. **No data flows**: learning loop (record decision → execution attempt → outcome) is unwired from run flow — writing decisions is new plumbing, not just a query.
2. **No executed-trades ledger** — fills/postbacks are event-only; real net EV per session (vs simulated) impossible.
3. **No session entity** — "sessions" exist only as `shadow_sessions.session_date` (unwritten); scorecard sessions metric needs a session table.
4. **Walkforward output is transient** — computed in-memory, never persisted; also `cost_adjusted_return == total_return` (cost folded into net, not a separate field).
5. **Cost drag is approximated everywhere** — `AnalyticsEngine.cost_analysis` counts execution attempts as cost proxy; only walkforward applies real `compute_cost` (entry-side only).

