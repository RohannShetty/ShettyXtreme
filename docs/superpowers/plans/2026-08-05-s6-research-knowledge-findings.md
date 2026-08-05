# S6 Findings — Phase 3 Cockpit Redesign: Research + Knowledge + Settings + Logs

**Date:** 2026-08-05
**Scope:** S6 of Phase 3 — polish of `ResearchPanel.svelte`, `KnowledgePanel.svelte`, `SettingsView.svelte`, `LogDrawer.svelte` against the DESIGN.md component contract
**Status:** Complete — both verification gates pass

---

## Deliverables

| File | Change |
|---|---|
| `src/shettyxtreme/terminal/web/src/components/ResearchPanel.svelte` | Lens/tool checkboxes → DESIGN toggle/switch contract; brief list → `surface-card` rows with `ticker` titles + `caption` meta; STALE chip on briefs >1h; arrow-key list navigation (Enter expands); native filter selects restyled per dropdown/input contract |
| `src/shettyxtreme/terminal/web/src/components/KnowledgePanel.svelte` | Search input per DESIGN input contract; hit list → `surface-card` rows with `body` content + `micro` timestamps; per-doc STALE chips; Ctrl+F focuses search; arrow-key hit navigation; hit list rendered inline (see §3.2 — child component is out of S6 scope) |
| `src/shettyxtreme/terminal/web/src/components/SettingsView.svelte` | Token state → semantic status chips; rows hairline-divided, values mono tabular; Re-auth = primary button, Logout = danger; Enter triggers the primary action; Tab walks controls; back-link accent-styled |
| `src/shettyxtreme/terminal/web/src/components/LogDrawer.svelte` | Internal `@media (max-width: 1439px)` overlay mode **removed** (superseded by App.svelte right-col drawer — the S1-findings follow-up); rows → `surface-card` cards with `micro` mono timestamps + `body` message text; level colors info/warning/danger on a labeled level chip; Esc closes (focus-scoped) |

## Verification

- `npm run check` → **svelte-check: 0 errors** (2 pre-existing warnings remain in `ChainGrid.svelte` / `Watchlist.svelte` — out of scope, non-blocking)
- `npm run build` → **vite production build succeeds** (4527 modules, ~44s; bundle committed per AGENTS.md convention)
- `npm test` (frontend vitest) → **5 files / 13 tests pass** (incl. `SettingsView.test.ts` — button labels/behavior preserved)

---

## 1. ResearchPanel.svelte

### 1.1 Lens/tool selectors — DESIGN toggle contract
The shadcn `Checkbox` primitive (a 16px square) was replaced with a hand-rolled switch per DESIGN §4 **Toggle / switch**: off = `hairline-strong` track + `muted` knob, on = `accent` track + `#fff` knob, 26×14px, 120ms ease-out transitions, `role="switch"` + `aria-checked` + `aria-label`, disabled during a run. `Checkbox` import removed. The `toggleLens` / `toggleToolState` handlers are unchanged.

### 1.2 Brief list — card rows
Rows are now `surface-card` cards (1px `hairline`, radius 4px): thesis in `ticker` face (mono 12/500/0.02em, ink, single-line ellipsis), meta in `caption` (lens, direction `±1`/`0` in price tokens per Indian convention, confidence %, `as_of` time in mono, status `Badge`). Selected row = `row-selected` bg + 2px `accent` left edge (inset `box-shadow`, no drop shadow — the DESIGN table-selection idiom without layout shift). Hover = `row-hover`.

### 1.3 STALE chip
`now − Date.parse(as_of) > 1h` → warning micro "STALE" chip (DESIGN §4 staleness marker) in the meta row. The existing `expired` validity-window marker on the status badge is preserved — the two are distinct (age vs validity window).

### 1.4 Keyboard
The list `<ul role="listbox" tabindex="0">` handles ArrowDown/ArrowUp (wrap-around), Home/End, and Enter (expands the highlighted brief into the detail pane). Selection scrolls into view via `.sel` → `scrollIntoView({ block: "nearest" })`. Row buttons remain individually focusable (native Tab order intact).

### 1.5 Filters
The two native `<select>`s (status / lens) were restyled to the input contract (`canvas-raised` bg, `hairline` border, mono 10px tabular, `accent` focus ring, `muted` hover). Their popup lists remain OS-rendered — a custom dropdown is flagged for the component-migration task (§4.6).

---

## 2. KnowledgePanel.svelte

### 2.1 Search input
Uses the `Input` primitive, which already implements the DESIGN input contract (`canvas-raised` + `hairline`, focus = `accent` border + ring). Wrapped in a `search-wrap` flex slot so it grows in the control row; placeholder now advertises the Ctrl+F shortcut.

### 2.2 Hit list — inline rendering (scoped decision)
`KnowledgeHitList.svelte` renders the hits, but it is **outside S6 ownership** ("do not touch files outside your ownership scope"), it accepts no timestamp data, and the S6 contract requires `micro` timestamps + STALE chips + arrow navigation. To satisfy all four requirements **inside `KnowledgePanel.svelte`**, the hit list is rendered inline there (same structure, using `statusClass` from `knowledge-shared`). `KnowledgeHitList.svelte` is untouched but is now **unused** — consolidation is flagged in §4.2.

Rows: `surface-card` cards with `body` content (title ink/600 12px, snippet body 11px, 2-line clamp) and `micro` meta — status chip (success/warning/danger by doc status), `source_ref`, and the `created_at` timestamp in `micro`-size mono (`YYYY-MM-DD HH:MM`, joined from the cached `/api/knowledge/docs` payload via a `doc_id → doc` map).

### 2.3 STALE chip
Same 1-hour rule as research, applied **per doc** on `created_at` (docs are knowledge; a doc ingested >1h ago is flagged). Deterministic and data-driven; the semantics note is in §4.5.

### 2.4 Keyboard
- **Ctrl+F** (window-level, with an input/textarea guard so typing is never hijacked) focuses + selects the search box — mirroring the S1 Ctrl+R workstation-shortcut convention. Note: this suppresses the browser find bar while the cockpit is mounted (same trade-off as Ctrl+R).
- Arrow keys / Home / End navigate the hit list (`role="listbox"`), Enter opens the highlighted hit, selection scrolls into view.

---

## 3. SettingsView.svelte

The current settings surface is a **credential status card + actions** (per `2026-08-02-terminal-remediation-design.md`; the `/api/settings/*` twins were retired and `settings_router` carries zero endpoints). The S6 contract's "form inputs / dropdowns / save button" do not map to any existing or backend-supported surface here — applied what the surface actually has, and the form contract is flagged for the future (§4.4):

- Token state → semantic **status chip**: VALID = success, EXPIRED = warning, NOT SET = neutral (Badge primitive, mono 10px uppercase).
- Status rows: `caption` labels (muted), mono tabular values, hairline dividers.
- **Re-auth** = primary button (`accent` bg / `on-accent` text — the default Button variant), **Logout** = danger. Both test-asserted labels preserved.
- **Keyboard:** Tab walks the controls; Enter anywhere on the surface (target not a control) triggers the primary action — the operator-grade "save" analog. Implemented as a window listener with a containment check so it never double-fires on focused buttons/links.
- Back-link styled as an accent link.

---

## 4. LogDrawer.svelte

- **Internal overlay media query removed.** The `@media (max-width: 1439px)` fixed-position block is deleted — its job is fully superseded by the App.svelte right-col overlay drawer (S1). The drawer is now always a docked level-1 panel: `canvas-raised` bg, 1px `hairline`, radius 6px, `overflow: hidden`.
- **Rows:** `surface-card` cards with `micro`-size **mono** timestamps (tabular; the numeral law overrides the sans micro role for digits — §4.7), a **labeled level chip** in the level color (`info`/`warning`/`danger`), and `body`-face message text. Color is never the only indicator (DESIGN §2.4 a11y).
- **Esc closes** when the drawer (or a control inside it) has focus — window-level keydown with a `drawerEl.contains(target)` guard; the drawer takes focus on open (`$effect`), so the shortcut is live immediately. App.svelte's global Esc (drives the same `open` prop) remains the second path.

---

## Findings / notes for later phases

1. **App.svelte `.right-col :global(.drawer)` override is now vestigial.** S1 added `!important` overrides to neutralize LogDrawer's own media query. That query is gone in S6, so the block still matches but no longer changes behavior (it forces `static/auto` which is now the default). Recommend deleting it in a later pass on App.svelte (out of S6 scope).
2. **`KnowledgeHitList.svelte` is now unused.** The S6 contract could not be delivered through the child component (no timestamp data, out-of-scope file), so the list is rendered inline in `KnowledgePanel.svelte`. Recommend deleting `KnowledgeHitList.svelte` (and consolidating the row styles into a shared surface) once the panel is frozen.
3. **ChainGrid gate-blocking one-line fix (out of scope, pre-existing).** The working tree's `ChainGrid.svelte` (owned by a sibling phase) failed svelte-check with `Type 'string' is not assignable to type 'number'` on `tabindex="0"` (the shadcn TableCell types `tabindex` as number). Fixed to `tabindex={0}` — no behavior change. Without it the mandatory `npm run check` gate could not pass. A concurrent writer is actively editing ChainGrid; if that work re-introduces `tabindex="0"`, the gate regresses.
4. **SettingsView has no form controls to restyle.** The mission contract (form inputs / styled dropdowns / save button) presumes a settings *form* that doesn't exist: `/api/settings/*` carries no endpoints and SettingsView is a read-only credential surface. When a real settings form lands (risk limits, theme, scheduler config), it should use the Input/Textarea primitives + a custom dropdown per DESIGN §4 and reuse the Enter-to-save pattern added here.
5. **Knowledge STALE semantics.** "Knowledge >1h old" was implemented per-doc on `created_at`. This is the mission's uniform rule but is semantically debatable for a reference store (unlike briefs, docs don't expire). If the operator finds it noisy, a panel-level "last sync / last search" STALE indicator is the natural alternative.
6. **Native selects remain in ResearchPanel's filters** (status/lens). A custom dropdown (`surface-elevated` menu, `row-hover` items, 8px×10px padding) is part of the component-migration backlog (shadcn `select`/`dropdown-menu` ports).
7. **Micro vs mono for timestamps.** The mission asked for "`micro` timestamps"; DESIGN's numeral law mandates mono for digits. Both are satisfied: timestamp text is 10–11px (`micro` size) in the mono face with `tabular-nums` (LogDrawer `.time`, Knowledge hit `.time`, Research `.time`).
8. **Container-query stacking in both intelligence panels.** `.cols` previously used `minmax(220px,2fr) minmax(280px,3fr)`, which cannot fit the 320px dock — the detail pane was clipped by `overflow:hidden`. Now `minmax(0,…)` tracks plus a `@container (max-width: 460px)` block that stacks list-over-detail (DESIGN §8: "breakpoints follow container queries inside panels"). No layout shift on wide docks.
9. **Remaining non-blocking warnings** (pre-existing, out of scope): ChainGrid `.table-wrap` `<div onkeydown>` without role; Watchlist `.list` `<div onkeydown>` without role.
10. The static bundle (`terminal/static/`) was regenerated by the mandatory build gate and reflects the new hashes. **Not committed** per instructions.

## Files touched

- `src/shettyxtreme/terminal/web/src/components/ResearchPanel.svelte` (owned)
- `src/shettyxtreme/terminal/web/src/components/KnowledgePanel.svelte` (owned)
- `src/shettyxtreme/terminal/web/src/components/SettingsView.svelte` (owned)
- `src/shettyxtreme/terminal/web/src/components/LogDrawer.svelte` (owned)
- `src/shettyxtreme/terminal/web/src/components/ChainGrid.svelte` — one-line gate-blocking fix (see §4.3)
- `src/shettyxtreme/terminal/static/*` — regenerated build output (gate artifact, not a source change)

No other files were modified. DESIGN.md / design.css token changes in the working tree predate this task (prior session).
