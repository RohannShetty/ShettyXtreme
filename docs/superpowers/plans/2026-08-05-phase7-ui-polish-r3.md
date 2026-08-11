# Phase 7 — UI Polish R3 — Resizable Gutter Focus Ring — Implementation Report

**Date:** 2026-08-06
**Status:** Implemented; verified
**Scope:** UI/UX review item R3 — visible 2px focus ring on resizable gutters. Single-file CSS change, zero behavior change.

---

## 1. What was changed

### 1.1 `web/src/App.svelte` — `.gutter:focus-visible` rule added

The `.gutter` rule (workspace grid columns, rail | gutter | center | gutter | right-col) previously had `outline: none` and no focus affordance of its own — keyboard focus only lit the faint 2×28px `.gutter-line` handle (opacity 0 → 1), which is nearly invisible against the near-black canvas.

Added directly after the `.gutter` block:

```css
.gutter:focus-visible {
  box-shadow: inset 0 0 0 2px var(--focus-ring);
}
```

- Draws a 2px **amber** (`#f5b942`) ring inset on the 8px gutter column when focused via keyboard (pointer users still see nothing until hover/drag — `:focus-visible` fires only for keyboard/assistive focus).
- Matches DESIGN.md §3.2 ("Keyboard focus is always visible — 2px focus-ring") and reuses the exact `box-shadow: inset 0 0 0 2px var(--focus-ring)` pattern already used by `ChainGrid.svelte` and `Watchlist.svelte`.
- **Drag state untouched:** the existing `.gutter.drag-active .gutter-line` / `.gutter:active .gutter-line` accent-color rules and `.gutter:hover .gutter-line, .gutter:focus-visible .gutter-line` opacity rules are preserved verbatim — the ring and the handle remain independent.
- Both gutters are covered: the markup uses `class="gutter"` for the rail divider and `class="gutter gutter-right"` for the right-dock divider, so one rule applies to both.

## 2. Files touched (strictly in scope)

| File | Change |
|---|---|
| `web/src/App.svelte` | +3 lines — `.gutter:focus-visible` rule after `.gutter` |
| `docs/superpowers/plans/2026-08-05-phase7-ui-polish-r3.md` | This report |

No commits made. No files outside scope touched.

## 3. Verification results

| Gate | Result |
|---|---|
| `npm run check` | ✅ PASS — `svelte-check found 0 errors and 0 warnings` |
| `npm run build` | ✅ PASS — `✓ built in 1m 15s`, bundle written to `../static/` (index-*.js 454.60 kB, index-*.css 96.74 kB) |
| `--focus-ring` var | ✅ Defined in `web/src/lib/design.css` (`#f5b942` light / `#d97706` dark) — amber, per DESIGN.md §3.2 |
| Manual keyboard check | Tab to either `role="separator"` gutter (rail: "Resize watchlist", right: "Resize right dock") shows the 2px amber inset ring; drag accent unchanged |

## 4. Notes

- `outline: none` remains on `.gutter` (it never had a default outline on Windows anyway, and the ring replaces it deterministically) — the inset box-shadow is the sole focus indicator, consistent with the rest of the codebase.
- R3 was the only focus-ring gap in this area: `grep -c ":focus-visible"` shows the pattern already exists across panels (AnalyticsPanel, ChainGrid, HintsPanel, KnowledgePanel, ProposalQueue, ModeSwitcher, Watchlist, ResearchPanel); gutters were the last uncovered interactive element.
