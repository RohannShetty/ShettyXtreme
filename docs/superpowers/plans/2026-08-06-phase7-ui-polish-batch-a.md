# Phase 7 UI Polish — Batch A (R4, R8, R11, R13)

Date: 2026-08-06
Source: `docs/superpowers/plans/2026-08-05-phase7-ui-review.md` (§2.3 Typography, R4/R8/R11/R13)
Scope: 4 low-risk typography/motion polish items. R7 (theme-icon cross-fade) deliberately NOT implemented — owned by another subagent.

## Changes

### R4 — Font smoothing at the root (`design.css`)

- **File:** `src/shettyxtreme/terminal/web/src/lib/design.css`
- **Lines:** `body` rule now spans 95–104; added comment at 101, `-webkit-font-smoothing: antialiased;` at 102, `-moz-osx-font-smoothing: grayscale;` at 103.
- **What:** macOS renders Inter heavier than designed; this restores the intended weight on every sans label in a text-dense surface. Harmless on Windows/Linux (per review doc).
- **Constraint check:** typography/labels unaffected; no color, size, or layout change.

### R8 — Reduced-motion guard on the kill-switch pulse (`app.css`)

- **File:** `src/shettyxtreme/terminal/web/src/lib/app.css`
- **Lines:** 84–89 (new block after the `kill-pulse` keyframes):
  ```css
  @media (prefers-reduced-motion: reduce) {
    .kill-pulse {
      animation: none;
    }
  }
  ```
- **What:** matches the existing `pip-pulse` guard (Header.svelte:555–559) and `live-pulse` guard (ChainGrid.svelte:508–512) exactly — same block shape, same `animation: none` body. The armed-pulse ring still renders at rest (the `box-shadow` stroke from the animation's 0% frame is replaced by the static `box-shadow` on the button when the animation is removed; the kill-switch button keeps its danger fill — the pulse is purely decorative).
- **Note:** `KillSwitch.svelte:100` applies `.kill-pulse` conditionally on `armed`; with `animation: none` under reduced motion the button is static but still visually distinct (danger bg, armed color swap).

### R11 — 9px chrome labels bumped to 10px (Header, TickerStrip)

DESIGN §3.1 floors body-adjacent type at 11px `micro`; the review accepts 10px for decorative chrome labels. Chose **10px over 11px** for all three: `.ltp-exch` sits under the 12px symbol (an 11px sub-label would crowd the hierarchy), and `.metric-label` shares a row with a Lucide icon inside `min-width: 110px` metric cards (11px bold + 0.08em tracking + icon would risk wrapping at the 110px floor). `.strip-foot` is a single symbol + dot with `margin-left: auto` — 10px keeps it visually consistent with the other two. All three remain decorative chrome (no numerals involved).

- **Header.svelte** — `.ltp-exch` (line 458): `font-size: 9px` → `10px`. Letter-spacing, color (`--faint`), `nowrap` unchanged.
- **TickerStrip.svelte** — `.metric-label` (line 362): `font-size: 9px` → `10px`. Weight 700, tracking 0.08em, uppercase unchanged.
- **TickerStrip.svelte** — `.strip-foot` (line 449): `font-size: 9px` → `10px`. `--faint` color unchanged.
- **Not touched:** `Watchlist.svelte` `.exch` (owned by another subagent). `.metric-sub`/`.dir`/`.chip` in TickerStrip are also 9px but were NOT in the review's R11 list (they are sub-data/status marks, not the flagged chrome labels) — left as-is to keep scope tight.

### R13 — `text-wrap: pretty` on the 404 prose (`App.svelte`)

- **File:** `src/shettyxtreme/terminal/web/src/App.svelte`
- **Lines:** `.simple-view p` rule at 526–535; added `text-wrap: pretty;` at 533 with a comment at 532.
- **What:** prevents a dangling word on the last line of the multi-line 404 paragraph. The chain/watchlist empty states are single-line → correctly skipped per review doc.
- **Line drift note:** review cited `App.svelte:524-529`; the 404 block now lives at lines 323–329 (markup) with the `.simple-view p` style at 526–535. Same rule, current location.

## Files touched (mine only)

| File | Change | Lines |
|---|---|---|
| `web/src/lib/design.css` | R4 font smoothing | 101–103 |
| `web/src/lib/app.css` | R8 reduced-motion guard | 84–89 |
| `web/src/components/Header.svelte` | R11 `.ltp-exch` 10px | 458 |
| `web/src/components/TickerStrip.svelte` | R11 `.metric-label` / `.strip-foot` 10px | 362, 449 |
| `web/src/App.svelte` | R13 `text-wrap: pretty` | 532–533 |

## Verification

1. **`npm run check`** (svelte-check, web dir): **0 errors, 0 warnings** ✓
2. **`npm run build`** (vite, web dir): **success** — 4634 modules, bundle written to `src/shettyxtreme/terminal/static/` (committed bundle, per AGENTS.md) ✓
3. **Line-count gate:** recursive scan of `web/src` (`*.svelte`, `*.css`, `*.ts`) — **no file > 1000 lines** ✓

## Deviations from review doc

- **R11 chose 10px (not 11px)** for all three labels. The review allows "10px (or 11px where space allows)"; 11px was judged to crowd the `.ltp-exch` symbol hierarchy and risk wrapping in the 110px-min metric cards. This matches the mission's guidance that 10px is acceptable for decorative chrome labels.
- **R13 line numbers drifted** (review cited 524–529; rule now at 526–535) — same paragraph, no behavior change.
- **R7 (theme icon cross-fade) intentionally not implemented** — assigned to another subagent.

## Out of scope (do not touch)

- `Watchlist.svelte` (`.exch` label, R5 `.rm` hit area) — other subagent
- `ChainGrid.svelte` (R2 border slot, R6 in-place merge, live-pulse guard) — other subagent
- `Header.svelte` R7 theme-icon cross-fade — other subagent
- `App.svelte` R5 `.drawer-close`, R3 gutter focus ring, R10 right-dock visibility — other subagent
