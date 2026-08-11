# Phase 6 · Wave 3 Item #5 — ChainGrid Container-Query (kill 720px min-width): Findings

**Date:** 2026-08-05
**Status:** Complete — svelte-check 0 errors/0 warnings, build OK, 17 frontend tests passing
**Recon source:** `docs/superpowers/plans/2026-08-05-phase6-recon.md` §7/§10 (roadmap #5) + `docs/superpowers/plans/2026-08-05-s1-shell-findings.md` §1.2 (item 4)
**Scope:** `src/shettyxtreme/terminal/web/src/components/ChainGrid.svelte` (CSS + one class attribute only — zero behavior/API change)

---

## 1. What changed

| Location | Before | After |
|----------|--------|-------|
| `.chain` panel rule | `min-width: 720px;` (hard limit on the panel root) | `min-width: 0;` + `container-type: inline-size;` — the panel shrinks with its flex parent |
| `<Table>` root | `class="text-[12px]"` | `class="chain-table text-[12px]"` (adds a hook on the table root div for `:global` styling) |
| New rules (wide) | — | `:global(.chain-table) { width: 100% }` — table stretches to fill the panel |
| New rules (narrow) | — | `@container (max-width: 719px) { :global(.chain-table) { width: 720px } }` — the chain keeps its full 720px layout and the `ScrollArea` (`orientation="both"`, already in `.table-wrap`) scrolls it horizontally **inside** the panel |

No JavaScript changed. No component behavior, tick handling, keyboard nav, or data flow touched.

## 2. Key findings

### 2.1 The ScrollArea was always capable — the min-width starved it
`<ScrollArea class="h-full w-full" orientation="both">` already renders a horizontal scrollbar when its content overflows. But with `min-width: 720px` on `.chain`, the *panel* was 720px wide, the table always fit inside it, and nothing ever overflowed the ScrollArea — so `.tab-panel`'s `overflow-x: auto` (App.svelte) was the only thing preventing viewport overflow, and the custom scrollbar never engaged. The fix removes the panel-level min-width and lets the *table* (not the panel) carry the 720px floor inside a container query. The scroll now lives at the right layer: the ScrollArea's custom horizontal scrollbar.

### 2.2 Why a container query, not a media query
DESIGN §8 is binding: *"Breakpoints follow container queries inside panels; panels never overflow the viewport horizontally."* The chain's usable width is not the viewport — it's the center column between the 260px rail and (at ≥1440px) the 320px right dock. A viewport media query can't know that (e.g. at 1024px the right dock is an overlay, so the chain panel is ~740px despite the viewport being narrower than 1440). `container-type: inline-size` on `.chain` matches the established pattern in `ResearchPanel.svelte` / `KnowledgePanel.svelte` (`.knowledge`/`.research` both use it for their dock stacking).

### 2.3 DESIGN §8 "never squeeze" → scroll, not collapse
The task offered three options. Option C (collapse columns to card lists at <768px) would violate DESIGN §8's *"Data tables never reflow mid-row"*. Option A (column density) alone can't fit 7 mono numeric columns under ~720px without squeezing. **Option B (internal scroll) is the DESIGN-conformant answer**, with the container query (Option A's mechanism) deciding *when* to scroll: wide panels stretch the table, narrow panels pin the full 720px layout and scroll. Both rules are dead simple and cheap.

### 2.4 Layout verification at the three target widths
`.workspace` = `260px | minmax(0,1fr) | 320px`, gaps 8px, padding 8px; right dock becomes a `position:fixed` overlay < 1440px (`@media (max-width: 1439px)`):

| Viewport | Center column ≈ | Chain panel | `@container` fires? | Result |
|----------|-----------------|-------------|---------------------|--------|
| **1440px** | 828px | 828px | No (>719px) | Table stretches to fill; no scrollbar |
| **1024px** | 740px | 740px | No (>719px) | Table stretches to fill; no scrollbar |
| **768px** | 484px | 484px | **Yes** (<719px) | Table pinned at 720px; ScrollArea scrolls horizontally inside the panel — **no viewport overflow** |

The `720px` floor inside the query equals the removed hard min-width, so narrow rendering is pixel-identical to the old wide layout — just scrolled.

### 2.5 Compiled-output proof
`vite build` output (`static/assets/index-gVdAyW0l.css`):
- `.chain.svelte-…{display:flex;flex-direction:column;min-width:0;height:100%;container-type:inline-size}` — hard min-width gone
- `.chain-table{width:100%}@container (max-width: 719px){.chain-table{width:720px}}` — both states compiled correctly (Svelte handles `:global()` inside `@container`)

## 3. Out-of-scope follow-ups (noted, not changed)

- **App.svelte `.tab-panel` `overflow-x: auto` is now dormant** — nothing inside a panel overflows anymore. It can be tightened to `overflow: hidden` (or removed) with the comment update in a future App.svelte wave. Left untouched per ownership scope.
- Sub-768px (DESIGN §8 "card lists") remains a later, separate effort — this item only had to hold ≥768px, which it does.

## 4. Verification

- `npm run check` (svelte-check) → **0 errors, 0 warnings**
- `npm run build` (vite) → success; committed bundle regenerated (`terminal/static/` — required side effect of the mandated build gate)
- `vitest run` → **17 passed / 7 files** (incl. all `ChainGrid.test.ts` live-tick tests — no chain functionality regression)
- Grep of compiled CSS: zero `min-width:720px` remaining
- Backend pytest suite not run — change is CSS-only in a frontend component; zero Python overlap
