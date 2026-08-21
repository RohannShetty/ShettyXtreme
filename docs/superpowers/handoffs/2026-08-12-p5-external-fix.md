# P5 EXTERNAL — Color Convention Toggle: Completion Handoff

**Date:** 2026-08-12 · **Status:** Complete · **Tests:** 1626 passed / 0 failed / 1 skipped (backend) + 28 passed / 0 failed (frontend)

## Summary

Price color convention is now configurable via `data-convention` on `<html>`:
- **International (default):** green=up, red=down
- **Indian (legacy opt-in):** red=up, green=down

The toggle persists via `sx-convention` localStorage + backend `SettingsStore` + `GET/PUT /api/settings/color-convention` with WS broadcast. All 16 directional token sites flip together; non-directional usages (CE/PE, BUY/SELL, SL/TGT, status badges) are decoupled.

## Files Modified

### Docs
- `DESIGN.md` — Amended §1, §2.1, §2.2, §2.3: convention is configurable, international is default
- `AGENTS.md` — Updated line 48: configurable convention reference
- `CHANGELOG.md` — Added v0.15.0 entry documenting the behavior change

### CSS Tokens (design.css + app.css)
- `web/src/lib/design.css` — Restructured: `:root` defaults to international (green=up), `:root[data-convention="indian"]` overrides to Indian (red=up). Added `--option-call`, `--option-put`, `--side-buy`, `--side-sell`, `--sl-level`, `--tgt-level` neutral tokens. Both compose with `data-theme` dark/light.
- `web/src/lib/app.css` — Added Tailwind aliases for new neutral tokens

### Frontend Infrastructure
- `web/src/lib/color-convention.ts` — **NEW** — mirrors `theme.ts`: `ColorConvention` type, localStorage key `sx-convention`, `getColorConvention()`, `applyColorConvention()`, `initColorConvention()`
- `web/src/main.ts` — Calls `initColorConvention()` before mount

### Backend
- `core/settings.py` — Added `DEFAULT_COLOR_CONVENTION`, `VALID_COLOR_CONVENTIONS`, `_validate_color_convention`, `_SPECS["color_convention"]`, `SettingsStore.color_convention()` accessor
- `terminal/api/settings_router.py` — Added `color_convention: str | None` to `SettingsUpdate`/`SettingsResponse`, `ColorConventionResponse`/`ColorConventionUpdate` models, `GET/PUT /api/settings/color-convention` endpoints with WS broadcast

### Frontend API
- `web/src/lib/api.ts` — Added `ColorConvention` import, `color_convention` to `SettingsResponse`/`SettingsUpdate`, `ColorConventionResponse` type, `setColorConvention()` function

### UI Controls
- `web/src/components/SettingsView.svelte` — Added "Price colors" card with segmented control (Indian / International), mirroring Theme card pattern

### Decoupled Non-Directional Usages
- `web/src/components/OrderHistory.svelte` — CE/PE→`--option-call`/`--option-put`, BUY/SELL→`--side-buy`/`--side-sell`, SL/TGT→`--sl-level`/`--tgt-level`, FILLED→`--success` (fixes DESIGN.md violation)
- `web/src/components/ProposalQueue.svelte` — Same decoupling: CE/PE, BUY/SELL, SL/TGT, EV/P&L use semantic class names instead of `.up`/`.down`
- `web/src/components/GreeksPanel.svelte` — CE/PE→`--option-call`/`--option-put`
- `web/src/components/PositionsRiskStrip.svelte` — CE/PE→`--option-call`/`--option-put`
- `web/src/components/RiskHeatmap.svelte` — Replaced hardcoded `rgba(246,82,92)`/`rgba(46,189,133)` in `sectorBg()` with computed `--price-up`/`--price-down` token reads

### Comment Updates
- `web/src/components/Header.svelte` — Updated price convention comment
- `web/src/components/ChainGrid.svelte` — Updated price law comment
- `web/src/components/TickerStrip.svelte` — Updated regime caret comment + CSS comment

### Static Bundle (committed)
- `src/shettyxtreme/terminal/static/assets/index-lwfCvaXz.js` — NEW bundle
- `src/shettyxtreme/terminal/static/assets/index-hqPi1mK8.css` — NEW bundle
- `src/shettyxtreme/terminal/static/assets/index-CkQ5uwKI.js` — DELETED (old)
- `src/shettyxtreme/terminal/static/assets/index-DjuKOoPX.css` — DELETED (old)
- `src/shettyxtreme/terminal/static/index.html` — Updated asset references

## Tests Added

### Backend (pytest)
- `tests/core/test_settings_store.py`:
  - `test_color_convention_default_is_international` — verifies default is "international"
  - `test_color_convention_must_be_indian_or_international` — verifies validation rejects unknowns, accepts valid values
- `tests/terminal/test_settings_router.py`:
  - `TestColorConvention.test_get_color_convention` — GET default
  - `TestColorConvention.test_put_color_convention_persists_and_broadcasts` — PUT persists + WS broadcast
  - `TestColorConvention.test_put_color_convention_invalid_400` — invalid value → 400

### Frontend (vitest)
- `web/src/lib/color-convention.test.ts` — **NEW**:
  - Default fallback `international`
  - localStorage round-trip
  - `data-convention` attribute application
  - `initColorConvention()` behavior
- `web/src/components/CandleChart.test.ts` — Updated test title to drop "Indian convention"

## Verification Output

```
Backend: 1626 passed, 1 skipped, 0 failed (95.01s)
Frontend: 28 passed, 0 failed (8 test files, 53.43s)
svelte-check: 0 errors, 2 warnings (pre-existing)
npm run build: ✓ built in 19.29s
```

## Edge Cases / Follow-ups

1. **Visual upgrade break**: Existing operators who never chose a convention will see flipped colors on upgrade (green=up instead of red=up). This is documented in CHANGELOG as the intended behavior; they can switch back in one click via Settings → Price colors.
2. **No-JS fallback**: `:root` without `data-convention` renders international (green=up). Pre-first-paint is handled by `initColorConvention()` in `main.ts` before mount.
3. **RiskHeatmap `sectorBg`**: Now reads computed `--price-up`/`--price-down` CSS values via `getComputedStyle()`. This is slightly more expensive than the previous hardcoded hex, but only runs on render — no performance concern.
4. **Header toggle / CommandPalette**: Not included in this implementation (optional per findings). Can be added as a follow-up using the same `applyColorConvention()` + `setColorConvention()` pattern.
