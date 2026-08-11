# Phase 7 Wave 1 — Shortcut Documentation (#11) — Findings

**Date:** 2026-08-05
**Status:** Implemented; verification gate BLOCKED by a pre-existing type error in a parallel-lane file (see §4)
**Scope:** Roadmap §1.11 (shortcut help dialog + OPERATOR_MANUAL.md) — frontend + docs only, zero Python changes

---

## 1. What was built

### 1.1 `docs/OPERATOR_MANUAL.md` — "Keyboard shortcuts" section added
Inserted between "What you see on screen" and "Errors explained in plain words". Lists all four defined shortcuts in plain-English (manual is written for a human, not a programmer):

| Shortcut | Action |
|---|---|
| Ctrl+R | Show/hide the right-hand panel (logs, proposals, research, knowledge) |
| Ctrl+M | Cycle OBSERVER → PAPER → LIVE → back to OBSERVER (LIVE still asks for typed confirmation) |
| Ctrl+F | Jump straight to the knowledge search box |
| Ctrl+Shift+K | Kill switch — stops everything instantly, in any mode, on any screen |

Also tells the reader the in-app path to the same list: **Ctrl+/** (or **Ctrl+?**) or the keyboard button at the top right.

### 1.2 `web/src/components/ShortcutsDialog.svelte` — NEW component (self-contained)
- **Trigger:** ghost icon `Button` (Keyboard glyph from `@lucide/svelte`) inside a `Tooltip`, styled identically to the adjacent theme/logs-drawer buttons in `Header.svelte`.
- **Dialog:** built on the existing `Dialog` port (`$lib/components/ui/dialog`) — `DialogContent` (widened to `w-[min(480px,90vw)]`), `DialogHeader`, `DialogTitle`, `DialogDescription`, `onOpenChange` close contract matching `ModeSwitcher.svelte`/`KillSwitch.svelte`.
- **Table:** uses the existing `Table` port (`$lib/components/ui/table`) — `TableHeader`/`TableHead` ("Keys" | "Action"), `TableBody`/`TableRow`/`TableCell`. Description cell overrides the default `whitespace-nowrap` with `whitespace-normal` and splits action (12px ink, semibold) from detail (11px muted) lines.
- **Key rendering:** `Kbd` component (`$lib/components/ui/kbd`) per keycap, joined by a faint `+` separator span (mono face, DESIGN §4 chip convention).
- **Keyboard trigger:** window `keydown` for **Ctrl+/** and **Ctrl+?** (`event.key === "/" || "?"`) toggles the dialog; reuses the KnowledgePanel input-guard pattern (`INPUT`/`TEXTAREA`/`isContentEditable` → don't hijack). `preventDefault()` suppresses browser quick-find. Esc closes via the bits-ui dialog primitive (default).
- **Single source of truth:** `SHORTCUTS` array in this component is the documented registry; a comment cross-references the owning handlers — `App.svelte` (Ctrl+R), `ModeSwitcher.svelte` (Ctrl+M), `KnowledgePanel.svelte` (Ctrl+F), `KillSwitch.svelte` (Ctrl+Shift+K).

### 1.3 `web/src/components/Header.svelte` — help button mounted
`<ShortcutsDialog />` placed in the header strip between the theme toggle and the logs-drawer toggle (one import + one usage, +3 lines). The dialog's keyboard shortcut is mounted alongside the other cockpit-level shortcuts, so it only lives on the `/` route where the Header renders.

### 1.4 Ctrl+/ registry note
The component registers its own window listener (like `ModeSwitcher`/`KillSwitch` do) rather than threading state through `App.svelte`'s single `onKeydown` — keeps `App.svelte` untouched and the dialog self-contained. No key conflicts: Ctrl+/ and Ctrl+? are unused by any existing handler.

## 2. Files touched (strictly in scope)

| File | Change |
|---|---|
| `docs/OPERATOR_MANUAL.md` | +9 lines — "Keyboard shortcuts" section |
| `web/src/components/ShortcutsDialog.svelte` | NEW — help dialog + trigger + Ctrl+/ listener |
| `web/src/components/Header.svelte` | +3 lines — import + mount `<ShortcutsDialog />` |
| `docs/superpowers/plans/2026-08-05-phase7-shortcut-docs.md` | This report |

No commits made. No files outside scope touched.

## 3. Verification results

| Gate | Result |
|---|---|
| `npm run build` | ✅ PASS — `✓ built in 50.06s`, bundle written to `../static/` (index-*.js 432.88 kB, index-*.css 88.18 kB) |
| `npm run check` | ⚠️ 1 ERROR — **not in this lane's files** (see §4); 0 errors/warnings in `ShortcutsDialog.svelte` / `Header.svelte` |
| Manual doc check | ✅ OPERATOR_MANUAL.md lists all 4 shortcuts + Ctrl+/ trigger |
| Python suite | Not run — zero Python changes in this lane; parallel Lane-D agent has uncommitted Python edits in flight (see §4), so a full-suite run now would test a moving target |

## 4. BLOCKING ISSUE — pre-existing `npm run check` error (not caused by this lane)

```
KnowledgePanel.svelte:116 (loadStatus):
  status = await get<KnowledgeStatusResponse>("/api/knowledge/status");
Error: Type 'KnowledgeStatusResponse' is not assignable to type
  '{ docs: number; proposed: number; activated: number; tags: number; last_sync_at: null; }'.
  Types of property 'last_sync_at' are incompatible:
    Type 'string | null' is not assignable to type 'null'.
```

- **Root cause:** the parallel Wave-1 Lane-D agent (§1.9 knowledge last-sync, per recon §3 lane D) is mid-edit. Their uncommitted diff added `last_sync_at: string | null` to `KnowledgeStatusResponse` in `web/src/lib/api.ts` AND changed the `status` state initializer in `KnowledgePanel.svelte` to `$state<KnowledgeStatusResponse>({ ..., last_sync_at: null })`. The state variable is being typed from the object-literal initializer (`last_sync_at: null` literal) rather than the generic, so the response (`string | null`) is not assignable.
- **Proof it's not this lane:** `git status` shows `KnowledgePanel.svelte` and `api.ts` are dirty **only** via that lane's diff (`.git` baseline is clean for `npm run check`). This lane's diff touches only `Header.svelte`, `OPERATOR_MANUAL.md`, and the new component. svelte-check reports exactly 1 error, in that one file.
- **Recommendation:** the owning lane (or orchestrator) should type the state variable consistently — e.g. initializer `last_sync_at: null as string | null`, or drop the redundant explicit object type and rely on the generic. **Not fixed here** to avoid clobbering the parallel agent's in-progress edit (recon §3 mandates one writer per file).

## 5. Notes for follow-up (out of scope, deferred by design)
- The `SHORTCUTS` registry is intentionally a component-local constant; when roadmap §1.2 (command palette) lands, the recon proposes a shared shortcuts registry — this array is the natural seed.
- Ctrl+/ was chosen over Ctrl+K (reserved for the palette) and Ctrl+H (backspace semantics) — flagged here so §1.2 doesn't collide.
- Manual §4 has "Ctrl+/ (or Ctrl+?)" — on US layouts `?` is Shift+/; the handler accepts both `event.key` values so Ctrl+Shift+/ works too.
