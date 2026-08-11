# Phase 7 Wave 1 — Badge conviction variants (roadmap #6) — Findings

**Date:** 2026-08-05
**Scope:** `ui/badge/` conviction variants + consolidation of the two conviction-badge consumers (`ProposalQueue.svelte`, `ScannerPanel.svelte`)
**Status:** Complete — `npm run check` 0 errors / 0 warnings; `npm run build` succeeds

---

## Deliverables

| File | Change |
|---|---|
| `src/shettyxtreme/terminal/web/src/lib/components/ui/badge/index.ts` | Added 4 `conviction-{low,medium,high,extreme}` variants to `badgeVariants` (mono 10px uppercase base unchanged, DESIGN §4 chip) |
| `src/shettyxtreme/terminal/web/src/components/ProposalQueue.svelte` | Replaced ad-hoc `convictionClass()` (raw Tailwind on the Badge `class` prop) with typed `convictionVariant()` → `variant={...}`; label via `convictionLabel()` |
| `src/shettyxtreme/terminal/web/src/components/ScannerPanel.svelte` | Replaced scoped `.badge-conv` span + 5 CSS blocks with the Badge primitive `variant={convictionLevel(severity)}`; deleted the `.badge-conv*` styles |
| `src/shettyxtreme/terminal/static/` | Regenerated committed bundle (vite build, AGENTS.md convention — gate artifact, not committed) |

## Verification

- `npm run check` → **0 errors, 0 warnings** (whole tree, including parallel-lane files).
- `npm run build` → **vite production build succeeds** (1m6s, 4630 modules).
- Compiled CSS spot-check (bundle `index-SnnRnmqZ.css`): all variant utilities resolve to the intended tokens:
  `.text-primary{color:var(--accent)}` `.border-primary{border-color:var(--accent)}` `.bg-row-selected{background-color:var(--row-selected)}` `.text-ink{color:var(--ink)}` `.border-hairline{border-color:var(--hairline)}` `.text-muted-foreground{color:var(--muted)}` `.border-warning/.text-warning{...var(--warning)}`.

---

## 1. Variant set

```ts
"conviction-low":      "border-hairline text-muted-foreground",
"conviction-medium":   "border-warning text-warning",
"conviction-high":     "border-primary text-primary",
"conviction-extreme":  "border-hairline-strong bg-row-selected text-ink",
```

Maps 1:1 onto DESIGN.md §4 "Badge — conviction": LOW `{colors.muted}` text / MEDIUM `{colors.warning}` / HIGH `{colors.accent}` / EXTREME `{colors.ink}` on `{colors.row-selected}`. Base class already enforces mono face, 10px, uppercase, 2px radius — nothing per-variant needed.

## 2. Findings worth recording

### 2.1 `text-accent` is a latent color bug — HIGH was near-invisible in ProposalQueue
`app.css` maps the shadcn alias `--color-accent` to `var(--surface-elevated)` (P5a: shadcn "accent" = our hover-fill surface), so `text-accent` compiles to `color:var(--surface-elevated)` — dark-on-dark on the queue card. ProposalQueue's old HIGH (`border-accent-disabled text-accent`) rendered its label in surface gray, not amber. The new variant uses `text-primary`/`border-primary`, which resolve to `var(--accent)` (#f5b942 dark) — exactly what ScannerPanel's scoped `.badge-conv.high { color: var(--accent) }` rendered. **This consolidates both consumers onto the true amber and fixes the ProposalQueue HIGH label visibility.** (Flagged for the contract owner: nothing in `src/` currently references `text-accent`/`bg-accent` with the amber intent — the `accent-*` utilities are only safe for `accent-active`/`accent-disabled`.)

### 2.2 HIGH border unified to full amber
Old split: ProposalQueue HIGH used dim `accent-disabled` border; ScannerPanel used full `--accent` border. Unified on `border-primary` (full amber) per the badge primitive's convention that border matches text (`success/warning/danger/info` all do) and per ScannerPanel's S5 rendering.

### 2.3 Scanner badge size 11px → 10px (alignment, not regression)
`.badge-conv` was mono 11px; the primitive base is `text-[10px]`. The task mandates DESIGN.md tokens (mono, uppercase, 10px), so ScannerPanel conviction chips now render at the canonical badge size alongside ProposalQueue. `.badge-regime` (gap/cluster-type chips) intentionally left as scoped 11px micro — separate concern (S5 §4.3 micro-vs-mono tension, roadmap item, out of this task's scope).

### 2.4 Return-type discipline
Both consumers now type their level functions as `BadgeVariant` (from `ui/badge/index.ts`), so a future variant rename/removal is caught by svelte-check at the call sites — no stringly-typed `class` prop smuggling.

## 3. Non-goals / untouched

- `.badge-regime` in ScannerPanel (regime/gap-type chips) — scoped CSS kept.
- Other Badge consumers (`SettingsView`, `ResearchPanel`, `ResearchBriefDetail`) — no conviction usage, unaffected (variant set is additive).
- Backend, tests, docs (besides this report) — untouched.

## 4. Ops notes

- Working tree carries parallel-lane changes (knowledge-store sync, shortcuts dialog, Header, `tests/wave9/*`) from other Phase 7 lanes — not touched here. The regenerated static bundle reflects the merged current source, per the committed-bundle convention.
- Nothing committed (per task instruction).
