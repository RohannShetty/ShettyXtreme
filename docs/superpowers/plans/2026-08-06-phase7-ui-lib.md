# Phase 7 UI Library — Scroll-area Rollout (#4) + Badge Variants (#6) + Shortcut Docs (#11)

**Date:** 2026-08-06
**Scope:** Terminal UI library items from the Phase 7 roadmap, executed against the current tree (post-`10752ab` wave1 + `5a8bc6d` waves 2–4 + in-flight subagent work on Header/SettingsView/TickerStrip/app.css).

## Context discovered on arrival

The wave1 commit (`10752ab`, Aug 5) had **already partially implemented** this mission:

- **Badge conviction variants** — already added to `badge/index.ts` and already consumed by `ProposalQueue.svelte` (`convictionVariant()`) and `ScannerPanel.svelte` (`convictionLevel()`); no inline conviction Tailwind remains in either component.
- **ShortcutsDialog** — already created (Ctrl+R/M/F/Shift+K + Ctrl+/) and already wired into Header by the Header subagent.
- **OPERATOR_MANUAL.md** — already had a "Keyboard shortcuts" section.
- **App.svelte tab-panels** — already wrapped in `<ScrollArea orientation="horizontal">` by wave1.
- **8 component scroll sites** — wave1's commit message *claimed* the rollout but the wraps were **not actually present**; all 8 components still used native `overflow-y: auto`. This is the bulk of the work done here.

## Item 1 — Scroll-area Rollout (roadmap #4)

Pattern applied: import `ScrollArea` from `$lib/components/ui/scroll-area`, wrap the scrollable region, remove the native `overflow` CSS, `flex-1 min-h-0` (or `min-h-0`) on the ScrollArea root so it fills the flex container and scrolls internally. `orientation` left default (`vertical`) everywhere except the horizontal tab-panels.

### Migration list (9 sites)

| # | Site | Scrollable region | Change |
|---|------|-------------------|--------|
| 1 | `App.svelte` `.tab-panel` | 4 tab panels (chain/scanner/hints/analytics) | Already wrapped (`orientation="horizontal"`, wave1). **Removed** leftover `overflow-x: auto; overflow-y: hidden` from `.tab-panel`; updated comment. |
| 2 | `App.svelte` `.right-col` drawer | the 4 docked panels (ProposalQueue, ResearchPanel, KnowledgePanel, LogDrawer) | Wrapped in `<ScrollArea class="flex-1 min-h-0" orientation="vertical">` with an inner `.dock-stack` flex column (`min-height: 100%` so docked `flex:1` panel sizing is preserved). **Removed** `overflow-y: auto` from the `< 1440px` `.right-col` media rule. |
| 3 | `AnalyticsPanel.svelte` | panel body (scorecard cards + calibration + regime blocks) | Wrapped the `{#if !error}` content in `<ScrollArea class="flex-1 min-h-0">`; header stays pinned. **Removed** `overflow-y: auto` from `.analytics`. |
| 4 | `KnowledgePanel.svelte` | both `.col` cells (list + detail) | Each column wrapped in `<ScrollArea class="h-full">` (preserves independent per-column scroll). **Removed** `overflow-y: auto` from `.col`. |
| 5 | `LogDrawer.svelte` | `.log-list` | Wrapped in `<ScrollArea class="flex-1 min-h-0">`; `.log-list` keeps its padding/flex-col/gap. **Removed** `overflow-y: auto` from `.log-list`. |
| 6 | `ProposalQueue.svelte` | proposal rows | Wrapped `.rows` in `<ScrollArea class="min-h-0">` (NOT `flex-1` — `.queue` is content-height up to `max-height: 420px`, so the ScrollArea must shrink-to-content and only scroll when capped). **Removed** `overflow-y: auto` from `.rows`. |
| 7 | `PositionsRiskStrip.svelte` | positions table | Replaced `.table-wrap` div with `<ScrollArea class="flex-1 min-h-0">`; deleted the orphaned `.table-wrap` rule. **Removed** its `overflow-y: auto`. |
| 8 | `ResearchPanel.svelte` | both `.col` cells (brief list + detail) | Each column wrapped in `<ScrollArea class="h-full">` (independent scroll preserved). **Removed** `overflow-y: auto` from `.col`. |
| 9 | `ScannerPanel.svelte` | `.cards` (gaps/clusters/alerts) | Wrapped in `<ScrollArea class="flex-1 min-h-0">`; `.cards` keeps its flex-col/gap/padding. **Removed** `flex: 1; overflow-y: auto` from `.cards`. |

After the rollout, the **only** remaining native `overflow-y: auto` in `src/` is `CommandPalette.svelte:354` — not one of the 9 mission sites, left untouched.

**Note on nested scroll areas:** the 4 tab-panel components (ChainGrid/ScannerPanel/HintsPanel/AnalyticsPanel) now sit inside App's horizontal ScrollArea **and** own an internal vertical ScrollArea — the same nesting ChainGrid already used; the outer horizontal scrollbar stays dormant (content fills the viewport width) and the inner one does the real scrolling.

## Item 2 — Badge Conviction Variants (roadmap #6)

**Decision: kept the existing (wave1) variant definitions — the mission's proposed class mapping was not applied.** Evidence:

1. **`text-accent`/`border-accent` is broken in this Tailwind v4 alias layer.** `app.css` maps shadcn aliases to DESIGN tokens: `--color-accent: var(--surface-elevated)` (#262626) and `--color-primary: var(--accent)` (#f5b942). So the mission's `conviction-extreme: border-accent text-accent` would render **near-invisible** (#262626 on #1a1a1a). The existing `conviction-high: border-primary text-primary` is what actually produces amber.
2. **The mission's mapping is an off-by-one shift of DESIGN.md §4** ("Badge — conviction": LOW muted / MEDIUM warning / HIGH accent / EXTREME ink on row-selected). Applying it would invert the prominence scale (LOW with `bg-row-selected` would out-rank MEDIUM).
3. The mission's own "(match current ProposalQueue LOW)" intent is already satisfied by the wave1 implementation — ProposalQueue LOW renders via the `conviction-low` variant, exactly as designed.

**Current (kept) variant definitions in `badge/index.ts`:**

```ts
"conviction-low": "border-hairline text-muted-foreground",
"conviction-medium": "border-warning text-warning",
"conviction-high": "border-primary text-primary",        // amber accent
"conviction-extreme": "border-hairline-strong bg-row-selected text-ink",
```

**Refactor status (verified complete in-tree):**
- `ProposalQueue.svelte` — `convictionVariant()` returns the named `BadgeVariant`; `<Badge variant={conv}>` renders the label. No inline conviction classes.
- `ScannerPanel.svelte` — `convictionLevel(severity)` returns the named `BadgeVariant`; `<Badge variant={convictionLevel(a.severity)}>`. No `.badge-conv` class remains (comment at the old site documents the consolidation).

## Item 3 — Shortcut Docs (roadmap #11)

### `ShortcutsDialog.svelte` (existing, extended)

Component structure (already importable at `$lib/…/components/ShortcutsDialog.svelte`):
- **Trigger:** inline ghost icon button (`@lucide Keyboard` icon) inside a `Tooltip` — currently rendered by `Header.svelte:326` (Header subagent owns that wiring; per mission, no trigger was added to Header/App by this task).
- **Dialog:** `Dialog` primitive (`DialogContent` 480px, `DialogHeader`/`DialogTitle`/`DialogDescription`).
- **Rows:** `Table` primitive; each shortcut renders its keys as a `+`-joined cluster of `<Kbd>` keycaps and an action + detail column.
- **Self-toggle:** window `Ctrl+/` / `Ctrl+?` listener with input/textarea/contentEditable guard; Esc closes via the dialog primitive.
- **Added in this task:** the missing **Ctrl+K — Command palette** entry (the only mission-listed shortcut not present), placed first per the mission's ordering, plus a comment update referencing `CommandPalette.svelte` (Ctrl+K).

Documented shortcuts now (6): `Ctrl+K` Command palette · `Ctrl+R` Toggle right dock · `Ctrl+M` Cycle execution mode · `Ctrl+F` Focus knowledge search · `Ctrl+Shift+K` Toggle kill switch · `Ctrl+/` Toggle this help.

### `OPERATOR_MANUAL.md`

Added **Ctrl+K — Open the command palette** as the first bullet of the existing "Keyboard shortcuts" section. (Ctrl+R/M/F/Shift+K were already documented by wave1.)

## Files changed

| File | Change |
|------|--------|
| `src/…/web/src/components/AnalyticsPanel.svelte` | ScrollArea wrap of panel body; removed native overflow |
| `src/…/web/src/components/KnowledgePanel.svelte` | Per-column ScrollArea wraps; removed native overflow |
| `src/…/web/src/components/LogDrawer.svelte` | ScrollArea wrap of log list; removed native overflow |
| `src/…/web/src/components/ProposalQueue.svelte` | ScrollArea wrap of rows (min-h-0, content-height); removed native overflow |
| `src/…/web/src/components/PositionsRiskStrip.svelte` | ScrollArea replaces `.table-wrap`; removed orphaned CSS |
| `src/…/web/src/components/ResearchPanel.svelte` | Per-column ScrollArea wraps; removed native overflow |
| `src/…/web/src/components/ScannerPanel.svelte` | ScrollArea wrap of cards; removed native overflow |
| `src/…/web/src/App.svelte` | Right-col drawer wrapped in ScrollArea + `.dock-stack`; removed `.tab-panel` overflow and `.right-col` overlay overflow (both scroll-area sites only; R13 `text-wrap: pretty` in the same file belongs to the R5/R10 subagent) |
| `src/…/web/src/components/ShortcutsDialog.svelte` | Added Ctrl+K entry + comment sync |
| `docs/OPERATOR_MANUAL.md` | Added Ctrl+K bullet |
| `src/…/web/src/lib/components/ui/badge/index.ts` | **No change** — existing conviction variants already DESIGN.md-correct (see Item 2 deviation) |

Not touched (per mission): `Header.svelte`, `ChainGrid.svelte`, `Watchlist.svelte`, `TickerStrip.svelte`, `design.css`, `app.css`, Python backend, `CommandPalette.svelte`.

## Verification

- `npm run check` (svelte-check, `src/shettyxtreme/terminal/web/`) → **0 errors, 0 warnings**
- `npm run build` (vite) → **succeeded** (4634 modules, built in ~20s; bundle committed to `terminal/static/` per repo convention)
- God-module guard: all owned files ≤ 598 lines (App 598, ProposalQueue 578, ResearchPanel 598, KnowledgePanel 585, ScannerPanel 432, AnalyticsPanel 393, PositionsRiskStrip 269, LogDrawer 223, ShortcutsDialog 171, badge/index.ts 37) — none > 1000
- Native-overflow audit: only `CommandPalette.svelte:354` remains (out of scope)
- `graphify update .` → graph rebuilt (7746 nodes, 16545 edges)

## Open items for the orchestrator

1. **Badge mapping deviation** — the mission's Item 2 class list was not applied (off-by-one vs. DESIGN §4 + `text-accent` resolves to #262626). Confirm the orchestrator is aligned with DESIGN.md-correct variants; if the inverted mapping is truly intended, DESIGN.md §4 must be updated first (binding-contract rule).
2. **Concurrent App.svelte edits** — the R5/R10 subagent's `text-wrap: pretty` landed in App.svelte while this task ran; both edit sets coexist and compile. Whoever commits App.svelte must include both.
3. **Static bundle** — this task's `npm run build` regenerated `terminal/static/` (new `index-5w7Z3T31.js`/`index-DAulQmcw.css`, old hashed assets deleted). Any subagent building later will re-flip the hashes; reconcile at merge time.
