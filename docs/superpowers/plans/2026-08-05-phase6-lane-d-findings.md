# Phase 6 Lane D — Findings: Tab keep-alive + LIVE banner

**Date:** 2026-08-05
**Status:** Complete · v0.13.0 baseline (1116 tests) · frontend-only change
**Scope:** Roadmap #4 (tab keep-alive) → #8 (LIVE banner 4th grid row), serialized on `App.svelte`
**Files changed:**
- `src/shettyxtreme/terminal/web/src/App.svelte`
- `src/shettyxtreme/terminal/web/src/components/ModeSwitcher.svelte`
- `docs/superpowers/plans/2026-08-05-phase6-lane-d-findings.md` (this file)

---

## 1. Task 1 — Tab keep-alive (roadmap #4)

### 1.1 What changed

Scanner / Hints / Analytics panels switched from conditional mounting to
hidden-not-unmounted, matching the ChainGrid pattern:

```
{#if $activeTab === "scanner"} <div class="tab-panel">…  →  <div class="tab-panel" class:hidden={$activeTab !== "scanner"}>
```

All four center panels now stay mounted for the lifetime of the cockpit.
Switching tabs toggles `display:none` via the `hidden` class instead of
destroying and recreating the component instances. Consequences:

- **Component-local `$state` survives tab switches** — scroll positions, applied
  filters, loaded data, selected rows, in-flight requests are no longer lost.
- **`onMount` runs once at boot** — WS `onMessage` subscriptions and polling
  timers no longer re-establish (and re-fire initial fetches) on every switch.
- **`display:none` removes hidden panels from layout and the accessibility
  tree**, so no `inert`/`aria-hidden` additions are needed.

### 1.2 FINDING — pre-existing cascade-layer bug: `class:hidden` was silently defeated

The ChainGrid pattern this task was asked to match (`App.svelte:93-95`, shipped
since Phase 3) **was not actually hiding the chain panel**. The chain grid has
been visible on all four tabs:

- Svelte scoped component CSS (`.tab-panel.svelte-1n46o8q { display: flex }`) is
  emitted **unlayered**.
- Tailwind v4 emits `.hidden { display: none }` inside **`@layer utilities`**.
- Per CSS Cascade Layers, **unlayered author declarations beat layered ones
  regardless of specificity** → `display: flex` won, `hidden` did nothing.
- Confirmed in the committed bundle (`static/assets/index-DV_TFu9M.css`):
  `.tab-panel.svelte-1n46o8q{…display:flex…}` at ~43678 (unlayered) vs
  `.hidden{display:none}` at ~52223 (inside `@layer utilities{…}` opened at
  ~51512).

**Fix applied:** a scoped rule pins the hidden state at higher specificity in
the same unlayered context:

```css
.tab-panel.hidden { display: none; }   /* → .tab-panel.hidden.svelte-1n46o8q */
```

This makes keep-alive actually work for all four panels **and repairs the
pre-existing chain-panel visibility bug** for free.

### 1.3 Accepted cost (documented in recon §4.3)

Three extra panel mounts/fetches at boot (Scanner/Hints/Analytics `onMount` run
immediately). Panels idle hidden; this is the recommended option-1 trade-off.
If boot cost ever becomes unacceptable, the follow-up is store-backed state
(recon §4.3 option 2) or lazy first-mount.

---

## 2. Task 2 — LIVE banner 4th grid row (roadmap #8)

### 2.1 What changed

**App.svelte grid (4th row + measurement var):**

- `.app-grid` declares `--header-bottom: 52px` (8px grid padding + 44px header
  strip) — the banner's viewport-space anchor, replacing JS measurement.
- A **4th grid row (`auto 36px minmax(0,1fr) auto`) is reserved only while a
  banner is mounted**, via:

  ```css
  .app-grid:has(:global(.live-banner)) {
    grid-template-rows: auto 36px minmax(0, 1fr) auto;
  }
  ```

  The `:has()` guard means the dense 3-row layout is byte-identical to before
  outside LIVE sessions — no permanent 36px gap, no workspace shift when
  toggling. When LIVE, the workspace starts below the banner slot, so content
  is **never covered** by the bar (previously the fixed bar overlaid the
  workspace's top 28px).

**ModeSwitcher.svelte (banner consumes the var):**

- Deleted `bannerTop` state, `measureHeader()`, the `resize` listener, and the
  inline `--banner-top` style — the banner now uses
  `top: var(--header-bottom, 52px)` (fallback keeps the old 52px default if
  ever rendered outside `.app-grid`).
- Styling unchanged and DESIGN-§4 compliant: 36px, `danger` at 10% on
  `surface-card`, `hairline-strong` border-bottom, leading pulsing dot + body
  text, **no dismiss** (danger bars never dismiss), `role="alert"`,
  `pointer-events: none` (informational only).

### 2.2 Coupling contract

`--header-bottom` is the single measurement point. It is hardcoded to `52px`
and documented in both files to stay in sync with `.head`'s `height: 44px` +
`.app-grid`'s `padding: 8px`. If the header strip height ever changes, update
`.head` in `Header.svelte` **and** `--header-bottom` in `App.svelte` — the
comment at each site names the other.

### 2.3 Browser support note

The `:has()` selector is the one modern-CSS dependency introduced (Chrome 105+,
Edge 105+, Firefox 121+, Safari 15.4+). Acceptable for a local workstation
terminal running a Vite-built app; flagged here in case an old-embedded-browser
requirement ever appears. The Svelte compiler accepts `:has(:global(...))` with
no warnings (svelte-check 0/0).

---

## 3. Verification (all passed)

| Gate | Result |
|------|--------|
| `npm run check` | **0 errors, 0 warnings** |
| `npm run build` | **success** (4527 modules, 39.6s) |
| `npm run test` (vitest) | **13/13 passed** (5 files) |
| No file > 1000 lines | App.svelte 302 · ModeSwitcher.svelte 326 |

Compiled-bundle assertions (new `static/assets/index-CRgHdBTF.css`):
- `.app-grid.svelte-1n46o8q{…--header-bottom: 52px}` ✓
- `.app-grid.svelte-1n46o8q:has(.live-banner){grid-template-rows:auto 36px minmax(0,1fr) auto}` ✓
- `.tab-panel.hidden.svelte-1n46o8q{display:none}` ✓
- `.live-banner.svelte-17yhkps{position:fixed;top:var(--header-bottom, 52px);…}` ✓

No stray references remain (`bannerTop`, `--banner-top`, `measureHeader` →
grep: zero matches).

---

## 4. Notes for the next lane

- The `:has()` grid swap is the only place that reads DOM presence; if a future
  task replaces the `{#if isLive}` banner with a store-driven one, the selector
  still matches as long as the `.live-banner` class stays.
- `CHANGELOG.md` / version bumps are **not** part of this lane (no release).
- Not committed, per lane instructions.
