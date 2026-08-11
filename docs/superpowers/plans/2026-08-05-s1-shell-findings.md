# S1 Findings — Phase 3 Cockpit Redesign: Shell & Header

**Date:** 2026-08-05
**Scope:** S1 of Phase 3 — terminal shell layout (`App.svelte`), header with LTP hero (`Header.svelte`), positions/risk strip panel styling (`PositionsRiskStrip.svelte`)
**Status:** Complete — both verification gates pass

---

## Deliverables

| File | Change |
|---|---|
| `src/shettyxtreme/terminal/web/src/App.svelte` | Right-col → overlay drawer <1440px (Ctrl+R toggle); horizontal overflow contained per panel; 3-row grid + 3-col workspace preserved |
| `src/shettyxtreme/terminal/web/src/components/Header.svelte` | LTP hero (`number-xl`) for the selected symbol, live via WS ticks, exchange from watchlist, Indian price coloring |
| `src/shettyxtreme/terminal/web/src/components/PositionsRiskStrip.svelte` | `surface-card` bg + `hairline` border + 6px panel radius — no longer bare on canvas |

## Verification

- `npm run check` → **svelte-check: 0 errors, 0 warnings**
- `npm run build` → **vite production build succeeds** (bundle committed per AGENTS.md convention)

---

## 1. App.svelte — shell layout

### 1.1 Right-col no longer disappears <1440px

Previously `.right-col { display: none }` below 1440px hid ProposalQueue (execution approvals), Research, Knowledge, and the logs — a safety issue flagged in `2026-08-05-current-ui-analysis.md` (§1). Now, below 1440px the right dock becomes a **level-3 overlay drawer** (DESIGN §6): `surface-overlay` bg, `hairline-strong` left border, `width: min(380px, 88vw)`, `transform: translateX(100%) → 0`, 120ms ease-out — mirroring the LogDrawer's existing overlay pattern.

**Toggle surface:** `Ctrl+R` (global keydown, `preventDefault()` — the browser reload is intentionally suppressed while the cockpit is mounted), `Esc` (close), the header logs button (`drawerOpen`), and a drawer-internal close button in a new "Right Dock" head bar that renders only in overlay mode.

**Key decision — LogDrawer nesting conflict:** LogDrawer already self-overlays below 1440px (its own `@media` block sets `position: fixed`). If both it and the right-col drawer fixed-positioned, they would fight for the viewport edge. The fix lives in App.svelte scoped CSS: `.right-col :global(.drawer)` overrides LogDrawer's responsive mode back to static/docked inside the drawer. The `!important` is deliberate and documented — it neutralizes another component's media-query behavior without touching LogDrawer.svelte (out of scope). `drawerOpen` now drives *both* the right-col drawer and the LogDrawer's `open` state, so the header logs button and Ctrl+R are one consistent affordance.

### 1.2 Horizontal overflow fixed (DESIGN §8)

- `.workspace` dropped `overflow-x: auto` → now `overflow: hidden`. The grid tracks are fixed `260px | minmax(0,1fr) | 320px`, so the workspace can never push the viewport wide.
- `.tab-panel` gained `overflow-x: auto; overflow-y: hidden` — the chain grid's hard `min-width: 720px` (ChainGrid, out of scope) now scrolls *inside* the center column instead of overflowing. Each panel's own `.table-wrap { overflow: auto }` handles vertical. This is the "panels scroll internally, never overflow the viewport" contract.

### 1.3 Grid preserved

3-row grid (Header / workspace / PositionsRiskStrip) and 3-col workspace (rail 260px | center flex | right-col 320px) intact; `grid-template-rows: auto minmax(0,1fr) auto` unchanged.

---

## 2. Header.svelte — LTP hero

### 2.1 Data flow

- **Selection:** `selectedSymbol` store (`$lib/selection.ts`) via `$derived($selectedSymbol)`. The store carries only the symbol string — no exchange.
- **Exchange:** the tick WS payload (`projections.py:55`) carries no exchange either, so the header builds a symbol→exchange map from `GET /api/watchlist` on mount + every 30s health cycle. Falls back to `"NSE"`.
- **LTP:** live via `onMessage("tick", ...)` — a per-symbol `Record` of `{ltp, change_pct}`. The header tracks the last tick per symbol so ticks arrive independently of selection.
- **Format:** `number-xl` per DESIGN §3.1 — JetBrains Mono (`--font-mono`), 28px/700/32px, `-0.01em`, `tabular-nums`, `toLocaleString("en-IN")` (Indian grouping), 2 decimals. `white-space: nowrap` so the number never wraps.

### 2.2 Price law (Indian convention — never inverted)

- **Persistent color** follows `change_pct` sign: `> 0` → `--price-up` (red `#f6525c`), `< 0` → `--price-down` (green `#2ebd85`). This matches the watchlist and the backend's session direction.
- **Tick flash** follows the tick-vs-previous-tick move and, per DESIGN §3.2 ("price flash toggles color weight, never font weight or size"), switches to `--price-up-strong` / `--price-down-strong` for 150ms plus the `flash-up`/`flash-down` background fade — no layout jitter.
- No status tokens in the price column; no price tokens on buttons/chips.

### 2.3 44px strip + fit

DESIGN §5 header anatomy (logo/session · active symbol + `number-xl` LTP cluster · kill switch · mode/market-hours right) is respected: the hero sits immediately right of the brand, kill switch stays left-of-center, `.health` keeps `margin-left: auto`.

Full-width estimate put the header at ~1310px with everything visible — too wide for a 1024–1439 viewport. A **progressive compaction cascade** (documented in the CSS) yields the decorative chrome first while the safety set (ModeSwitcher, KillSwitch, pip, market-hours, cred chip, theme, logs toggles) never collapses (DESIGN §8):
- `≤1360px` — hide the `%` change chip (redundant with watchlist)
- `≤1240px` — hide the brand title (logo `SX` stays)
- `≤1080px` — hide the session clock, tighten gap/padding

`.head` is fixed `height: 44px`, `overflow: hidden` — the grid row resolves to exactly 44px and nothing pushes the viewport wider.

---

## 3. PositionsRiskStrip.svelte

Bare canvas panel → level-1 hairline card: `background: var(--surface-card)`, `1px var(--hairline)`, `border-radius: 6px` (panel radius). Zero functional changes — the positions table, margin bar, and risk chips are untouched.

---

## Technical notes / findings for later phases

1. **`selectedSymbol` needs an exchange.** The store is a bare string; the header had to derive exchange from a second REST call. For S2+ consider extending `selection.ts` to `{symbol, exchange}` (or pushing `WatchItem` in full) — removes the map + fallback.
2. **LogDrawer vs right-col drawer overlap is resolved at the App level with `!important`.** The cleaner long-term fix is deleting LogDrawer's internal `@media (max-width: 1439px)` block (its overlay behavior is fully superseded by the right-col drawer) — tracked for the component-migration task.
3. **Ctrl+R suppresses browser reload** while the cockpit is mounted. This is deliberate (workstation shortcut per mission), but should be documented for the operator; it does not affect other routes.
4. **ChainGrid `min-width: 720px`** is what forces the tab-panel horizontal scroll at <~990px center widths. A container-query approach (DESIGN §8) or making the chain column internally scrollable would remove the last hard min-width.
5. **Header below ~1000px** will clip (all compaction steps exhausted). DESIGN §8 targets ≥768 with degraded stacking; a two-row header or chip-density pass is the S2+ fallback if sub-1024 support matters.
6. The static bundle (`terminal/static/`) was regenerated by the mandatory `npm run build` gate and reflects the new bundle hashes. **Not committed** per instructions.

## Files touched

- `src/shettyxtreme/terminal/web/src/App.svelte` (owned)
- `src/shettyxtreme/terminal/web/src/components/Header.svelte` (owned)
- `src/shettyxtreme/terminal/web/src/components/PositionsRiskStrip.svelte` (owned)
- `src/shettyxtreme/terminal/static/*` — regenerated build output (gate artifact, not a source change)

No other files were modified. DESIGN.md / design.css token changes in the working tree predate this task (prior session).
