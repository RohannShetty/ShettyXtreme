# Phase 7 Wave 2 — Header Two-Row Fallback (#7) — Findings

**Date:** 2026-08-05
**Status:** Implemented + verified (npm run check 0/0, npm run build ✅, Python suite 1197 passed)
**Scope:** Roadmap §1.7 (header two-row fallback) — `Header.svelte` layout only. App.svelte integration explicitly deferred (see §5).
**Recon source:** `docs/superpowers/plans/2026-08-05-phase7-recon.md` §1.7

---

## 1. What was built

`web/src/components/Header.svelte` now supports a deterministic two-row layout below **1024px** via a pure-CSS `@media (max-width: 1024px)` fallback. No JS, no `matchMedia`, no resize listeners — the reflow is driven entirely by flexbox so there is no layout-jitter on resize (the header simply re-packs at the breakpoint).

### 1.1 DOM restructure — two semantic clusters

The single flat header strip was wrapped in two clusters (plain `<div>`/`<span>` wrappers — no new components):

```
<header class="head">
  <div class="head-status">   <!-- Row 1 (narrow) / left+center (wide) -->
    brand · ltp-hero · ModeSwitcher · health pip · ent-chip · session · cred-chip
  </div>
  <div class="head-actions">  <!-- Row 2 (narrow) / right cluster (wide) -->
    KillSwitch · theme toggle · ShortcutsDialog · logs drawer toggle
  </div>
</header>
```

- `ModeSwitcher` and `KillSwitch` are wrapped in `<span class="head-mode">` / `<span class="head-kill">` so their roots can be targeted by Header's scoped CSS (components' roots carry Header's scope class, but the spans give an explicit, stable hook).
- The three right-side toggles are each wrapped in `<span class="head-action">`.

### 1.2 Wide layout is byte-identical (≥1024px) via `display: contents`

On wide screens the two clusters use `display: contents`, so their children become **direct flex items of `.head`** again — exactly the old flat DOM. The legacy interleave is re-pinned with explicit `order` values so nothing moves:

| order | item |
|---|---|
| 1 | `.brand` |
| 2 | `.ltp-hero` |
| 3 | `.head-mode` (ModeSwitcher) |
| 4 | `.head-kill` (KillSwitch) |
| 5 | `.health` (connection pip — keeps `margin-left: auto` → pushes right cluster) |
| 6 | `.ent-chip` |
| 7 | `.session` |
| 8 | `.cred-chip` |
| 9 | `.head-action` ×3 (theme · shortcuts · drawer — DOM order preserved among equal orders) |

`margin-left: auto` on `.health` is untouched, so the right cluster still hugs the right edge. Visually: **brand → hero → mode → KILL → [auto-margin] pip → ent → session → cred → theme → shortcuts → drawer**, identical to the pre-change header.

### 1.3 Narrow layout (<1024px) — two 36px rows

```css
@media (max-width: 1024px) {
  .head { flex-wrap: wrap; height: auto; }          /* was fixed height:44px */
  .head-status, .head-actions {
    display: flex; align-items: center; gap: 8px;
    flex: 1 1 100%; min-height: 36px;
  }
  .head-status { flex-wrap: wrap; }                  /* safety net for very narrow */
  .head-actions { justify-content: flex-end; }       /* right-aligned action row */
  .health { margin-left: 0; }                        /* row 1 flows left-aligned */
}
```

- `.head` switches from fixed `height: 44px` to `flex-wrap: wrap; height: auto`. Each cluster gets `flex: 1 1 100%`, forcing exactly two stacked full-width rows. The pinned `order` values now sequence items **within** each cluster (row 1: brand→hero→mode→pip→ent→session→cred; row 2: kill→theme→shortcuts→drawer), so no per-row re-interleaving rules are needed.
- **Row heights are 36px, not 32px** (the task's "e.g. 32px") because DESIGN §9 floors the kill switch at `min-height: 36px` and `.head` keeps `overflow: hidden` — a 32px row would clip it. Both rows share `min-height: 36px` so they stay consistent with each other.
- The `ltp-value` (`number-xl`, 28px/32px line-height) fits the 36px row unchanged — no size reduction needed on row 1.

### 1.4 Interaction with the existing compaction cascade

The pre-existing cascade still runs **above** 1024px (`.ltp-chg` hidden ≤1360px, `.title` ≤1240px, `.session-time` + gap-8 ≤1080px). Below 1024px the two-row fallback takes over; the safety set (mode, kill switch, pip, market-hours, cred chip, toggles) never collapses at any breakpoint — consistent with DESIGN §8.

## 2. CSS media query strategy

Single `@media (max-width: 1024px)` block at the bottom of the `<style>` section (after the 1360/1240/1080 cascade so it wins on overlap). Key mechanism: **`display: contents` ↔ `display: flex` flip** on the two clusters plus **flex `order` pinning**:

- `display: contents` (wide) = "pretend the wrapper isn't there" → zero visual change to the legacy single row, zero risk of breaking `App.svelte`'s grid or the `--header-bottom` measurement at desktop widths.
- The flip at 1024px is a single property change per cluster; flexbox re-packs the children into two lines with no layout thrash.
- No media-query-specific `order` overrides: the base `order` values serve both layouts (they sequence the flat row on wide *and* sequence within each cluster on narrow).

## 3. Responsive behavior (reasoned, per viewport)

| Viewport | Behavior |
|---|---|
| 1920px / 1440px | Single 44px row, unchanged from before — all clusters `display: contents`, compaction cascade hides only decorative chrome (ltp-chg ≤1360, title ≤1240). |
| 1024px (exact) | Breakpoint fires; two 36px rows (~80px total incl. gap/padding). Row 2 right-aligned. `title` + `session-time` already hidden by cascade. |
| 768px | Two rows; row 1 (brand/hero/mode/pip/session/cred ≈ 640px worst-case) fits 768px; `.head-status` keeps `flex-wrap: wrap` as a safety net should chips ever need to wrap. Row 2 (kill + 3 icon toggles) comfortably right-aligned. |
| < 768px | Not a tested target (DESIGN §8 stacks everything below 768px); the wrap safety net prevents clipping rather than guaranteeing the exact two-row split. |

The header is `flex: none` in `App.svelte`'s grid, so it grows to its content height on narrow screens without fighting the grid.

## 4. Verification results

| Gate | Result |
|---|---|
| `npm run check` | ✅ **0 errors, 0 warnings** |
| `npm run build` | ✅ PASS — `✓ built in 1m 2s`; bundle written to `../static/` (index-B6d35RnH.js 433.85 kB, index-CYmh_ZrS.css 88.31 kB) |
| Python suite | ✅ **1197 passed / 0 failed / 0 skipped** (full gate: `pytest tests/ -q --tb=short`, basetemp phase7) |
| `grep "import openalgo\|from openalgo" src/` | ✅ 0 matches (standalone rule) |
| God-module guard | ✅ `Header.svelte` = 694 lines (< 1000) |
| File scope | Only `Header.svelte` + this report touched; no new components created; `App.svelte`, `CommandPalette`, `TickerStrip` untouched |

## 5. Integration notes for the App.svelte phase (deliberately NOT done here)

The recon report §1.7 flagged a **known coupling**: `App.svelte` hardcodes `--header-bottom: 52px` (8px grid padding + 44px header) for the LIVE banner slot (`App.svelte:174-178,187`), and `ModeSwitcher`'s `.live-banner` reads `var(--header-bottom)`. **On <1024px the two-row header is ~80px tall**, so `--header-bottom` is stale there and the LIVE banner would sit 28px too high (overlapping the header's second row) until the integration pass.

Per the mission constraints App.svelte was **not** modified. When the Header is integrated into App.svelte (wave 2 integration step), bump `--header-bottom` responsively, e.g. `@media (max-width: 1024px) { --header-bottom: 88px; }` (or compute from the two 36px rows + 8px padding + 8px grid gap = 88px), and keep the `.app-grid:has(:global(.live-banner))` 4th-row mechanism intact.

No commits made. Parallel-lane files in the working tree (`TickerStrip.svelte` untracked, stale committed bundle) were not touched except the bundle regeneration required by the committed-bundle convention.
