# Phase 7 Wave 2 — Command palette (roadmap #2) — Implementation Report

**Date:** 2026-08-05
**Scope:** `src/shettyxtreme/terminal/web/src/components/CommandPalette.svelte` (⌘K quick navigation + actions)
**Status:** Complete — `npm run check` 0 errors / 0 warnings; `npm run build` succeeds; full suite 1197 passed / 0 failed / 0 skipped
**Constraint compliance:** App.svelte and Header.svelte NOT modified (integration deferred to the wiring phase); no new dependencies (bits-ui `computeCommandScore` reused — recon §1.2 verified bits-ui 2.18.1 exports `Command` + `computeCommandScore`)

---

## Deliverables

| File | Change |
|---|---|
| `src/shettyxtreme/terminal/web/src/components/CommandPalette.svelte` | New self-contained ⌘K palette: module-scoped `open()`/`close()` + `paletteOpen` store, fuzzy search over 8 nav targets + 3 actions, keyboard nav (↑/↓/Enter/Esc), DESIGN-token styling on the existing `Dialog` port |
| `src/shettyxtreme/terminal/static/` | Regenerated committed bundle (vite build, AGENTS.md convention) |

## Verification

- `npm run check` → **0 errors, 0 warnings** (whole tree, including parallel-lane files).
- `npm run build` → **vite production build succeeds** (17.9s, 4630 modules).
- `npm test` (vitest, web) → **17 passed / 17** (7 files).
- Python suite (AGENTS.md gate): `pytest tests/` → **1197 passed / 0 failed / 0 skipped** (66.3s).
- Gate greps: no `openalgo` import in the new file; file length 408 lines (< 1000 god-module guard).

---

## 1. Implementation details

### 1.1 Architecture — module-scoped controller

The component is split into two scripts:

- **`<script module>`** — exports the control surface: `paletteOpen` (`writable` store), `open()`, `close()`. This is the API App.svelte imports in the integration phase:
  ```ts
  import CommandPalette, { open, close } from "./components/CommandPalette.svelte";
  ```
  No refs, no `bind:` needed — the store is the single source of truth and the instance script renders the `Dialog` off `$paletteOpen`.
- **Instance script** — the item registry, fuzzy matcher, keyboard handling, and focus management.

The Dialog port (`$lib/components/ui/dialog`) provides the level-3 overlay contract for free (DESIGN §6: `surface-overlay` + `scrim` + 1px `hairline-strong`), including the focus scope, Escape-to-close, and scroll lock from bits-ui's primitive. Width is widened to `w-[min(560px,90vw)]` and internal padding overridden (`gap-0 p-0`) so the palette renders as a chrome-less command surface.

### 1.2 Item registry — 8 navigation targets + 3 actions

Navigation targets (center tabs via the `activeTab` store, routes via `location.hash`):

| id | label | action |
|---|---|---|
| `nav-watchlist` | Watchlist | `location.hash = "/"` (rail is on the main view) |
| `nav-chain` / `nav-scanner` / `nav-hints` / `nav-analytics` | Chain / Scanner / Hints / Analytics | `activeTab.set(...)` + hash `/` |
| `nav-research` / `nav-knowledge` | Research / Knowledge | hash `/` + **`sx:open-dock` window event** (they live behind App's drawer state) |
| `nav-settings` | Settings | `location.hash = "/settings"` |

Actions:

| id | label | action |
|---|---|---|
| `act-theme` | Toggle theme | `applyTheme(getTheme() === "dark" ? "light" : "dark")` — direct (theme.ts is frontend-only) |
| `act-kill` | Toggle kill switch | **`sx:toggle-kill-switch` window event** |
| `act-mode` | Cycle execution mode | **`sx:cycle-mode` window event** |

The three window events are the deliberate integration seams: disarm carries the typed-confirm safety flow (F-EXEC-001) and LIVE arming carries the typed-confirm dialog (D10), both owned by KillSwitch/ModeSwitcher respectively. **The palette never bypasses those dialogs** — it only asks, exactly like the existing Ctrl+Shift+K / Ctrl+M window listeners do. This preserves the "platform proposes, human approves" invariant while keeping the component self-contained. Integration-phase wiring is documented in §3.

### 1.3 Fuzzy search

Reuses `computeCommandScore` from bits-ui (zero new deps). Each item scores against `label + keywords`; items with `score > 0` are kept, sorted descending by score. Empty query returns the registry order (all 11 items). The theme icon is derived (`Sun` in dark → switch to light, `Moon` in light) to mirror the Header's toggle affordance.

### 1.4 Keyboard navigation

- **Ctrl+K / ⌘K** (window listener, registered in `onMount`) — opens the palette. Toggles closed if already open. Uses the exact input-guard pattern from KnowledgePanel/ShortcutsDialog: never hijacks while the operator is typing in an INPUT/TEXTAREA/contentEditable. `Ctrl+Shift+K` is explicitly excluded so the kill-switch shortcut keeps priority (recon §4 risk mitigation: "Ctrl+K global handler must not fight Ctrl+M/R/F/Shift+K").
- **↑ / ↓** — move selection (wraps; guarded against empty result set).
- **Enter** — run the selected item's action, then close.
- **Esc** — closes via the Dialog primitive's EscapeLayer (`escapeKeydownBehavior: "close"` default), which also fires `onOpenChange(false)` → `close()`.
- **Mouse** — hover moves selection, click runs the item.

### 1.5 Design tokens

- Query field is **mono** (DESIGN §3: command/terminal text → JetBrains Mono; tabular-nums comes free via the global `.mono` class).
- Item labels in Inter 13px `--ink`; hints in mono 10px `--faint`; icons `--muted` → `--accent` when selected.
- Selected row: `--row-selected` fill + 2px `--accent` left edge (DESIGN §2.4 "selected row edge" = accent).
- Focus indication: `:focus-within` turns the input's bottom hairline `--accent` (no focus ring removal anywhere).
- Footer key hints use the `Kbd` chip (`ui/kbd`): ↑↓ navigate · ↵ select · Esc close.

### 1.6 a11y

- `DialogTitle` rendered `sr-only` ("Command palette") so the dialog has an accessible name.
- Input is a `combobox` with `aria-controls` → results `listbox`, `aria-activedescendant` pointing at the selected option id, `aria-expanded`.
- Each result is a real `<button role="option" aria-selected=...>`, so Enter/mouse both work and screen readers get the selection state.
- `svelte-check` a11y rules: 0 warnings.

## 2. API surface

| Symbol | Kind | Source |
|---|---|---|
| `open()` | `() => void` | module export — sets `paletteOpen` true, resets query + selection, focuses input |
| `close()` | `() => void` | module export — sets `paletteOpen` false |
| `paletteOpen` | `Writable<boolean>` | module export — for advanced consumers (e.g. bind in App) |
| `CommandPalette` | component | default export — mount `<CommandPalette />` anywhere; registering its own Ctrl+K listener means *mounting it alone enables the shortcut* |

Usage from App.svelte (integration phase):
```svelte
<script lang="ts">
  import CommandPalette, { open } from "./components/CommandPalette.svelte";
  // optional: call open() from a header button or own shortcut handler
</script>
<CommandPalette />
```

## 3. Window-event integration contracts (wired in the integration phase)

| Event | Dispatched by palette item | Expected listener (integration phase) |
|---|---|---|
| `sx:open-dock` | Research, Knowledge | App.svelte: `window.addEventListener("sx:open-dock", () => (drawerOpen = true))` |
| `sx:toggle-kill-switch` | Toggle kill switch | KillSwitch.svelte: forward to its existing `toggle()` (keeps the DISARM typed-confirm) |
| `sx:cycle-mode` | Cycle execution mode | ModeSwitcher.svelte: forward to its existing `cycleMode()` (keeps the LIVE typed-confirm) |

These events carry no `detail` in v1; if the integration phase wants Research vs Knowledge to scroll the dock to a specific panel, `sx:open-dock` can grow a `detail: { panel: "research" | "knowledge" }`.

## 4. Non-goals / untouched

- **App.svelte / Header.svelte** — not modified (both are parallel-lane files; Header two-row and ticker strip are separate wave-2 items).
- **ui/`command/` port** — not created. The recon §1.2 offered a full shadcn-svelte command port as an option, but the component spec asked for the existing Dialog + fuzzy search, which the single-file approach satisfies with the already-verified bits-ui scorer. No new files in `ui/`.
- **Symbol/instrument search** (palette v2 in recon §1.2) — intentionally out of scope; needs `/api/instruments/search` endpoint which doesn't exist yet.
- **Backend, tests, docs** (besides this report) — untouched.

## 5. Ops notes

- Working tree carries parallel-lane changes (Header two-row, TickerStrip, other wave-2 items) — not touched here. The regenerated static bundle reflects the merged current source, per the committed-bundle convention (same as the badge-variants report).
- Nothing committed (per task instruction).
