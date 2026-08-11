# S5 Findings — Phase 3 Cockpit Redesign: Scanner + Intelligence Panels

**Date:** 2026-08-05
**Scope:** S5 of Phase 3 — `ScannerPanel.svelte`, `HintsPanel.svelte`, `AnalyticsPanel.svelte` (polish to the pure black/white Phase 3 palette)
**Status:** Complete — both verification gates pass for owned files

---

## Deliverables

| File | Change |
|---|---|
| `src/shettyxtreme/terminal/web/src/components/ScannerPanel.svelte` | Regime badges, 4-level conviction badges, card-ized columns (`eyebrow` + `number-lg` stat), STALE chip (>60s), arrow-key navigation across all scanner items |
| `src/shettyxtreme/terminal/web/src/components/HintsPanel.svelte` | Direction badge (UP red / DOWN green / NEUTRAL muted), mono + Indian-grouped strike/premium/EV, `body` rationale + `caption` meta, STALE chip (>5min), Enter-to-expand details |
| `src/shettyxtreme/terminal/web/src/components/AnalyticsPanel.svelte` | Metric cards (`surface-card` / `number-lg` / `caption`), token-only calibration SVG, current-regime accent bars, STALE chip (>10min), Tab-navigable metric cards |

## Verification

- `npm run check` → **owned files: 0 errors, 0 warnings.** The tree-wide gate currently reports 1 pre-existing error in `ChainGrid.svelte:375` (`data-strike={String(row.strike)}` — `Type 'string' is not assignable to type 'number'`), a file owned by another Phase 3 slice and actively being edited in this working tree. Not in scope to fix; flagged for the ChainGrid owner (S4).
- `npm run build` → **vite production build succeeds** (43.2s, 4527 modules; bundle regenerated in `terminal/static/` per AGENTS.md convention — gate artifact, not committed).

---

## 1. ScannerPanel.svelte

### 1.1 Badges
- **Regime-style badge** (`.badge-regime`): `surface-elevated` bg, `hairline` border, micro-uppercase — applied to `gap_type` / `cluster_type` labels (the scanner's regime-like data). **Face decision:** mission says `micro` (sans 11px); DESIGN.md §4 "Badge — regime" says mono `number-sm`. The mission is the later, more specific instruction, and the labels are chrome (not numerals) — sans micro per DESIGN §3 "labels render in the sans face". Flagged tension; easy to flip to mono if the contract owner prefers.
- **Conviction badge** (`.badge-conv`): mapped from alert `severity` to the DESIGN §4 4-level scale — LOW `muted` / MEDIUM `warning` / HIGH `accent` / EXTREME `ink` on `row-selected` bg. Note: this **removes the old danger-red HIGH** from the scanner's alert badges — HIGH is now accent-amber, per the mission spec. (Alert severity is conviction-like, so the mapping is semantically sound; a true D/P/G conviction value is not present in the scanner payload.)

### 1.2 Scanner cards
The three columns became cards per DESIGN §4 / prompt 2: `surface-card` bg + `hairline` border + 6px panel radius, `eyebrow` (11px/600/0.14em uppercase) label, and a `number-lg` (mono 20px/600/24px) count stat. Item rows keep the 26px density with `hairline` dividers; the selected row gets `row-selected` bg + a 2px accent left edge (via `border-left`, not box-shadow — DESIGN §6 no-shadow ban).

### 1.3 STALE chip
`fetchedAt` is stamped on successful load; a 30s interval advances a `now` clock; `stale` flips when `now - fetchedAt > 60_000`. Chip: `warning` color, micro uppercase, 2px radius — placed in the panel head next to the title.

### 1.4 Keyboard navigation
Roving-tabindex listbox pattern (matches the Watchlist house style): only the active item is in the Tab order (`tabindex=0`/`-1`), and each item handles `onkeydown`. ArrowDown/Up step through the flat item list (gaps → clusters → alerts); ArrowLeft/Right hop between non-empty columns; Home/End jump to bounds. A `$effect` moves real focus onto the active item with `scrollIntoView({block:"nearest"})`, gated by a `navActive` flag so the panel never steals focus on mount/load. Cursor is clamped when data shrinks.

---

## 2. HintsPanel.svelte

### 2.1 Direction badge
Mission labels UP/DOWN/NEUTRAL (mapped from the backend's `bullish`/`bearish`/other): UP → `price-up` (red, Indian law), DOWN → `price-down` (green), NEUTRAL → `muted` + `hairline-strong` border. Badge is mono-uppercase per the existing badge primitive (face unspecified by the mission).

### 2.2 Numerals & prose
Strike/premium/EV render in JetBrains Mono with `tabular-nums` and `toLocaleString("en-IN")` (Indian grouping, 2dp). The rationale is `body` (13px/20px `--body`); the strategy-name line is `caption` (12px/16px) as meta.

### 2.3 STALE chip
Same mechanism, `STALE_MS = 5 * 60_000` (>5min).

### 2.4 Enter-to-expand
The hint card is a `role="button"` (`tabindex=0`, `aria-expanded`, `aria-controls`) — Enter or Space toggles the details region (strike/premium/EV + rationale). Collapsed state shows the direction badge + strategy + a "Press Enter to expand details" hint. Progressive disclosure per the cockpit's keyboard-first contract. Refresh resets to collapsed.

---

## 3. AnalyticsPanel.svelte

### 3.1 Metric cards
Changed from `surface-elevated` → `surface-card` bg; label promoted from 9px micro to `caption` (12px/16px); value promoted to `number-lg` (mono 20px/600/24px). Tab navigation: the cards container is `role="listbox"` and each card `role="option"` + `aria-selected=false` + `tabindex=0`, so Tab steps card-to-card with a visible `focus-ring` outline (DESIGN §3.2). N/A cards keep the dashed `--hairline` border + `note` title.

### 3.2 Calibration SVG
Already token-only (all `var(--...)` — no hardcoded hex); verified and left as-is. Kept the whisker/dot/polyline encoding unchanged.

### 3.3 Regime win-rate bars
The scorecard response does **not** carry the current regime, so the panel fetches `/api/intelligence/regime` in parallel (with a `.catch(() => null)` so a regime failure never kills the panel) and matches `RegimeRow.regime` against it (both sides use the same normalized enum space — `trending_up`/`trending_down`/`range_bound`/`volatile`/`transition`). `accent` bar + accent label for the current regime, `muted` for others. Graceful fallback: when the regime is unknown, all bars stay `accent` (preserves the old behavior rather than dimming everything).

### 3.4 STALE chip
`STALE_MS = 10 * 60_000` (>10min).

---

## Technical notes / findings for later phases

1. **Scorecard should carry `current_regime`.** The AnalyticsPanel now makes a second REST call (`/api/intelligence/regime`) solely to accent the right bar. Adding `current_regime` to `ScorecardResponse` (`terminal/api/analytics_router.py` + `analytics_models.py`) would make it atomic and kill the extra hop + fallback logic.
2. **The 0-error tree gate is blocked by other slices.** `ChainGrid.svelte:375` (`data-strike` typed as number) predates/co-occurs with this slice and lives in S4's file. The working tree shows concurrent edits to ChainGrid/KnowledgePanel/ResearchPanel/etc. — re-run `npm run check` after those slices land.
3. **`micro` vs mono badge face tension.** Mission spec (micro) and DESIGN.md §4 badge table (mono `number-sm`) disagree on the regime-badge face. Resolved in favor of the mission for S5; either the mission doc or DESIGN.md §4 should be aligned at the next contract pass.
4. **Badge reuse vs primitive.** The scanner/hints badges are scoped spans rather than the shadcn `Badge` primitive because the mission's specs (per-level border colors, 4-level conviction scale) exceed the primitive's `variant` set. If badges proliferate, extend `badgeVariants` with `conviction-*` variants instead of more scoped CSS.
5. **Tab remount churn persists** (current-ui-analysis pain #2): scanner/hints/analytics remount on every tab switch, re-fetching and re-arming staleness timers. Keep-alive in App.svelte (e.g., `{#if}` → hidden) would remove the fetch flash; noted for a later slice.
6. The static bundle (`terminal/static/`) was regenerated by the mandatory `npm run build` gate. **Not committed** per instructions.

## Files touched

- `src/shettyxtreme/terminal/web/src/components/ScannerPanel.svelte` (owned)
- `src/shettyxtreme/terminal/web/src/components/HintsPanel.svelte` (owned)
- `src/shettyxtreme/terminal/web/src/components/AnalyticsPanel.svelte` (owned)
- `src/shettyxtreme/terminal/static/*` — regenerated build output (gate artifact, not a source change)

No other files were modified.
