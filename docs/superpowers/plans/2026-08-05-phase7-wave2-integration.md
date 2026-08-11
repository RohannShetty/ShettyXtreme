# Phase 7 Wave 2 — App.svelte Integration — Report

**Date:** 2026-08-05
**Status:** Complete — `npm run check` 0 errors / 0 warnings; `npm run build` succeeds; Python suite **1197 passed / 0 failed / 0 skipped**; vitest 17/17
**Scope:** Wave 2 frontend-chrome integration into `App.svelte` (fix-26 Header two-row, fix-27 TickerStrip, fix-28 CommandPalette) + recon §1.3 resizable split panes + palette window-event contract wiring
**Input:** `docs/superpowers/plans/2026-08-05-phase7-recon.md` §1.2/§1.3/§1.7/§1.8 and the three wave-2 component reports

---

## 1. What was integrated

| Component | Report | Mounted as |
|---|---|---|
| `CommandPalette` | `2026-08-05-phase7-wave2-command-palette.md` | Root sibling of `<Toaster />`, **outside** the route branches — Ctrl+K works on every route |
| `TickerStrip` | `2026-08-05-phase7-wave2-ticker-strip.md` | New grid row directly below the Header (`route === "/"` only) |
| Header two-row | `2026-08-05-phase7-wave2-header-two-row.md` | No Header edits — App-side `--header-bottom` responsive bump (see §3) |
| Resizable split panes | recon §1.3 | Hand-rolled gutters in `.workspace` (no new dependency — `svelte-panels` is not installed) |

The three wave-2 components themselves were **not modified** (mission constraint). Two additive listener wires were added in `KillSwitch.svelte` and `ModeSwitcher.svelte` — the palette report's documented integration contract (§2.2 below) — these are not among the three protected components.

## 2. Command palette — mount + keyboard wiring

### 2.1 Ctrl+K / ⌘K

**No extra shortcut wiring was needed.** CommandPalette registers its own global `keydown` listener in `onMount` (report §1.4: input-guarded, Ctrl+Shift+K excluded so the kill switch keeps priority). Mounting `<CommandPalette />` alone enables the shortcut. App.svelte's existing `onKeydown` handles only Ctrl+R / Escape, so there is no collision.

### 2.2 Window-event contract (report §3) — all three wired

| Event | Dispatched by | Listener wired |
|---|---|---|
| `sx:open-dock` | Research / Knowledge palette items | **App.svelte** `onMount`: `window.addEventListener("sx:open-dock", onOpenDock)` → `drawerOpen = true` (removed in cleanup). Above 1440px the dock is grid-pinned so it's a no-op visually; below it slides the overlay in. |
| `sx:toggle-kill-switch` | Toggle kill switch item | **KillSwitch.svelte**: `window.addEventListener("sx:toggle-kill-switch", onToggleKillSwitch)` → `toggle()` — DISARM keeps its typed-confirm (F-EXEC-001); never bypassed |
| `sx:cycle-mode` | Cycle execution mode item | **ModeSwitcher.svelte**: `window.addEventListener("sx:cycle-mode", onCycleMode)` → `cycleMode()` — LIVE arming keeps its typed-confirm dialog (D10) |

### 2.3 Esc layering

App's existing `Escape → close drawer` handler is now guarded with `!$paletteOpen` (imported from CommandPalette's module store, a documented consumer API). With the palette open, Esc belongs to the palette's Dialog EscapeLayer; closing the drawer underneath simultaneously would be a double-close.

## 3. Ticker strip + `--header-bottom`

### 3.1 Placement

`<TickerStrip />` is wrapped in `<div class="ticker-row">` and placed directly below `<Header />` in `.app-grid`. The wrapper exists so grid-row placement is explicit — TickerStrip's root (`<div class="strip">`) shares the `.strip` class name with PositionsRiskStrip (`<section class="strip">`), which would make a `:global(.strip)` selector ambiguous.

### 3.2 `--header-bottom` responsive bump

- **≥1024px (unchanged):** `--header-bottom: 52px` — 8px grid padding + 44px header.
- **≤1024px (new):** `--header-bottom: 88px` via `@media (max-width: 1024px)` — 8px grid padding + 4px head padding + two 36px rows. This is exactly the bump the header report §5 flagged; without it the LIVE banner would overlap the header's second row.

The `.app-grid:has(:global(.live-banner))` 4th-row reserve mechanism is kept and extended (see §4).

## 4. Grid-row restructure (and a latent LIVE bug fix)

The `:has(.live-banner)` banner-slot template previously added a 4th row while only 3 DOM items existed (Header, workspace, PositionsRiskStrip). Grid auto-placement then assigned the **workspace to the 36px banner row** — crushing the workspace in LIVE mode. Verified this is real: the compiled bundle carries `.app-grid.svelte-x:has(.live-banner){grid-template-rows:auto 36px minmax(0,1fr) auto}` with only 3 children.

Fixed with explicit grid-row placement plus the new strip row:

| Row | Non-LIVE | LIVE |
|---|---|---|
| 1 | Header (auto) | Header (auto) |
| 2 | **TickerStrip** (`.ticker-row { grid-row: 2 }`) | 36px banner slot (fixed bar overlays) |
| 3 | workspace (`grid-row: 3`) | **TickerStrip** (`grid-row: 3`) |
| 4 | positions (`grid-row: 4`) | workspace (`grid-row: 4`) |
| 5 | — | positions (`grid-row: 5`) |

`.app-grid` template: `auto auto minmax(0, 1fr) auto` (base) / `auto 36px auto minmax(0, 1fr) auto` (live). All overrides confirmed present in the compiled bundle.

## 5. Resizable split panes (recon §1.3)

The recon listed this as Wave-2 item #4 with a dependency decision (`svelte-panels` not installed). Chose the **hand-rolled** path — zero new dependencies, App.svelte-only, ~80 lines.

### 5.1 Mechanism

- `.workspace` grid columns are now `var(--rail-w, 260px) 8px minmax(0, 1fr) 8px var(--right-w, 320px)` with `gap: 0` — the two 8px gutter columns replace the old 8px column gap, so the spacing is **byte-identical** to the previous `260px … 320px; gap: 8px`.
- Two `<div class="gutter" role="separator" tabindex="0">` handles (rail↔center, center↔right-col). Pointer events with `setPointerCapture`; arrow keys nudge ±8px. During a drag a `drag-active` class lights the 2px accent line (`--hairline-strong` → `--accent`), and `.workspace.dragging` disables text selection.
- `aria-valuenow/valuemin/valuemax` on each separator. The two `a11y_no_noninteractive_*` svelte-check warnings are suppressed with `svelte-ignore` comments — the focusable `role="separator"` + arrow-key pattern is the correct WAI-ARIA resizable-separator widget, and svelte-check's interactive-role list predates the `separator` widget role (verified: adding `tabindex`+handlers without `role="separator"` would be worse for a11y).
- Widths persist to `localStorage` (`sx:rail-w`, `sx:right-w`) on drag end / arrow key. Restore clamps to `[min, min(hard-max, 0.5×vw)]` so a narrow viewport can never be asked to render two oversized panes (recon §1.3 risk note).

### 5.2 Clamps + breakpoint

| Pane | Min | Max |
|---|---|---|
| rail | 260px (matches original `.rail` min-width) | 480px |
| right dock | 320px (matches original `.right-col` min-width) | 640px |

Below 1440px the `.right-col` becomes the fixed overlay drawer; its gutter is `display: none` and `--right-w` is simply unused until the viewport grows back (3-col grid: `var(--rail-w) 8px minmax(0,1fr)`). No persistence reset at the breakpoint needed — clamped restore keeps stored values valid.

## 6. Verification results

| Gate | Result |
|---|---|
| `npm run check` | ✅ **0 errors, 0 warnings** (whole tree) |
| `npm run build` | ✅ PASS — `✓ built in 34.3s`; bundle written to `../static/` (`index-DD8e8w9P.js` 454.25 kB, `index-HX37SJqg.css` 93.44 kB) |
| `npm test` (vitest, web) | ✅ **17 passed / 17** (7 files) |
| Python suite | ✅ **1197 passed / 0 failed / 0 skipped** (full gate: `pytest tests/ -q --tb=short`, basetemp phase7-wave2) |
| `grep "import openalgo\|from openalgo" src/` | ✅ 0 matches (standalone rule) |
| God-module guard | ✅ App.svelte 579 lines, KillSwitch 154, ModeSwitcher 350 (< 1000) |
| Compiled-CSS audit | ✅ `:has(.live-banner)` template + row overrides, `--rail-w` columns, `--header-bottom: 88px`, `.gutter-right` all present in `static/` bundle |
| `graphify update .` | ✅ 7435 nodes / 15927 edges rebuilt |

### Manual checks (reasoned, not browser-tested)

- **Ctrl+K**: palette registers its own listener — mounting alone enables open/close toggle, input-guarded, Ctrl+Shift+K untouched (kill switch).
- **Palette actions**: Research/Knowledge → `sx:open-dock` → drawer slides in below 1440px; Toggle kill switch → typed DISARM confirm; Cycle mode → LIVE typed confirm (all safety flows preserved).
- **Header two-row**: ≤1024px the header re-packs to two 36px rows (pure CSS in Header.svelte); `--header-bottom: 88px` keeps the LIVE banner below both rows; the strip + workspace shift down correctly in the 5-row live template.
- **Resizable**: drag rail/right gutters ≥1440px (right) and always (rail); arrow keys nudge; widths persist and re-apply with clamps.

## 7. Files changed

| File | Change |
|---|---|
| `src/shettyxtreme/terminal/web/src/App.svelte` | Imports + mounts CommandPalette (root) and TickerStrip (ticker-row); `sx:open-dock` listener; Esc palette guard; resizable-pane state + gutter handlers; grid rows reworked to 4/5-row with explicit placement; `--header-bottom` 88px bump ≤1024px; gutter + workspace CSS; media query updated |
| `src/shettyxtreme/terminal/web/src/components/KillSwitch.svelte` | Added `sx:toggle-kill-switch` window listener → `toggle()` (+ cleanup) |
| `src/shettyxtreme/terminal/web/src/components/ModeSwitcher.svelte` | Added `sx:cycle-mode` window listener → `cycleMode()` (+ cleanup) |
| `src/shettyxtreme/terminal/static/` | Regenerated committed bundle (AGENTS.md convention) |
| `docs/superpowers/plans/2026-08-05-phase7-wave2-integration.md` | This report |

**Not touched** (mission constraint): `CommandPalette.svelte`, `TickerStrip.svelte`, `Header.svelte`.

## 8. Issues encountered

1. **Latent LIVE-mode layout bug** (pre-existing): the `:has(.live-banner)` 4-row template auto-placed the workspace into the 36px banner row, crushing it. Fixed by explicit `grid-row` placement (see §4). Not a regression — an improvement that the strip-row insertion forced to the surface.
2. **svelte-check a11y warnings** on the separator handles: `a11y_no_noninteractive_tabindex` / `a11y_no_noninteractive_element_interactions`. The ARIA focusable-separator widget pattern is correct; suppressed with `svelte-ignore` (first svelte-ignore use in the repo — two-line comments don't parse, per-code single-line comments do).
3. **`.strip` class collision**: TickerStrip and PositionsRiskStrip both root at `.strip`; the ticker got a `.ticker-row` wrapper so grid-row placement is unambiguous without `:global(.strip)`.
4. **Resizable dependency decision** resolved toward hand-rolling (no `svelte-panels` install), keeping the mission's "only modify App.svelte" constraint intact.

## 9. Non-goals / follow-ups

- **`options-summary` endpoint** (strip report §1 IV-rank caveat): still needs `GET /api/intelligence/options-summary` backed by `IVRankCalculator` — backend lane, roadmap §1.12.
- **WS regime push** for the strip (report §2 "future"): switching regime to the already-broadcast `regime` topic would drop its 30s poll — integration-wave optimization, deferred.
- **Palette symbol search** (recon §1.2 palette v2): needs `/api/instruments/search`, out of scope.
- No commits made (per task instruction).
