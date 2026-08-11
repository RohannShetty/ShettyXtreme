# Phase 7 — Terminal UI/UX Polish Review

- **Date:** 2026-08-05
- **Mode:** `full` (make-interfaces-feel-better skill)
- **Scope:** Six terminal components + their shadcn-svelte primitives:
  `App.svelte`, `Header.svelte`, `CommandPalette.svelte`, `TickerStrip.svelte`,
  `ChainGrid.svelte`, `Watchlist.svelte`
- **Framework / styling conventions:** Svelte 5 (runes), Tailwind v4, scoped
  component CSS, shadcn-svelte + bits-ui primitives, design tokens in
  `src/lib/design.css` / `src/lib/app.css`. No motion library installed
  (`package.json` has neither `motion` nor `framer-motion`) — any icon animation
  must use the CSS cross-fade pattern, not a new dependency.
- **Binding contract:** `DESIGN.md` governs all UI work. Two contract facts
  shaped this review: (1) **no drop shadows / gradients / glassmorphism** (DESIGN
  §1, §6) — so the skill's "shadows instead of borders" advice is rejected for
  this codebase; (2) transitions ≤ 120 ms except price flash (DESIGN §4) — so
  animation recommendations are capped at 120 ms unless the flash contract
  applies.
- **Review boundary:** Read-only. No files were modified. Visual states were
  verified by reading source + primitives; no browser session was run (no dev
  server), so pixel-level verification is **not verified** (see Verification).

---

## 1. Executive Summary

The terminal is in genuinely strong shape. It follows the DESIGN contract
closely: tabular numerals everywhere, mono for all numerics, single amber
accent, Indian price law honored in both themes, hairline-only elevation, no
`transition: all` anywhere, no emoji-in-data, and full ARIA on the palette and
keyboard navigation on the watchlist/chain. The density discipline
(28 px/24 px rows, 9–13 px type) is the product, and it reads correctly.

**No HIGH findings.** Nothing found that makes an interaction inaccessible,
misleading, unreadable, or repeatedly disruptive. There are **6 MEDIUM** and
**7 LOW** polish items, all cheap to land. The single most impactful change is
giving the command palette (and every dialog) a 120 ms enter/exit — right now
the operator's most-used overlay snaps in and out. The most visible
consistency bug is the chain's selected row growing a 2 px left border from
nothing (row content jitters ~1–2 px on every arrow-key selection), where the
watchlist already solved the same problem correctly.

| Category | Evidence inspected | Result |
|---|---|---|
| Typography | design.css, app.css, header hero, strip labels, all numeric roles | 4 findings (font smoothing, 9 px labels, text-wrap, tabular verified-clean) |
| Surfaces | radii in App/rail/panels/dialog, selected-row borders, hit areas, focus rings | 3 findings (border shift, hit areas, gutter focus) |
| Animations | dialog primitive, theme toggle, pip/live/kill pulses, flash keyframes, drawer transition | 3 findings (dialog enter/exit, theme icon swap, kill-pulse reduced-motion) |
| Icons | Lucide usage in all six components, stroke widths, glyphs | 2 findings (TickerStrip glyphs; stroke-weight verified-consistent) |
| Performance | transition properties, will-change, tick/refresh render paths, off-screen dock | 2 findings (15 s chain rebuild, off-screen paint) |

---

## 2. Findings

Findings are grouped by the skill's principles. Line numbers cite current
source.

### 2.1 Animations

#### Dialog enter/exit missing — every dialog snaps (incl. the command palette)
| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| MEDIUM | `src/lib/components/ui/dialog/dialog-content.svelte:16,21` | `<DialogPrimitive.Overlay class="fixed inset-0 z-40 bg-scrim">` and `<DialogPrimitive.Content class={cn("fixed …", className)}>` — no `data-[state]` animation; content and scrim appear/disappear instantly | Add `tw-animate-css` (import in `app.css`) and on Content: `duration-[120ms] data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95`; on Overlay: `duration-[120ms] data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0` | The palette (Ctrl+K) is the operator's highest-frequency overlay; a hard snap feels like the app died rather than answered. DESIGN §4 permits ≤ 120 ms transitions; the skill's subtle-exit principle wants a soft fade out, not removal-with-no-exit |

#### Theme-toggle icon hard-swaps instead of cross-fading
| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| LOW | `Header.svelte:313-319`; `CommandPalette.svelte:181,185` | `{#if theme === "dark"} <Sun …/> {:else} <Moon …/> {/if}` — the icon is unmounted/mounted, snapping on toggle | Keep both icons in the DOM inside a `relative` wrapper and cross-fade: inactive one gets `opacity-0 scale-[0.25] blur-[4px]`, active one `opacity-100 scale-100 blur-0`, both `transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)]` (exact values from the skill; no motion dep needed) | Principle 7 — state-change icons should animate with opacity/scale/blur, not toggle visibility. Rare interaction so 300 ms is fine; a static color cue already exists |

#### kill-pulse ignores reduced-motion while its siblings honor it
| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| LOW | `src/lib/app.css:71-82`; `KillSwitch.svelte:100` | `.kill-pulse { animation: kill-pulse 1.4s … infinite }` with no reduced-motion guard — while `pip-pulse` (`Header.svelte:555-559`) and `live-pulse` (`ChainGrid.svelte:508-512`) both have `@media (prefers-reduced-motion: reduce) { animation: none }` | Add the same guard around the kill-pulse keyframes | Principle 19 — motion restraint. The static cue (red bg + label) is preserved, so disabling the pulse under reduced-motion loses nothing |

### 2.2 Surfaces

#### Selected chain row grows a 2 px left border from nothing — content shifts
| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| MEDIUM | `ChainGrid.svelte:395-399` | Base row has no left border; selected adds `"border-l-2 border-l-accent bg-row-selected"` — with `border-collapse: collapse` (`table.svelte:14`) the row's left edge and first-cell content shift ~1–2 px on every selection | Reserve the border slot on every row: base gets `border-l-2 border-l-transparent`, selected swaps the color to `border-l-accent` — exactly the pattern `Watchlist.svelte:321,327` already uses | Skill common-mistake table: hover/selected states must not cause layout shift. Arrow-key strike navigation is a frequent interaction; the jitter is visible |

#### Tiny hit areas on remove/close controls
| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| MEDIUM | `Watchlist.svelte:387-394` (`.rm`, `padding: 2px`, ≈ 20 px target); `App.svelte:495-504` (`.drawer-close`, `padding: 2px`, ≈ 24 px target) | ≈ 20–24 px click targets in a precision tool | `.rm` → extend to the full 28 px row height (`padding: 4px` + a `::after` covering the row, or simply larger padding — do not overlap the row's own click target); `.drawer-close` → `padding: 6px` / `size-9` inside the 44 px header | Principle 16 — dense desktop floor is 40 px, but the ceiling here is set by collision (28 px row, 44 px header); make each target as large as possible without overlapping neighbors |

#### Keyboard focus invisible on the resizable gutters
| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| MEDIUM | `App.svelte:397-405` (`.gutter { outline: none }`), `:414-418` (focus-visible only lights the 2 px handle) | `outline: none` + a subtle 2×28 px handle brighten on `:focus-visible` | Add `box-shadow: inset 0 0 0 2px var(--focus-ring);` on `.gutter:focus-visible` (keeping the accent handle while dragging) | DESIGN §3.2: "Keyboard focus is always visible (2 px focus-ring)". The gutters are focusable (tabindex 0, arrow-key resize) in a keyboard-first workstation; the faint handle is not a sufficient ring |

### 2.3 Typography

#### No font smoothing at the root — macOS text renders heavier
| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| MEDIUM | `src/lib/design.css:94-101` (`body { … }`) | No `-webkit-font-smoothing` / `-moz-osx-font-smoothing` anywhere (grep confirmed zero matches in web/src) | Add to `body` (or `html`): `-webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;` | Principle 8 — on macOS Inter renders heavier than designed; this affects every label in a text-dense surface. Harmless on Windows/Linux |

#### 9 px labels sit below the DESIGN `micro` floor
| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| LOW | `Header.svelte:459` (`.ltp-exch` 9 px), `Watchlist.svelte:356` (`.exch` 9 px), `TickerStrip.svelte:362` (`.metric-label` 9 px), `:447` (`.strip-foot` 9 px) | 9 px sans at `--faint`/`--muted` | Bump to 10–11 px (DESIGN `micro` = 11 px) where space allows, or consciously accept as deliberate chrome — but never let a number render in sans, and keep these decorative-only | DESIGN §3.1 floors body-adjacent type at 11 px `micro`; 9 px renders inconsistently across platforms and is sub-AA at these contrast levels. Low because the strings are decorative labels, not data |

#### Prose without `text-wrap: pretty`
| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| LOW | `App.svelte:524-529` (404 `<p>`, multi-line, `line-height: 1.6`) | Default wrapping can orphan the last line | Add `text-wrap: pretty` to the paragraph (and to any future multi-line empty-state copy) | typography.md — `pretty` prevents a dangling word on the last line. Chain/watchlist empty states are single lines → skip |

### 2.4 Icons

#### TickerStrip renders direction/transition glyphs as text, not SVG
| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| LOW | `TickerStrip.svelte:265,267` (`▲` / `▼`), `:275` (`⇄`) | Unicode glyphs as regime direction carets and the regime-transition marker | Lucide `ArrowUp` / `ArrowDown` (`size-3`, `price-up`/`price-down` colors) and `ArrowLeftRight`, each `aria-hidden="true"` | icons.md — one SVG icon set, no glyphs; text glyphs render inconsistently across platforms/fonts. DESIGN §7 bans emoji in data UI; geometric glyphs are borderline but still font-dependent |

### 2.5 Performance

#### Chain grid rebuilds every row on the 15 s quiet poll
| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| MEDIUM | `ChainGrid.svelte:244-256` (`refreshSilently` → `contracts = resp.contracts`) | Assigning a fresh array every 15 s recomputes the `rows` derived and re-binds every row/cell in the grid (~100+ rows × 7 cells) | Merge in place like `applyTick` does: iterate the response and update matching `contractKey` entries' fields only, keeping the array identity; keep the wholesale swap only when expiry/symbol actually changed | performance.md — avoid needless re-render churn on a data-dense surface; kills the periodic 15 s hitch. The per-tick WS path is already fine-grained in Svelte 5 and needs no change |

#### Closed right dock stays painted below 1440 px
| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| LOW | `App.svelte:553-571` | `.right-col { transform: translateX(100%) }` — off-screen but still composited/painted; Research + Knowledge panels (the heavy ones) render on every frame by default | Add `visibility: hidden` to `.right-col` and `visibility: visible` to `.right-col.open`, with `transition: transform 120ms ease-out, visibility 120ms` — skips paint while closed, keeps the keep-alive DOM + WS state intact | performance.md — the default state (drawer closed) currently pays the full paint cost of four panels |

### 2.6 Verified clean (no change)

- **Tabular numerals:** `.num`, `.ticker`, `.mono`, `table td:last-child`
  (`design.css:102-105`) + `.mono-num`/`.strike-cell` — complete coverage.
- **No `transition: all`** anywhere; every transition is property-specific
  (grep across web/src).
- **Flash contract honored:** `flash-up`/`flash-down` 150 ms background fade
  (`design.css:108-111`); header hero flash toggles color weight, never size
  (`Header.svelte:72-85`).
- **Concentric radii:** panels/rail 6 px, controls 4 px, badges 2 px, dialog 6 px
  with edge-to-edge children — no pinched nesting.
- **Icon consistency:** single Lucide set, default 2 px stroke beside 600-weight
  labels everywhere (matches the stroke-to-text-weight table).
- **Motion restraint:** row hover is instant; palette navigation is instant —
  both correct for high-frequency interactions.
- **`will-change`:** unused, appropriately.

---

## 3. Considered but Rejected

| Location | Candidate | Rejected because |
| --- | --- | --- |
| All surfaces | Replace hairline borders with layered `box-shadow` for elevation (skill's "shadows for elevation") | DESIGN §1/§6 explicitly ban drop shadows anywhere; hairline+surface-step elevation is the binding contract |
| `App.svelte` tabs / page load | Staggered enter animation on the workspace | DESIGN §1: "the only animated elements are price flashes on tick, the pulsing LIVE indicator, and the selected row's accent edge" — no page-load choreography; also motion restraint for a workstation |
| `button.svelte` base | `active:scale-[0.96]` on every button | DESIGN §4 has no press-scale contract and caps transitions at 120 ms; press scale is a nice-to-have on primary CTAs only (see R12), not a base primitive change |
| `table-row.svelte` | Keep `transition-colors` on row hover | Already present and correct (150 ms color only) — no change |

---

## 4. Prioritized Recommendations (impact-ranked)

**Priority tiers:** High = fixes a visible inconsistency or a11y gap in a
frequent path; Medium = real polish, cheap; Low = optional finishing.

| # | Priority | Recommendation | Effort |
|---|---|---|---|
| R1 | **High** | Add 120 ms enter/exit to `DialogContent`/`Overlay` (adds `tw-animate-css` dep) — palette and every dialog stop snapping | S (~30 min, 1 file + 1 import) |
| R2 | **High** | Reserve the 2 px left border on every chain row; swap color on selection (mirror watchlist) | XS (~15 min, 1 line) |
| R3 | **High** | Visible 2 px focus ring on the resizable gutters (`:focus-visible`) | XS (~15 min, 1 block) |
| R4 | **Medium** | Root `-webkit-font-smoothing: antialiased` (+ macOS grayscale) in `design.css` | XS (~5 min, 2 lines) |
| R5 | **Medium** | Enlarge `.rm` and `.drawer-close` hit areas (to 28 px row / 44 px header ceilings) | XS–S (~20 min) |
| R6 | **Medium** | In-place merge in `refreshSilently` so the chain stops rebuilding all rows every 15 s | M (~1–2 h, careful with the reqId/expiry convergence logic) |
| R7 | **Low** | Cross-fade the Sun/Moon theme icon (header + palette) with the CSS opacity/scale/blur pattern | S (~45 min) |
| R8 | **Low** | `prefers-reduced-motion` guard on `kill-pulse` (match pip/live guards) | XS (~5 min) |
| R9 | **Low** | Swap TickerStrip `▲▼⇄` glyphs for Lucide arrows; `aria-hidden` | XS (~20 min) |
| R10 | **Low** | `visibility: hidden` on the closed overlay drawer below 1440 px | XS (~15 min) |
| R11 | **Low** | Bump 9 px chrome labels to 10–11 px where space allows | S (~30 min, cosmetic) |
| R12 | **Low** | `active:scale-[0.96]` on the primary Add-symbol / header action buttons only, with a `static` opt-out | S (~30 min) |
| R13 | **Low** | `text-wrap: pretty` on the 404 prose | XS (~5 min) |

---

## 5. Key Code Examples

### R1 — Dialog enter/exit (the one that changes the feel of the whole app)

```svelte
<!-- src/lib/components/ui/dialog/dialog-content.svelte -->
<DialogPrimitive.Portal>
  <DialogPrimitive.Overlay
    class="fixed inset-0 z-40 bg-scrim duration-[120ms]
      data-[state=open]:animate-in data-[state=open]:fade-in-0
      data-[state=closed]:animate-out data-[state=closed]:fade-out-0"
  >
    {#if overlay}{@render overlay()}{/if}
  </DialogPrimitive.Overlay>
  <DialogPrimitive.Content
    class={cn(
      "fixed left-1/2 top-1/2 z-50 grid w-[min(420px,90vw)] -translate-x-1/2 -translate-y-1/2 gap-4
       rounded-[6px] border border-hairline-strong bg-surface-overlay p-4 text-body
       duration-[120ms]
       data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95
       data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95
       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      className
    )}
    {...rest}
  >
    {#if children}{@render children()}{/if}
  </DialogPrimitive.Content>
</DialogPrimitive.Portal>
```

```bash
npm i tw-animate-css          # then add `@import "tw-animate-css";` to src/lib/app.css
```

Kept at 120 ms to stay inside DESIGN §4's transition cap. Enter zooms from
0.95, exit fades — the skill's subtle-exit shape, not a dramatic one.

### R2 — Stable chain selection (no layout shift)

```svelte
<!-- ChainGrid.svelte — base row reserves the border slot -->
<TableRow
  class={cn(
    "chain-row h-6 border-l-2 border-l-transparent",
    selectedStrike === row.strike ? "border-l-accent bg-row-selected" : "",
  )}
>
```

This is byte-for-byte the pattern `Watchlist.svelte:321,327` already uses, so
the two dense lists stay visually consistent.

### R3 — Gutter focus ring

```css
/* App.svelte — next to the existing .gutter rule */
.gutter:focus-visible {
  box-shadow: inset 0 0 0 2px var(--focus-ring);
}
```

The handle still lights amber while dragging (`.gutter.drag-active .gutter-line`),
so the drag cue is unchanged; focus now has a proper 2 px ring.

### R7 — Theme icon cross-fade (CSS-only, no motion dependency)

```svelte
<!-- Header.svelte — replace the {#if} swap -->
<button variant="ghost" size="icon" class="relative text-muted-foreground hover:text-accent-active" ...>
  <span
    class="absolute inset-0 flex items-center justify-center transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)]"
    class:scale-100:class:opacity-100:blur-0={theme === "dark"}
  >
    <Sun class="size-4" />
  </span>
  <span
    class="flex items-center justify-center transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)]"
    class:opacity-0:scale-[0.25]:blur-[4px]={theme === "dark"}
  >
    <Moon class="size-4" />
  </span>
</button>
```

Svelte 5 note: the ternary-class shorthand above is illustrative — in runes mode
use `class={theme === "dark" ? "opacity-0 scale-[0.25] blur-[4px]" : "opacity-100 scale-100 blur-0"}`.
Exact skill values: scale `0.25→1`, opacity `0→1`, blur `4px→0`, ease
`cubic-bezier(0.2,0,0,1)`. The non-absolute icon (Moon) keeps the layout size.

### R6 — In-place chain refresh (pseudocode for the merge)

```ts
async function refreshSilently(): Promise<void> {
  if (loading) return;
  const resp = await get<OptionsResponse>(`/api/intelligence/options?...`);
  if (!resp.contracts) return;
  const byKey = new Map(resp.contracts.map((c) => [contractKey(c.strike, sideOf(c.option_type)), c]));
  for (const row of rows) {          // keep array identity — no rows rebuild
    for (const side of ["ce", "pe"] as const) {
      const c = side === "ce" ? row.ce : row.pe;
      if (!c) continue;
      const fresh = byKey.get(contractKey(c.strike, side));
      if (fresh) Object.assign(c, fresh);   // fine-grained per-cell updates
    }
  }
  // ...expiry bookkeeping unchanged
}
```

This keeps the WS-style fine-grained reactivity that Svelte 5 gives per
property, instead of re-rendering the whole grid on a 15 s cadence.

---

## 6. Verification

Read-only review; no browser session was available.

- **Verified by source inspection:** all token usages against `design.css` /
  `DESIGN.md`; tabular-nums coverage; transition-property lists (grep — no
  `transition: all`); the flash animation timing; reduced-motion guards present
  on pip/live pulses and absent on kill-pulse; `border-collapse: collapse` on
  the chain table (basis for R2); palette/listbox ARIA wiring.
- **Verified by grep:** zero `antialiased`/font-smoothing matches in
  `web/src`; zero `motion`/`framer-motion` in `package.json`; icon set is 100 %
  Lucide.
- **Not verified (no dev server):** actual motion at 10 % speed in a browser
  Animations panel; pixel-exact contrast checks in light theme; the ~1–2 px
  chain-selection shift magnitude on a real render. All three are small,
  deterministic consequences of the cited CSS/classes, but should be eyeballed
  during implementation.

## 7. Verdict

**Needs changes** — 0 HIGH, 6 MEDIUM, 7 LOW, none blocking. The six MEDIUM
items (R1–R6) are each ≤ 1–2 h; the first three are ~1 h combined and deliver
most of the visible difference. Nothing in this review touches the price-law,
the accent discipline, or the density contract — the DESIGN.md rules all hold
and are the reason the surface is already this coherent.

### Suggested execution order

1. **R2 + R3 + R4** (~35 min) — the consistency/a11y/rendering trivials.
2. **R1** (~30 min) — dialog animation, the highest-feel change.
3. **R6** (~1–2 h) — the only perf item that matters on a 15 s cadence.
4. **R5** hit areas, then the LOW batch (R7–R13) opportunistically.
