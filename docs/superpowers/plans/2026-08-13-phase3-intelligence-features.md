# Phase 3: Intelligence Features Implementation Plan

**Date:** 2026-08-13  
**Status:** Planning  
**Scope:** Scanner (3.1), Hints (3.2), Analytics (3.3), Greeks (3.4) panels  
**Dependency:** Backend work must complete before frontend enhancements

---

## Executive Summary

Phase 3 delivers professional-grade intelligence features across 4 panels. Backend audit reveals **12 missing endpoints** and **5 partial implementations** that must be addressed before frontend work.

**Key gaps:**
- Scanner: 8 of 11 scanners never run (Tier-B poller not started), no configurable thresholds, no WS alerts
- Hints: no one-click proposal generation, no accuracy tracking
- Analytics: no history endpoints for IV rank/PCR/max pain/regime charts, no data export
- Greeks: no greeks history for visualization

---

## Phase 3A: Backend Foundation (Priority: Critical)

### Task 3A.1: Scanner Infrastructure
**Goal:** Make all 11 scanners operational and configurable

**Backend work:**
1. Start `_scanner_poller_task` in `app.py` lifespan — poll chain every 15s, call `scan()` on all Tier-B scanners
2. Add scanner threshold configuration to `SettingsStore`:
   - Schema: `scanner_thresholds: dict[str, dict[str, float]]` (scanner_type → param_name → value)
   - Endpoints: `GET/PUT /api/settings/scanner-thresholds`
   - Wire thresholds into `instantiate_scanners()` in `app.py`
3. Add `scanner_finding` WebSocket topic:
   - `ScannerProjection.on_scanner_finding` → broadcast via `ws_bridge`
   - Frontend subscribes to `scanner_finding` topic
4. Persist scanner findings to SQLite:
   - New table: `scanner_findings` (id, scanner_type, symbol, severity, detail_json, timestamp)
   - Endpoint: `GET /api/scanner/findings/history?scanner_type=&limit=&since=`
   - Replace in-memory ring buffer with DB-backed storage

**Files:**
- `src/shettyxtreme/terminal/api/app.py` (lifespan, scanner instantiation)
- `src/shettyxtreme/core/settings.py` (scanner_thresholds field)
- `src/shettyxtreme/terminal/api/settings_router.py` (new endpoints)
- `src/shettyxtreme/terminal/projections.py` (ScannerProjection broadcast)
- `src/shettyxtreme/intelligence/scanners/` (ensure all accept threshold kwargs)
- New: `src/shettyxtreme/terminal/api/scanner_store.py` (SQLite persistence)

**Tests:**
- `tests/terminal/test_scanner_poller.py` (poller starts, calls scan())
- `tests/terminal/test_scanner_thresholds.py` (settings read/write)
- `tests/terminal/test_scanner_ws_broadcast.py` (WS topic fires)
- `tests/terminal/test_scanner_history.py` (DB persistence)

**Estimated effort:** 2-3 days

---

### Task 3A.2: Hints → Proposal Generation
**Goal:** Enable one-click proposal creation from hints

**Backend work:**
1. Add `POST /api/intelligence/propose-from-hint` endpoint:
   - Accepts: `{symbol, direction, strike, premium, expiry, option_type, lot_size, lots, stop_loss, target, rationale}`
   - Creates proposal via `ExecutionEngine.submit_signal()` with `source="manual_hint"`
   - Returns: `ProposalResponse`
2. Add `strategy` field to `StrategyHintResponse` model (currently omitted)
3. Add hint accuracy tracking:
   - New table: `hint_outcomes` (hint_id, symbol, direction, strike, suggested_at, outcome, actual_pnl, recorded_at)
   - Endpoint: `GET /api/intelligence/hint-stats?days=30` → win_rate, avg_pnl, sample_size
   - Record outcome when position closes (hook into `PositionProjection.on_position_close`)

**Files:**
- `src/shettyxtreme/terminal/api/intelligence_router.py` (propose-from-hint, hint-stats)
- `src/shettyxtreme/terminal/api/models.py` (StrategyHintResponse.strategy field)
- New: `src/shettyxtreme/terminal/api/hint_store.py` (SQLite persistence)
- `src/shettyxtreme/terminal/projections.py` (PositionProjection outcome recording)

**Tests:**
- `tests/terminal/test_propose_from_hint.py` (proposal creation)
- `tests/terminal/test_hint_stats.py` (accuracy tracking)

**Estimated effort:** 1-2 days

---

### Task 3A.3: Analytics History Endpoints
**Goal:** Expose time-series data for IV rank, PCR, max pain, regime charts

**Backend work:**
1. IV rank history:
   - Endpoint: `GET /api/analytics/iv-rank-history?symbol=&days=30`
   - Source: `IVRankCalculator._snapshots` (already stores timestamped IVSnapshot deque)
   - Response: `[{timestamp, iv_rank_percent, iv_classification}]`
2. PCR history:
   - Endpoint: `GET /api/analytics/pcr-history?symbol=&days=30`
   - Source: `OITracker._snapshots` (already stores OISnapshot list)
   - Response: `[{timestamp, pcr, total_call_oi, total_put_oi}]`
3. Max pain history:
   - New recording: capture max pain on every chain poll (in `IntelligenceProjection.on_market_data` or chain endpoint)
   - New table: `max_pain_history` (symbol, expiry, max_pain, timestamp)
   - Endpoint: `GET /api/analytics/max-pain-history?symbol=&days=30`
   - Response: `[{timestamp, max_pain, spot_price}]`
4. Regime history:
   - New recording: capture regime on every regime change (in `IntelligenceProjection.on_regime`)
   - New table: `regime_history` (regime, confidence, adx, timestamp)
   - Endpoint: `GET /api/analytics/regime-history?days=30`
   - Response: `[{timestamp, regime, confidence, adx}]`
5. Data export:
   - Endpoint: `GET /api/analytics/export?format=csv&days=30`
   - Exports: scorecard metrics, regime history, IV rank, PCR, max pain as CSV/JSON
   - Response: file download (Content-Disposition: attachment)

**Files:**
- `src/shettyxtreme/terminal/api/analytics_router.py` (5 new endpoints)
- `src/shettyxtreme/intelligence/iv_rank.py` (expose _snapshots via method)
- `src/shettyxtreme/options/oi_tracker.py` (expose _snapshots via method)
- `src/shettyxtreme/terminal/projections.py` (max pain + regime recording)
- New: `src/shettyxtreme/terminal/api/analytics_store.py` (SQLite for max_pain_history, regime_history)

**Tests:**
- `tests/terminal/test_iv_rank_history.py`
- `tests/terminal/test_pcr_history.py`
- `tests/terminal/test_max_pain_history.py`
- `tests/terminal/test_regime_history.py`
- `tests/terminal/test_analytics_export.py`

**Estimated effort:** 2-3 days

---

### Task 3A.4: Greeks History Endpoint
**Goal:** Enable greeks visualization charts

**Backend work:**
1. New recording: capture portfolio greeks on every position change or chain poll
   - Hook: `PositionProjection.on_position_update` + chain endpoint
   - New table: `greeks_history` (net_delta, net_gamma, net_theta, net_vega, position_count, timestamp)
2. Endpoint: `GET /api/execution/greeks-history?days=7`
   - Response: `[{timestamp, net_delta, net_gamma, net_theta, net_vega, position_count}]`
3. Optional: per-position greeks history (lower priority, larger storage)

**Files:**
- `src/shettyxtreme/terminal/api/execution_router.py` (greeks-history endpoint)
- `src/shettyxtreme/terminal/projections.py` (greeks recording)
- New: `src/shettyxtreme/terminal/api/greeks_store.py` (SQLite persistence)

**Tests:**
- `tests/terminal/test_greeks_history.py`

**Estimated effort:** 1 day

---

## Phase 3B: Frontend Enhancements (Priority: High)

### Task 3B.1: Scanner Panel UI
**Goal:** Professional scanner UI with configurable thresholds and real-time alerts

**Frontend work:**
1. Add threshold configuration UI:
   - Settings modal or inline editor per scanner type
   - Calls `PUT /api/settings/scanner-thresholds`
   - Shows current values, allows edit, saves
2. Subscribe to `scanner_finding` WebSocket topic:
   - Real-time alert badges/notifications when new findings arrive
   - Auto-scroll to latest finding
3. Add alert history view:
   - Tab: "Active" (current findings) / "History" (past 7 days)
   - Calls `GET /api/scanner/findings/history`
   - Filterable by scanner_type, severity, symbol
4. Enhance finding cards:
   - Severity badge with conviction level (already present)
   - Expandable detail section (show all detail fields, not just first 2)
   - "Create proposal" button for actionable findings (future integration with 3B.2)

**Files:**
- `src/shettyxtreme/terminal/web/src/components/ScannerPanel.svelte`
- `src/shettyxtreme/terminal/web/src/lib/api.ts` (new types + functions)

**Estimated effort:** 2 days

---

### Task 3B.2: Hints Panel UI
**Goal:** One-click proposal generation and accuracy tracking

**Frontend work:**
1. Add "Create Proposal" button:
   - Visible when hint is actionable (direction != neutral, strike/premium present)
   - Calls `POST /api/intelligence/propose-from-hint`
   - Shows success toast, navigates to Proposals tab
2. Add accuracy stats card:
   - Shows: win_rate, avg_pnl, sample_size (from `GET /api/intelligence/hint-stats`)
   - "Last 30 days" label
   - Muted if sample_size < 10
3. Enhance hint card:
   - Show `strategy` name (now available from backend)
   - Show confidence as percentage bar
   - Show SL/TP levels visually (horizontal line markers on a mini-chart?)

**Files:**
- `src/shettyxtreme/terminal/web/src/components/HintsPanel.svelte`
- `src/shettyxtreme/terminal/web/src/lib/api.ts` (propose-from-hint, hint-stats)

**Estimated effort:** 1-2 days

---

### Task 3B.3: Analytics Panel UI
**Goal:** Professional analytics dashboard with charts and export

**Frontend work:**
1. IV Rank chart:
   - Line chart: IV rank % over time (0-100% scale)
   - Horizontal bands: LOW (<20), NORMAL (20-30), HIGH (>30)
   - Current value marker
   - Calls `GET /api/analytics/iv-rank-history`
2. PCR chart:
   - Line chart: PCR over time
   - Horizontal bands: OVERSOLD (<0.7), NEUTRAL (0.7-1.2), OVERBOUGHT (>1.2)
   - Current value marker
   - Calls `GET /api/analytics/pcr-history`
3. Max Pain chart:
   - Line chart: max pain vs spot price over time
   - Two lines: max_pain (dashed), spot (solid)
   - Calls `GET /api/analytics/max-pain-history`
4. Regime indicator:
   - Timeline visualization: regime changes over time
   - Color-coded bars: trending_up (green), trending_down (red), range_bound (yellow), volatile (orange)
   - Current regime highlighted
   - Calls `GET /api/analytics/regime-history`
5. Export button:
   - "Export Data" button in panel header
   - Downloads CSV/JSON via `GET /api/analytics/export`
   - Options: date range, format (CSV/JSON)

**Chart library:** Use lightweight SVG charts (no external deps) or integrate a small library like `chart.js` (40KB gzipped) or `uPlot` (30KB). Decision needed.

**Files:**
- `src/shettyxtreme/terminal/web/src/components/AnalyticsPanel.svelte`
- New: `src/shettyxtreme/terminal/web/src/lib/charts.ts` (chart rendering utilities)
- `src/shettyxtreme/terminal/web/src/lib/api.ts` (history endpoints)

**Estimated effort:** 3-4 days

---

### Task 3B.4: Greeks Panel UI
**Goal:** Greeks visualization and enhanced risk metrics

**Frontend work:**
1. Greeks history charts:
   - 4 line charts: net_delta, net_gamma, net_theta, net_vega over time
   - Time range selector: 1D / 7D / 30D
   - Calls `GET /api/execution/greeks-history`
2. Enhanced risk metrics display:
   - Already have `GET /api/execution/risk/heatmap` data
   - Visualize sector exposure as horizontal bar chart
   - Visualize stress scenarios as table with color-coded PnL impact
   - Show margin utilization as gauge (0-100%, red if >80%)
3. Per-position greeks table enhancements:
   - Sortable columns (click header to sort)
   - Color-code delta (green if positive, red if negative)
   - Show greeks as sparklines (mini-charts in table cells) — optional, lower priority

**Files:**
- `src/shettyxtreme/terminal/web/src/components/GreeksPanel.svelte`
- `src/shettyxtreme/terminal/web/src/lib/charts.ts` (reuse from 3B.3)
- `src/shettyxtreme/terminal/web/src/lib/api.ts` (greeks-history)

**Estimated effort:** 2-3 days

---

## Phase 3C: Integration & Polish (Priority: Medium)

### Task 3C.1: Cross-Panel Integration
**Goal:** Connect panels where logical

**Work:**
1. Scanner → Proposal: "Create proposal" button on scanner findings (if actionable)
2. Hints → Analytics: Show hint accuracy in context of regime (e.g., "hints are 65% accurate in trending markets")
3. Analytics → Greeks: Click regime bar to see greeks during that regime period
4. Global: Ensure all panels handle loading/error/empty states consistently

**Estimated effort:** 1-2 days

---

### Task 3C.2: Performance & UX Polish
**Goal:** Ensure smooth UX across all panels

**Work:**
1. Loading skeletons for all charts (already present in some panels, ensure consistency)
2. Debounce chart re-renders on data updates (max 1 render per 500ms)
3. Keyboard navigation: ensure all panels support Tab/Enter/Escape
4. Accessibility: ARIA labels for charts, color-blind-safe palettes
5. Responsive: ensure panels work in narrow right-dock mode (<460px)

**Estimated effort:** 1-2 days

---

## Execution Strategy

### Wave 1: Backend (Week 1-2)
- **Parallel tracks:**
  - Track A: Task 3A.1 (Scanner infrastructure) — 2-3 days
  - Track B: Task 3A.2 (Hints → Proposal) — 1-2 days
  - Track C: Task 3A.3 (Analytics history) — 2-3 days
  - Track D: Task 3A.4 (Greeks history) — 1 day
- **Gate:** All backend tests pass, endpoints documented in `api.ts`

### Wave 2: Frontend (Week 2-3)
- **Sequential (charts depend on backend):**
  - Task 3B.1 (Scanner UI) — 2 days
  - Task 3B.2 (Hints UI) — 1-2 days
  - Task 3B.3 (Analytics UI) — 3-4 days
  - Task 3B.4 (Greeks UI) — 2-3 days
- **Gate:** `npm run check` 0 errors, `npm run build` success, manual smoke test

### Wave 3: Integration (Week 3)
- Task 3C.1 (Cross-panel) — 1-2 days
- Task 3C.2 (Polish) — 1-2 days
- **Gate:** Full test suite passes, design review, user acceptance

**Total estimated effort:** 3 weeks (15-20 working days)

---

## Risk Mitigation

### Chart Library Decision
**Options:**
1. **SVG-only (no deps):** Lightweight, full control, but more code to write
2. **Chart.js (40KB):** Mature, easy to use, but adds dependency
3. **uPlot (30KB):** Fast, lightweight, but less feature-rich

**Recommendation:** Start with SVG-only for simple line charts (IV rank, PCR, max pain). If complexity grows (multi-series, zoom, tooltips), migrate to uPlot.

### Backend Scope Creep
**Risk:** History endpoints could expand (per-position greeks history, granular scanner configs)
**Mitigation:** Stick to the spec. Per-position history is "nice-to-have" — defer if time-pressed.

### Frontend Performance
**Risk:** Charts with 1000+ data points could lag
**Mitigation:** Downsample on backend (return max 200 points per history endpoint). Frontend debounces renders.

---

## Success Criteria

- ✅ All 11 scanners operational (Tier-B poller running)
- ✅ Scanner thresholds configurable via UI
- ✅ Real-time scanner alerts via WebSocket
- ✅ One-click proposal generation from hints
- ✅ Hint accuracy tracking (win rate, avg PnL)
- ✅ IV rank, PCR, max pain, regime history charts
- ✅ Greeks history charts (net Δ/Γ/Θ/V)
- ✅ Data export (CSV/JSON)
- ✅ All panels follow DESIGN.md (dark theme, Indian price convention, JetBrains Mono numerals)
- ✅ Full test suite passes (1629+ tests, 0 failures)
- ✅ `npm run check` 0 errors, `npm run build` success

---

## Next Steps

1. **Approve this plan** — confirm scope and priorities
2. **Start Wave 1 (backend)** — dispatch parallel tracks for 3A.1-3A.4
3. **Daily check-ins** — review progress, unblock issues
4. **Wave 2 (frontend)** — after backend gate passes
5. **Wave 3 (integration)** — after frontend gate passes

---

## Appendix: Backend Audit Summary

**Ready (no backend work):**
- Scanner: 11 types implemented, findings endpoint exists
- Hints: strategy-hint endpoint exists, proposals auto-generate
- Analytics: current snapshot endpoints exist (regime, options-summary, v2 chain)
- Greeks: portfolio-greeks + risk/heatmap endpoints exist

**Needs backend work (12 items):**
1. Scanner: configurable thresholds
2. Scanner: WS alerts for findings
3. Scanner: alert history (persistent)
4. Scanner: Tier-B poller runtime
5. Hints: one-click proposal POST
6. Hints: accuracy tracking
7. Analytics: IV rank history
8. Analytics: PCR history
9. Analytics: max pain history
10. Analytics: regime history
11. Analytics: data export
12. Greeks: greeks history

**Partial (needs enhancement):**
- Scanner alerts: exists but only risk/system, not findings
- Hints proposals: auto-gen works, but no manual trigger
- Analytics scorecard: Phase 4B surface, not Phase 3 chart data
- Greeks per-position: depends on IV cache warmth
- Strategy-hint response: missing `strategy` field
