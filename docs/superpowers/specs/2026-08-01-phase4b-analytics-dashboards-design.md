# Phase 4B — Analytics Dashboards + Recording Track: Design Spec

**Date:** 2026-08-01 · **Status:** APPROVED (wayfinder tickets 05–06) · **Branch:** phase4 from master · **Map:** `.scratch/phase4-knowledge-dashboards/map.md`

## 1. Purpose

Ship the scorecard-core dashboards v1 in the terminal: calibration curve rendered from real data now, honest DESIGN.md-styled empty states for metrics with no data yet, plus a small **recording track** so the scorecard fills with real data over time — SessionLog (sessions written at lifespan start/stop) and `regime_at_decision` recorded at decide time. Zero new charting deps (plain SVG/CSS).

## 2. Binding constraints

- Zero new runtime deps; charts are plain SVG/CSS using DESIGN.md tokens (JetBrains Mono tabular numerals, one accent, red-up `#f6525c` / green-down `#2ebd85`).
- ≤500 lines/file; suite never shrinks, **0 skipped**; grep gate zero; test runner `.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=... -p no:cacheprovider` with `PYTHONPATH=""`.
- New tests in `tests/wave9/`.
- No LLM involvement anywhere in this track (D3).
- Never stage `AGENTS.md`, `.opencode/opencode.json`, `docs/superpowers/plans/2026-07-31-graphify-upgrade.md`.

## 3. Grounding (ticket 06 inventory — verified)

- **Calibration:** `GET /api/learning/calibration` → `{reliable: bool, points: [{conviction_bin: [lo,hi], actual_win_rate, sample_size, confidence_interval: [lo,hi]}]}` — computable today (empty payload when no DB yet).
- **Sessions logged:** NONE at runtime → new SessionLog.
- **Per-session outcomes / net EV:** library-only (`WalkforwardEvaluator`, tests only) → NOT in v1; empty state + follow-up note.
- **Win rate by regime:** needs regime at decision time → new `regime_at_decision` recording.
- **Trades ledger:** none → out of scope for v1 scorecard (empty state).

## 4. Design

### 4.1 SessionLog (`learning/sessions.py`)

- `SessionLog(db_path: str)` — sqlite `sessions` table: `session_id TEXT PK, started_at TEXT, ended_at TEXT, mode TEXT ('OBSERVER'|'LIVE')`.
- `start(mode: str) -> str` (session_id, `started_at=now`), `end(session_id) -> None` (sets `ended_at`; unknown id → no-op), `list(limit: int = 100) -> list[dict]`, `counts() -> dict` (`{total, open, live, observer}` — open = no ended_at), `close()`.
- File-level write per call (never hold a connection across requests — ResearchStore pattern is fine but sessions are tiny; use per-call connection for robustness: simplest is a single connection like ResearchStore; spec: single connection, commit per op).
- `learning/` imports core only (no change to existing rule) — sessions.py uses stdlib sqlite3 + datetime only.
- **Wiring (terminal layer):** `app.py` lifespan start: `session_id = session_log.start(mode)` where mode comes from the runtime mode (OBSERVER default; read from config/`run.py` mode — use `os.environ.get("SHETTY_MODE", "OBSERVER")`? The mode lives in execution mode manager. Keep simple: `mode` param recorded from the app's runtime mode via `execution` mode state if reachable, else `"OBSERVER"` — spec: read `app.state.mode` if set, else `"OBSERVER"`). Teardown: `session_log.end(session_id)`. Store instance on `app.state.session_log`.

### 4.2 regime_at_decision (`research/briefs.py` + `research/store.py`)

- `ResearchBrief` gains `regime_at_decision: str | None = None` — harness-owned (NOT in `MODEL_AUTHORED_FIELDS`, like `decided_at`).
- `store.decide(brief_id: str, decision: str, regime: str | None = None)` — writes `regime_at_decision` into the payload alongside `decided_at`.
- Router `_decide` (integration pass): reads current regime from `request.app.state.intelligence_projection.get_regime()` → `regime.get("regime")` and passes it. (Existing callers of `store.decide` without regime keep working — optional param.)
- Scoring: `store.scoring()` unchanged (per-lens); the scorecard endpoint derives by-regime from payloads directly.

### 4.3 Scorecard aggregation (`terminal/api/analytics_router.py` + `analytics_models.py`)

Models in NEW `terminal/api/analytics_models.py` (keeps `models.py` untouched → disjoint waves):
- `ScorecardMetricResponse` — `{key: str, label: str, value: str | float | None, unit: str | None, available: bool, note: str | None}`.
- `RegimeRowResponse` — `{regime: str, decided: int, with_outcome: int, win_rate: float}`.
- `ScorecardResponse` — `{reliable_calibration: bool, metrics: list[ScorecardMetricResponse], by_regime: list[RegimeRowResponse], calibration: list[CalibrationPointResponse]}`.
- `SessionsResponse` — `{sessions: list[dict], counts: dict}`.

Endpoints (`/api/analytics`, tag `analytics`):
- `GET /api/analytics/scorecard` — assembles (terminal layer may read research store + session log + calibration):
  - metrics: `sessions_total`, `sessions_open`, `decisions` (decided briefs count), `with_outcome`, `win_rate` (WIN/with_outcome), `avg_confidence` (decided briefs), `calibration_reliable` — each with `available: bool` (data present?) + honest `note` (e.g. "no sessions recorded yet — runs automatically at terminal start/stop").
  - `by_regime`: GROUP BY `regime_at_decision` over decided briefs with outcomes (win_rate per regime).
  - `calibration`: passthrough from `/api/learning/calibration` logic (reuse `_fit_calibration` — import from learning_router? Better: move/duplicate the fit call — spec: analytics_router imports `_fit_calibration` from `learning_router` (same package, no circularity risk) or reads CalibrationStore directly; pick: call `_fit_calibration(LEARNING_DB_PATH)` via import from learning_router — both in terminal/api).
  - Empty everything → 200 with `available: false` metrics (never 500).
- `GET /api/analytics/sessions?limit` — session log rows + counts; missing DB → `{sessions: [], counts: {...zeros}}`.

### 4.4 Panel (`terminal/web/src/components/AnalyticsPanel.svelte`)

- **Scorecard cards row:** sessions total + open, decisions, win rate, avg confidence — each a card with label (Inter, muted), value (JetBrains Mono tabular), and `no data` state when `available: false` (dashed border + note tooltip/title).
- **Calibration chart:** plain SVG — step chart over `conviction_bin` midpoints vs `actual_win_rate`, points sized by `sample_size`, CI whiskers, diagonal reference line, reliability badge ("reliable"/"insufficient data"). SVG computed in script (no lib).
- **By-regime bars:** simple CSS horizontal bars (width % = win_rate) per regime row with count labels.
- Auto-load on mount + manual refresh; no WS needed (data is daily-slow) — refresh button only.
- api.ts: analytics types (`ScorecardResponse`, `SessionsResponse`).
- Mount: below ResearchPanel in the right column? The right column is already dense; mount AnalyticsPanel in the center column under ChainGrid/HintsPanel? Spec: mount in `.center` under HintsPanel (charts need width). DESIGN.md compliance pass.

## 5. Data flow

```
lifespan: SessionLog("data/sessions.db") → start(mode) → app.state.session_log
POST /api/research/briefs/{id}/approve|reject → _decide(..., regime=proj.regime) → store.decide writes regime_at_decision
GET /api/analytics/scorecard → sessions counts + research store aggregates + regime rows + calibration
GET /api/analytics/sessions → session log rows
AnalyticsPanel (onMount) → GET scorecard + calibration → SVG step chart + cards + regime bars
```

## 6. Error handling

- Missing DBs everywhere → 200 with zeros/empty + `available: false`; never 500.
- `decide` regime param optional — no caller breaks.
- SessionLog unknown end id → no-op.
- SVG rendering with zero points → render empty-state message (no divide-by-zero).

## 7. Excluded / deferred

- Net-EV-per-session + cost analysis (needs runtime outcome recording of executed trades — no ledger exists; ticket 06 recorded; follow-up phase).
- Portfolio heatmap, walkforward explorer surfaces.
- Session/outcome recording from LIVE executions (postback → ledger) — separate future track.
- Multi-broker + backtest depth (tickets 07/08 — DECIDED-DEFER).

## 8. Delivery

Same branch/wave protocol as 4A; both tracks merge as Phase 4 (v0.10.0) — docs (CHANGELOG v0.10.0, roadmap §17 Phase 4 row, README), merge + push presented.
