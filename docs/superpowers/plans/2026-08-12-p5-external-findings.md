# P5 EXTERNAL Findings — Color Convention Toggle

**Date:** 2026-08-12 · **Status:** Investigation complete — no code changed · **Phase:** Final (pre-completion)

## TL;DR

The terminal is **already built on a centralized CSS-variable token system** — the change is far smaller than a full sweep:

- **One source of truth**: `src/shettyxtreme/terminal/web/src/lib/design.css` defines `--price-up` (red `#f6525c`), `--price-down` (green `#2ebd85`), `--candle-up/-down`, `--flash-up/-down`, and `-strong`/`-soft` variants, plus `.price-up`/`.price-down` utility classes. Tailwind utilities (`text-price-up`, `border-price-up`) resolve through `app.css` aliases back to the same variables — **no component hardcodes hex** except ONE spot (`RiskHeatmap.sectorBg`).
- **A ready-made precedent exists**: theme selection already ships as `data-theme` on `<html>` + `sx-theme` localStorage + backend `SettingsStore` (`core/settings.py`) + `GET/PUT /api/settings/theme` with WS broadcast (`settings_router.py`) + a segmented control in `SettingsView.svelte`. A color-convention toggle is the same pattern with a second attribute/key.
- **The flip is mostly free**: every directional component binds its class to `price-up`/`price-down` (or `candle-up`/`candle-down`) **semantically** (e.g. `changePct > 0 ? "price-up" : "price-down"`), so swapping the token VALUES in one CSS block re-colors the entire app.
- **The catch — three coupled non-directional uses** must be de-scoped or decoupled before the token swap, or the toggle will incorrectly re-color them:
  1. **CE/PE option-type badges** reuse `price-up`/`price-down` (CE = red, PE = green) in 4 components — categorical, not directional.
  2. **SL/TGT level colors** bind `class="down"` → `var(--price-up)` (red) and `class="up"` → `var(--price-down)` (green) with **inverted class names** (`OrderHistory`, `ProposalQueue`) — level semantics, not tick direction.
  3. **OrderHistory FILLED status badge** uses `price-down` (green) — a status color that already violates DESIGN.md's "status colors never appear in price columns; price colors never appear in status badges" and should be `--success`.
- **Default per requirement**: international (green = up, red = down). This **amends the DESIGN.md "law"** (`red = rise, green = fall — never invert`, line 112) — the design contract must be amended *before* code (P5 spec convention: "DESIGN.md must be amended in P5 step 0 BEFORE code").

---

## 1. Current color convention — where the contract lives

| Source | Lines | Contract |
|---|---|---|
| `DESIGN.md` | 112, 125, 147–154, 163–164 | "Indian price convention is law in BOTH themes: **red = rise, green = fall** — the exact inverse of international convention. Never 'fix' this, never invert it." Token table: `price-up #f6525c`, `price-down #2ebd85`, `candle-up #f6525c`, `candle-down #2ebd85`, `flash-up/flash-down` rgba pairs. |
| `AGENTS.md` | 48 | "DESIGN.md is binding for all UI work … Indian price convention — **red = up `#f6525c`, green = down `#2ebd85` — never 'fix' this**." |
| `.projectos/identity/frozen-rules.md` | (grep hit) | Identity doc references the convention (via `.projectos/governance`). |
| `CHANGELOG.md` | 21, 194 | Records the Phase-3 redesign "Indian price convention preserved: red=up, green=down" and blueprint token system. |

**No backend component emits color** — colors are 100% a frontend presentation concern (grep of `src/**/*.py` for price/candle tokens: zero hits beyond an unrelated docstring about Fyers candle *data*).

---

## 2. Where colors are defined — the token system

### `src/shettyxtreme/terminal/web/src/lib/design.css` (THE single source of truth)

- `:root` / `:root[data-theme="dark"]` block (lines 6–47):
  - `--price-up: #f6525c; --price-up-strong: #ff7a82; --price-up-soft: rgba(246,82,92,0.12)`
  - `--price-down: #2ebd85; --price-down-strong: #3fd9a0; --price-down-soft: rgba(46,189,133,0.12)`
  - `--flash-up: rgba(246,82,92,0.16); --flash-down: rgba(46,189,133,0.16)`
  - `--candle-up: #f6525c; --candle-down: #2ebd85`
- `:root[data-theme="light"]` block (lines 51–91): same hue mapping, down-green darkened to `#1e9e6b` for AA (comment explicitly notes "Price law preserved: red = up, green = down").
- Utility classes `.price-up` / `.price-down` (lines 109–110) + `.flash-up` / `.flash-down` keyframes (111–114).

### `src/shettyxtreme/terminal/web/src/lib/app.css` (Tailwind layer aliases)

- `@theme inline` maps `--color-price-up: var(--price-up)` (and `-strong`, `-soft`, `-flash`, `-down` variants, lines 43–50) so `text-price-up` / `border-price-up` utilities resolve through the same tokens. Header comment: "Never hard-code hex here. (P5a)".
- `@custom-variant dark` keyed to `[data-theme="dark"]` (line 8) — the attribute-driven theming precedent.

### `src/shettyxtreme/terminal/web/src/lib/theme.ts` (persistence precedent)

- `sx-theme` localStorage key → `data-theme` on `<html>`; `initTheme()` called in `main.ts` **before** `mount(App)` (pre-first-paint). `getTheme()` falls back to `"dark"`.

### Backend settings plumbing (persistence precedent)

- `core/settings.py`: `_SPECS` schema dict (line 202–219) with `"theme": _Spec(DEFAULT_THEME, _validate_theme)`; `DEFAULT_THEME = "dark"`, `VALID_THEMES = ("dark", "light")`; `_validate_theme` (line 89) rejects unknowns with `SettingsError`; `SettingsStore.theme()` accessor; SQLite `KVStore` persistence (survives restarts).
- `terminal/api/settings_router.py`: `SettingsUpdate` model (49–52), `ThemeResponse`/`ThemeUpdate` (83–88), `GET/PUT /api/settings/theme` (224–240) — PUT validates, persists, then `ws_bridge.broadcast("theme", {"theme": theme})`. GET/PUT `/api/settings` (202–220) batch path.
- `web/src/lib/api.ts`: `SettingsResponse` (480–485), `setTheme` (510–512).

---

## 3. Color usage inventory — every site that renders up/down

### 3a. Directional usage — SHOULD follow the convention toggle (the intended flip targets)

| Component | Location | What | Binding |
|---|---|---|---|
| `Header.svelte` | 82–97, 480–484 | LTP hero — flash direction then `change_pct` | `ltpColor` derived → `price-up-strong` / `price-down-strong` / `price-up` / `price-down`; `ltpFlash` → `flash-up` / `flash-down`; scoped `.ltp-hero .price-up-strong` → `var(--price-up-strong)` |
| `Watchlist.svelte` | 120–127 | Row LTP color + tick flash | `flashClass` → `flash-up`/`flash-down`; `pnlClass` → `changePct > 0 ? "price-up" : "price-down"` |
| `ChainGrid.svelte` | 190–209, 326–327, 608–612 | Option-chain LTP tick direction + flash | `dirMap` (`up`/`down`), `price-up`/`price-down` + `flash-*` classes; comment "Indian price law: red = up, green = down" (194); `:global(.mono-num)` defers color to global tokens (612) |
| `GreeksPanel.svelte` | 82–84 | **Greeks** — `deltaClass`: `value > 0 ? "price-up" : "price-down"` (net Δ + per-position Δ) | token class |
| `PositionsRiskStrip.svelte` | 80 | **P&L** — `value > 0 ? "price-up" : "price-down"` | token class |
| `RiskHeatmap.svelte` | 101–103, 115–120, 403–406, 517–521 | **P&L** class + sector heat background + delta bars | `pnlClass` token-based; **`sectorBg` HARDCODES `rgba(246, 82, 92, …)` / `rgba(46, 189, 133, …)` in JS (118–119)** — the only component-level hex in the app; also scoped `.price-up/.price-down` (517–521) and bar backgrounds `var(--price-up)` (403–406) |
| `ScannerPanel.svelte` | 190–192 | **Scanner alert** direction → `price-up`/`price-down` (direction string contains "down") | token class |
| `HintsPanel.svelte` | 195–218 | Direction badge UP/DOWN | `.badge-direction.up` → `var(--price-up)`; `.down` → `var(--price-down)` |
| `TickerStrip.svelte` | 54–56, 421–428 | Regime direction caret (red ▲ up, green ▼ down) | `.dir-up` → `var(--price-up)`; `.dir-down` → `var(--price-down)` |
| `CandleChart.svelte` | 70, 180–183 | **Candles** — `close >= open ? "var(--candle-up)" : "var(--candle-down)"` | token var (chart-level, mirrors price tokens) |
| `ResearchPanel.svelte` | 154 | Research direction badge (`direction === 1 → price-up, -1 → price-down`) | token class |
| `ResearchBriefDetail.svelte` | 17 | Same direction mapping | token class |
| `ProposalQueue.svelte` | 645–650 | SL/TGT sum colors (see 3b) | `.sum-row b.up` → `var(--price-up)`; `.down` → `var(--price-down)` |

### 3b. Coupled non-directional usage — MUST be de-scoped before the token swap

1. **CE/PE option-type badges** — `GreeksPanel.svelte:156`, `PositionsRiskStrip.svelte:142`, `OrderHistory.svelte:116`, `ProposalQueue.svelte:243, 252–253`: `option_type === 'CE' ? 'text-price-up' : 'text-price-down'`. Categorical (Call vs Put), NOT up/down. A convention flip would silently turn CE green / PE red.
2. **BUY/SELL side badges** — `OrderHistory.svelte:124–126`: `side === "BUY" → text-price-up (red)`, `SELL → price-down (green)`. Categorical, not directional.
3. **SL/TGT level colors** — `OrderHistory.svelte:139–140, 305–309` and `ProposalQueue.svelte:274–275, 363`: **inverted class naming** — `<b class="down">` for SL binds to `var(--price-up)` (red), `<b class="up">` for TGT binds to `var(--price-down)` (green). These encode level semantics (SL = downside/risk, TGT = upside), not tick direction; wholesale token swap would flip them.
4. **OrderHistory FILLED status badge** — `OrderHistory.svelte:51`: `case "FILLED": return "border-price-down text-price-down"`. Status color reusing a price token — DESIGN.md violation already (status colors must use `--success`/`--warning`/`--danger`/`--info`); would flip green→red under international if left bound.

### 3c. Status/semantic colors — MUST NOT flip (design tokens already separate)

`--success` / `--warning` / `--danger` / `--info` are distinct tokens per DESIGN.md ("Status colors never appear in price columns; price colors never appear in status badges"). Verified in use:
- `OrderHistory.svelte:52–55` (REJECTED→danger, CANCELLED→warning, OPEN→info)
- `TickerStrip.svelte:415–417, 429–431, 439` (regime tone + IV gauge gradient green→amber→red — semantic level encoding, not price direction)
- `Header.svelte` cred chips `.ok/.warn/.mute` (602–626), kill-switch pulse (`app.css` `kill-pulse` uses danger rgba)
- Toasts in `App.svelte:161–172` (alert severity → toast.error/warning/info)
- `RiskHeatmap.svelte:441` risk-alert background (danger rgba)

---

## 4. Toggle architecture — proposed

### 4.1 Design decision (D13 candidate)

Amend DESIGN.md + AGENTS.md: the Indian convention becomes **one of two selectable conventions**, not "law". New binding rule: **default = international (green = up, red = down)**; Indian remains available as the opt-in for operators who prefer it. Hue mapping per convention:

| Token role | Indian (legacy) | International (new default) |
|---|---|---|
| `--price-up` / `--candle-up` / `--flash-up` / `-strong` / `-soft` | red `#f6525c` family | green `#2ebd85` family |
| `--price-down` / `--candle-down` / `--flash-down` / `-strong` / `-soft` | green `#2ebd85` family | red `#f6525c` family |

### 4.2 Frontend — mirror the theme pattern exactly

1. **`design.css`**: introduce a second attribute dimension alongside `data-theme`:
   - `:root[data-convention="indian"]` — the legacy red-up/green-down values (moved out of `:root`).
   - `:root` / `:root[data-convention="international"]` — the new default (green-up/red-down), i.e. **swap the value assignments** of the up/down token pairs only. Everything downstream (`--color-price-up` aliases in `app.css`, `.price-up` utilities, component classes) keeps working unchanged.
   - Both must compose with both themes (`data-theme` dark/light) — the light-theme down-green AA darkening (`#1e9e6b`) follows whichever hue is "down".
2. **New `lib/color-convention.ts`** (mirrors `theme.ts`): `ColorConvention = "indian" | "international"`; key `sx-convention`; `getColorConvention()` (fallback `"international"` — the new default); `applyColorConvention()` sets `document.documentElement.dataset.convention`; `initColorConvention()` called in `main.ts` before mount (pre-first-paint, no flash).
3. **Component changes**: none required for the flip itself — all 14 directional sites bind semantically. The only real code change is the `RiskHeatmap.sectorBg` hardcode (convert to a CSS class using `var(--price-up-soft)`-style tokens or `color-mix`).
4. **Controls** (optional but expected):
   - `SettingsView.svelte`: segmented control "Price colors: Indian / International" mirroring the Theme card (lines 397–432).
   - `Header.svelte` toggle (near the theme toggle, line 311) and/or `CommandPalette.svelte` command (`act-color-convention`, mirroring `act-theme` at 147–155).
   - Live-updates: like theme, apply locally first then reconcile with backend (SettingsView `onChangeTheme` pattern, 185–203).

### 4.3 Backend — persist as a setting

1. `core/settings.py`: add `DEFAULT_COLOR_CONVENTION = "international"`, `VALID_COLOR_CONVENTIONS = ("indian", "international")`, `_validate_color_convention` (mirror `_validate_theme`, 89–93), `_SPECS["color_convention"] = _Spec(DEFAULT_COLOR_CONVENTION, _validate_color_convention)` (line 202 block), `SettingsStore.color_convention()` accessor (mirror 266–267).
2. `terminal/api/settings_router.py`: add `color_convention: str | None` to `SettingsUpdate` (49–52) + `SettingsResponse` (76–80); new `GET/PUT /api/settings/color-convention` (mirror theme endpoints 224–240, including `ws_bridge.broadcast("color-convention", {...})`). Batch PUT via `/api/settings` works automatically once the spec exists.
3. `web/src/lib/api.ts`: `SettingsResponse.color_convention`, `ColorConventionResponse`/`ColorConventionUpdate`, `setColorConvention()` (mirror 500–512).
4. **WS consumer**: currently NO frontend component subscribes to the `"theme"` topic either — theme sync is pull-on-load + optimistic local apply. For convention, same approach is fine; optionally subscribe in `App.svelte` (`onMessage("color-convention", …)` mirroring the `"alert"` handler at 161–172) so a second terminal tab stays in sync.

### 4.4 Decoupling the three coupled usages (pre-requisite for a clean flip)

| Coupling | Fix |
|---|---|
| CE/PE badges (4 components) | Introduce neutral option-type tokens (`--call`/`--put` or reuse `--info`-family) OR a convention-independent pair (e.g. CE = `var(--accent)`, PE = `var(--muted)`). **Recommendation**: decouple — do not let CE/PE flip with price convention. |
| BUY/SELL badges | Same treatment — categorical side colors, decouple from price tokens (e.g. BUY = `var(--success)`, SELL = `var(--danger)` — international-neutral). |
| SL/TGT level colors | Keep bound to price tokens ONLY if product intent is "follow convention"; otherwise rename to explicit `--sl`/`--tgt` semantic tokens (red SL / green TGT reads as risk/upside in both conventions). **Recommendation**: rename to semantic tokens; fix the inverted `.up`/`.down` class naming while there. |
| FILLED badge | Change `OrderHistory.svelte:51` to `border-success text-success` — fixes the existing DESIGN.md status/price token violation AND removes it from the flip set. |

---

## 5. Migration strategy

1. **Phase 0 (binding)**: amend `DESIGN.md` §1 (line 112) + §2.1 (line 125) + token table (147–164) and `AGENTS.md` line 48 to state: convention is configurable, **international is the default**, Indian is the legacy opt-in. Update `.projectos/identity/frozen-rules.md` if it codifies the convention.
2. **Backward compatibility**:
   - `sx-convention` absent in localStorage → `"international"` (the new requirement default). Existing operators who never chose a convention will see the flipped colors on upgrade — **document this in CHANGELOG** as the intended P5 EXTERNAL behavior change; they can switch back to Indian in one click.
   - No migration of stored values needed — the setting is additive; `SettingsStore` returns the default until first written. No DB schema change (KV store).
   - `:root` fallback (no-JS, pre-init) = international to match the default and avoid a flash of Indian colors before JS applies the attribute.
3. **Sequencing**: DESIGN.md amend → decouple the 4 coupled usages (with their own tests) → token swap block in design.css → `color-convention.ts` → backend settings → UI controls → RiskHeatmap hardcode fix → docs/CHANGELOG.

---

## 6. Testing strategy

### Backend (pytest, existing suites)
- `tests/core/test_settings_store.py`: extend with `test_color_convention_default_is_international`, `test_color_convention_must_be_indian_or_international` (mirror `test_theme_must_be_dark_or_light`, line 73), batch-update snapshot coverage (mirror lines 111–123).
- `tests/terminal/test_settings_router.py`: `GET /api/settings/color-convention` default; `PUT` persists + asserts `ws_bridge.broadcast("color-convention", ...)` (mirror `test_put_theme_persists_and_broadcasts`, 167–178); invalid value → 400 (mirror 180–183); `PUT /api/settings` with `color_convention` field (mirror 73–88).
- Full suite gate: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase5 -p no:cacheprovider`.

### Frontend (vitest + svelte-check)
- New `lib/color-convention.test.ts`: default fallback `international`, round-trip localStorage, `data-convention` attribute application.
- `CandleChart.test.ts` (line 40–56) already asserts `fill="var(--candle-up)"`/`var(--candle-down)` by **token name** — stays green under both conventions; update the test *title/comment* to drop "Indian convention".
- New test: mount with `data-convention="international"` and assert computed up/down token values are swapped (or assert the CSS override block in design.css).
- `SettingsView` control test (mirror existing theme control interactions).
- Gates: `npm run check` (0 errors — mandatory), `npm run test` (vitest run), `npm run build` → committed `src/shettyxtreme/terminal/static/` bundle **must be rebuilt** (it is committed, per AGENTS.md).

### Manual verification
- Boot `run.py --mode OBSERVER`; toggle both conventions × both themes (4 combinations); verify: LTP hero flash/color, watchlist change_pct, chain tick flash, greeks delta, positions P&L, scanner alerts, hints direction badge, ticker regime caret, candles, research direction badges — all flip together; CE/PE, BUY/SELL, SL/TGT, status badges, IV gauge **do not** flip.

---

## 7. Files to touch (implementation checklist)

| File | Change |
|---|---|
| `DESIGN.md`, `AGENTS.md`, `CHANGELOG.md` | Amend convention contract; default = international; changelog entry |
| `web/src/lib/design.css` | Add `data-convention` token blocks (compose with both themes) |
| `web/src/lib/color-convention.ts` | **NEW** — mirror `theme.ts` |
| `web/src/main.ts` | `initColorConvention()` before mount |
| `core/settings.py` | Spec + validator + accessor (`color_convention`) |
| `terminal/api/settings_router.py` | Models + GET/PUT endpoints + WS broadcast |
| `web/src/lib/api.ts` | Types + `setColorConvention` |
| `web/src/components/SettingsView.svelte` | Segmented control (mirror Theme card) |
| `web/src/components/Header.svelte`, `CommandPalette.svelte` | Quick toggle + palette command (optional) |
| `web/src/components/RiskHeatmap.svelte` | Replace hardcoded `rgba(246,82,92)/(46,189,133)` in `sectorBg` with token-driven CSS |
| `web/src/components/OrderHistory.svelte`, `ProposalQueue.svelte` | Decouple FILLED → `--success`; SL/TGT semantic tokens; fix inverted `.up`/`.down` naming |
| `web/src/components/GreeksPanel.svelte`, `PositionsRiskStrip.svelte`, `ProposalQueue.svelte` (CE/PE), `OrderHistory.svelte` (CE/PE + side) | Decouple categorical badges from price tokens |
| Tests | `tests/core/test_settings_store.py`, `tests/terminal/test_settings_router.py`, `web/src/lib/color-convention.test.ts`, `CandleChart.test.ts` title, SettingsView test |

**Risk note**: the token swap is high-blast-radius-by-design (every directional site flips at once) but low-complexity because of the existing token discipline. The only true hazards are the three coupled non-directional usages in §3b — decouple those FIRST, in a separate commit with its own tests, so the flip commit is a pure value swap.
