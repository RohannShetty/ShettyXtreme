# Phase 7 UI Polish — Batch B (R5, R7, R9, R10) — Implementation Report

- **Date:** 2026-08-06
- **Scope:** 4 polish items from `docs/superpowers/plans/2026-08-05-phase7-ui-review.md` (R5, R7, R9, R10)
- **Design contract:** `DESIGN.md` (binding) — near-black canvas, single amber accent, transitions ≤ 120 ms except sanctioned exceptions (price flash; R7's rare 300 ms theme cross-fade per the review doc), no shadows/gradients, **red = up `#f6525c`, green = down `#2ebd85` (never inverted)**.
- **Verification:** `npm run check` 0 errors/0 warnings, `npm run build` success, no file > 1000 lines.

---

## R5 — Enlarge hit areas on remove/close controls (MEDIUM)

### `src/shettyxtreme/terminal/web/src/components/Watchlist.svelte` (lines 387–402)

`.rm` (the per-row remove button) was `padding: 2px` → ≈ 18 px tall target inside a fixed 28 px row. Rewritten:

```css
.rm {
  background: none;
  border: none;
  color: var(--faint);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  align-self: stretch;   /* fill the 28px row height */
  padding: 0 3px;
}
```

- `align-self: stretch` (overrides the grid's `align-items: center`) makes the button fill the full **28 px row height** in its dedicated 20 px grid column (`grid-template-columns: minmax(0, 1fr) auto auto 20px`) — the hit area grows from ~18 × 20 px to **28 × 20 px**, i.e. the row-height ceiling.
- Horizontal padding stays at 3 px so the button never widens into the `chg` text column, and the row's own select target (`selectRow`) is untouched — the button's `e.stopPropagation()` still wins in its own column.
- `.rm:hover { color: var(--danger) }` unchanged. No icon change (`size-3.5`), so no layout shift.

### `src/shettyxtreme/terminal/web/src/App.svelte` (lines 510–522)

`.drawer-close` (right-dock close button) was `padding: 2px` → ≈ 20 px target. Changed to `padding: 6px` (with a comment) → `size-4` icon + 12 px padding = **28 px target** inside the 44 px drawer header, per the review's "padding: 6px / size-9 inside the 44 px header".

---

## R7 — Theme-toggle icon cross-fade (LOW)

Both icons stay in the DOM inside a `relative` wrapper; the inactive one fades to `opacity-0 scale-[0.25] blur-[4px]`, the active one sits at `opacity-100 scale-100 blur-0`; both carry `transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)]`. Pure CSS via Tailwind utilities — no motion dependency. (300 ms is the review-doc-sanctioned exception to the 120 ms cap: rare interaction, and a static color cue already exists.)

### `src/shettyxtreme/terminal/web/src/components/Header.svelte` (lines 314–321)

Replaced the `{#if theme === "dark"} <Sun/> {:else} <Moon/> {/if}` hard swap with:

```svelte
<span class="relative inline-flex size-4" aria-hidden="true">
  <Sun class="size-4 transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)] {theme === "dark" ? "opacity-100 scale-100 blur-0" : "opacity-0 scale-[0.25] blur-[4px]"}" />
  <Moon class="absolute inset-0 size-4 transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)] {theme === "dark" ? "opacity-0 scale-[0.25] blur-[4px]" : "opacity-100 scale-100 blur-0"}" />
</span>
```

- Sun in normal flow (keeps the 16 px layout slot), Moon `absolute inset-0` overlapping — zero layout shift on toggle.
- Wrapper `aria-hidden="true"`: the button already has `aria-label="Toggle light or dark theme"`, so the icon pair is decorative.
- Driven by the existing reactive `theme = $state(getTheme())` (Header.svelte line 53) — no new state.

### `src/shettyxtreme/terminal/web/src/components/CommandPalette.svelte` (lines 31, 147–159, 183–196, 304–315)

The palette used a different pattern than the header — a derived component swap (`themeIcon = $derived(getTheme() === "dark" ? Sun : Moon)` injected into the theme item) rather than an `{#if}`. Converted to a reactive cross-fade:

- **Line 31:** import now includes `type Theme`.
- **Lines 183–196:** `themeIcon` derived removed; replaced with `let theme: Theme = $state(getTheme());` and the `filtered` derived no longer re-maps the theme item's icon (plain filter/sort now).
- **Lines 147–159:** the `act-theme` run handler keeps `theme` in sync — `run: () => { const next: Theme = theme === "dark" ? "light" : "dark"; applyTheme(next); theme = next; }` (the palette closes before running, but the state is correct for the next open and future-proof if it ever stays open).
- **Lines 304–315:** template special-cases the theme item — both `Sun`/`Moon` at `absolute inset-0 size-3.5` cross-fading, preserving the generic row's selected-state color cue (`text-accent` vs `text-muted-foreground`):
  ```
  class="absolute inset-0 size-3.5 transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)] {i === selected ? 'text-accent' : 'text-muted-foreground'} {theme === 'dark' ? 'opacity-100 scale-100 blur-0' : 'opacity-0 scale-[0.25] blur-[4px]'}"
  ```
  All other palette items keep the generic `<Icon …/>` path unchanged. Wrapper `aria-hidden="true"`.

---

## R9 — TickerStrip Unicode glyphs → Lucide SVGs (LOW)

### `src/shettyxtreme/terminal/web/src/components/TickerStrip.svelte` (lines 4–12, 272–276, 282–284, 427–432)

- **Import (lines 4–12):** added `ArrowDown, ArrowLeftRight, ArrowUp` to the existing `@lucide/svelte` import.
- **Regime direction carets (lines 272–276):** `▲` / `▼` glyph spans → `<ArrowUp class="dir-up size-3" aria-hidden="true" />` / `<ArrowDown class="dir-down size-3" aria-hidden="true" />`. The `dir-up`/`dir-down` classes keep the **price tokens — red = up, green = down (Indian law)**; the SVGs render at `size-3` (12 px) per the review.
- **Regime transition marker (lines 282–284):** `⇄` inside a bordered `.chip` pill → `<ArrowLeftRight class="chip-warn size-3" aria-hidden="true" />` (warning token color preserved).
- **CSS (lines 427–432):** removed the now-dead `.dir { font-size: 9px }` rule (font-size does nothing for SVGs); kept `.dir-up` / `.dir-down` color rules and updated the Indian-price-law comment.
- All three glyphs replaced — zero font-dependent characters remain in the strip.

---

## R10 — Closed right dock visibility optimization (LOW)

### `src/shettyxtreme/terminal/web/src/App.svelte` (lines 572–599)

In the ≤ 1439 px overlay-drawer media query only (the docked ≥ 1440 px grid column is untouched):

```css
.right-col {
  ...
  transform: translateX(100%);
  visibility: hidden;                                   /* added */
  transition: transform 120ms ease-out, visibility 120ms; /* added */
}
.right-col.open {
  transform: translateX(0);
  visibility: visible;                                  /* added */
}
```

- **Closed (default):** `visibility: hidden` + off-screen transform → the four docked panels (ProposalQueue, Research, Knowledge, LogDrawer) **skip paint entirely** while the drawer is closed.
- **Transition behavior:** `visibility` transitions discretely — flips to `visible` on open-start (so the slide-in is fully painted), holds visible through the 120 ms slide-out, then flips `hidden` at close-end. No flash, no early-hide.
- **Keep-alive preserved:** the DOM and all WS state stay mounted — only compositing is skipped, matching the review's intent.

---

## Verification

| Gate | Result |
|---|---|
| `npm run check` (svelte-check, web/) | **0 errors, 0 warnings** |
| `npm run build` (vite, web/) | **Success** — 4634 modules, built in 23.34 s; bundle written to `terminal/static/` |
| No file > 1000 lines | **Pass** — max is Header.svelte (659); all 5 touched files well under |

`src/shettyxtreme/terminal/static/` assets were regenerated by the build (committed bundle convention per AGENTS.md). No backend/Python files touched. The other modified files in the working tree (`SettingsView`, `ScannerPanel`, `design.css`, etc.) belong to parallel batch work by other agents — not part of this report.

---

## Deviations from the review doc

1. **Import package:** the review says `lucide-svelte`; the codebase imports from **`@lucide/svelte`** (monorepo alias — 22 existing imports). Used `@lucide/svelte` for consistency.
2. **R9 transition marker:** dropped the bordered `.chip` pill wrapper (it is sized for 9 px mono text — an SVG inside would be cramped/overflow); kept the `.chip-warn` warning color on the `ArrowLeftRight`. Visual intent (amber "transition" marker) preserved.
3. **R7 in CommandPalette:** the review's example targets Header only; the palette's original code was a derived component swap, not an `{#if}`. Implemented the same cross-fade via reactive `theme` state + a template special-case, preserving the selected-row accent color.
4. **R5 `.rm`:** used `align-self: stretch` + `padding: 0 3px` instead of the review's "padding: 4px + ::after" option — this fills the full 28 px row height without widening into the `chg` column (the review's own collision constraint), and avoids a pseudo-element.
5. **R7 duration 300 ms:** kept as specified by the review (and this dispatch's instructions) even though it exceeds DESIGN §4's 120 ms cap — sanctioned exception for the rare theme toggle; a static color cue exists on the button.
6. **Dead CSS:** removed the `.dir { font-size: 9px }` rule made unused by the SVG swap.
