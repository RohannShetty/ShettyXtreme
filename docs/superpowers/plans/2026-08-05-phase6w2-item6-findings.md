# Phase 6 Wave 2 Item #6 — TableRow rest-props forwarding (findings)

Date: 2026-08-05 · Phase 6 W2 item #6 (tiny primitive fix) · Frontend-only change

## Summary

`TableRow` (`src/shettyxtreme/terminal/web/src/lib/components/ui/table/table-row.svelte`)
did not forward rest props. Its `Props` type was `{ class?: string; children?: Snippet }`
and the `<tr>` received only the merged `class`. Consumers could not pass
`data-state`, `aria-*`, `data-*`, or `onkeydown`-style handlers — which blocked
proper a11y and the component's own `data-[state=selected]:*` styling variants
(they were dead code; nothing could ever set `data-state` on the `<tr>`).

The fix follows the exact convention already used by the sibling primitives
`TableHead` (`HTMLThAttributes`) and `TableCell` (`HTMLTdAttributes`): type the
props against the Svelte element attribute interface, destructure `...rest`, and
spread `{...rest}` on the element. `class` and `children` keep their existing
behavior (class merge via `cn()` is unchanged; snippet rendering unchanged).

## Changes

Files in ownership scope:

- `src/shettyxtreme/terminal/web/src/lib/components/ui/table/table-row.svelte`
  - `Props` now typed as `HTMLAttributes<HTMLTableRowElement> & { class?: string; children?: Snippet }`.
    Note: there is **no** `HTMLTrAttributes` export in `svelte/elements` (verified
    against `node_modules/svelte/elements.d.ts` — `tr` maps to
    `HTMLAttributes<HTMLTableRowElement>`, exported at line 751; siblings use the
    per-element interfaces `HTMLThAttributes`/`HTMLTdAttributes` which do exist).
  - `const { class: className, children, ...rest }: Props = $props();`
  - `<tr ... {...rest}>` spread added after the `cn()` class expression, matching
    the `TableHead`/`TableCell` pattern.
- `src/shettyxtreme/terminal/web/src/lib/components/ui/table/table-row.test-harness.svelte` (new)
  - Harness rendering `<TableRow data-state="selected" aria-selected="true" data-testid="row" onkeydown={...}>`.
- `src/shettyxtreme/terminal/web/src/lib/components/ui/table/table-row.test.ts` (new)
  - Vitest test asserting `data-state`/`aria-selected` land on the `<tr>`, the
    component's base `border-b` class survives the merge, and the `onkeydown`
    handler in rest props actually fires (counter increments via
    `fireEvent.keyDown`).

## Regression check

Existing consumers (`ChainGrid.svelte`, `PositionsRiskStrip.svelte`) pass only
`class` to `TableRow` — behavior unchanged (`class` is destructured before
`...rest`, so it never leaks into the spread; the `cn()` merge is untouched).
`TableHead`/`TableCell` were already typed this way, so this brings `TableRow` to
parity rather than introducing a new pattern.

## Verification

- `npm run check` → **0 errors / 0 warnings attributable to this item** (see note
  below on pre-existing errors).
- `npm run build` → **success** (vite production build, `../static/` bundle regenerated).
- `npm run test` (vitest) → **17/17 passed** across 7 files, including the new
  `table-row.test.ts`. (First full-suite run showed 14; subsequent runs are stable
  at 17 — the delta is the pre-existing untracked `ChainGrid.test.ts`, 3 tests,
  which is part of the in-flight refactor in the shared working tree, not this item.)

## Pre-existing `svelte-check` errors — NOT caused by this item

`svelte-check` reports **6 errors in `ChainGrid.svelte`** (lines 183–186:
`Property 'iv'/'bid'/'ask' does not exist on type 'Partial<TickPayload> & { symbol?: unknown; }'`).
These are in the in-flight refactor work already present in the working tree
(`ws.ts` and `ChainGrid.svelte` are both modified/untracked from before this
session; `ChainGrid.test.ts` is untracked too). Proven pre-existing by stashing
the `table-row.svelte` change and re-running: the same 6 `ChainGrid` errors appear
(plus 1 error in the new test harness, which is expected — the harness uses
`data-state`, which only type-checks once the fix is present). After restoring the
fix, the error count returns to exactly the 6 pre-existing `ChainGrid` errors;
none are in files owned by this item.

Note: the first `npm run check` in this session reported "0 errors" — subsequent
runs are deterministic at 6 errors in `ChainGrid.svelte`. This is svelte-check's
language-server incremental cache surfacing the in-flight `ws.ts`/`ChainGrid`
type drift on later runs; it is unrelated to the table-row change.

## Files touched (ownership scope only)

- `src/shettyxtreme/terminal/web/src/lib/components/ui/table/table-row.svelte`
- `src/shettyxtreme/terminal/web/src/lib/components/ui/table/table-row.test-harness.svelte` (new)
- `src/shettyxtreme/terminal/web/src/lib/components/ui/table/table-row.test.ts` (new)
