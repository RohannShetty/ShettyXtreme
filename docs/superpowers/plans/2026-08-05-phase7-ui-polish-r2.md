# Phase 7 — UI Polish R2: Reserve 2px chain-row border (no selection jitter) — Implementation Report

**Date:** 2026-08-06
**Scope:** `src/shettyxtreme/terminal/web/src/components/ChainGrid.svelte` (selected chain row no longer shifts content on arrow-key navigation)
**Status:** Complete — `npm run check` 0 errors / 0 warnings; `npm run build` succeeds
**Source review:** `docs/superpowers/plans/2026-08-05-phase7-ui-review.md` R2 (High, XS, ~1 line)

---

## Deliverables

| File | Change |
|---|---|
| `src/shettyxtreme/terminal/web/src/components/ChainGrid.svelte` | Base chain row now reserves the 2px left-border slot with `border-l-2 border-l-transparent`; the selected state only swaps the border color to `border-l-accent` (dropping the redundant `border-l-2` from the selected string). Content no longer shifts ~1–2 px when selection moves. |
| `src/shettyxtreme/terminal/static/` | Regenerated committed bundle (vite build, AGENTS.md convention) |

## Implementation

Before (`ChainGrid.svelte:395-399`):

```svelte
<TableRow
  class={cn(
    "chain-row h-6",
    selectedStrike === row.strike ? "border-l-2 border-l-accent bg-row-selected" : "",
  )}
>
```

After:

```svelte
<TableRow
  class={cn(
    "chain-row h-6 border-l-2 border-l-transparent",
    selectedStrike === row.strike ? "border-l-accent bg-row-selected" : "",
  )}
>
```

This is byte-for-byte the pattern `Watchlist.svelte` already uses (`.row` → `border-left: 2px solid transparent`; `.row.selected` → `border-left-color: var(--accent)`), so the two dense lists stay visually consistent. Because the border slot is reserved on every row, `border-collapse: collapse` on the table no longer causes the row's left edge / first-cell content to shift when the selection moves — arrow-key strike navigation is jitter-free.

## Verification

- `npm run check` → **0 errors, 0 warnings** (svelte-check, whole tree).
- `npm run build` → **vite production build succeeds** (1m 9s, 4634 modules).
- `git diff` confirms the change is 2 lines in `ChainGrid.svelte` only — nothing else in `src/` touched.
- No visual change to the selected state itself: still `border-l-accent` + `bg-row-selected`.
- Pixel-level eyeball of the arrow-key shift was not run (no dev server session); the fix is the deterministic CSS consequence of reserving the border slot, identical to the already-shipped watchlist behavior.

## Notes

- The working tree already carried uncommitted Phase 7 changes (review doc, wave-2 docs, earlier polish edits) before this task; this report covers only the R2 change.
- Not committed, per task scope.
