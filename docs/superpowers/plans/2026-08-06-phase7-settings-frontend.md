# Phase 7 Wave 3 — Settings Frontend (SettingsView) — Implementation Report

**Date:** 2026-08-06
**Status:** Complete
**Backend precondition:** `docs/superpowers/plans/2026-08-05-phase7w3-settings-backend.md` (settings router live, 1241 tests passing)
**Design contract:** `DESIGN.md` (binding — near-black canvas, single amber accent, hairline-only elevation, ≤120ms transitions, mono numerals)

---

## 1. What was changed, per file

### `src/shettyxtreme/terminal/web/src/lib/api.ts` (+78 lines — owned)

Added the missing HTTP verb helper and the typed settings API surface:

- **`putBody<T>(path, body)`** — mirrors the existing `postBody<T>()` (10 s AbortController deadline, `same-origin` credentials, JSON body, error message extracted from `detail`/`message`). There was no PUT helper before; the settings router's three PUT endpoints all need one.
- **Types** — `SettingsScheduler`, `SettingsResponse`, `SettingsUpdate`, `SchedulerUpdate`, `ThemeResponse`, all mirroring the pydantic response models in `settings_router.py` (wire names: `enabled`, `interval_minutes`, `lenses`, `tools`, `running`, `next_run_at`, `last_run_at`, `last_result`).
- **Functions** — `getSettings()`, `updateSettings()`, `setTheme()`, `getScheduler()`, `updateScheduler()`. `Theme` is imported from `./theme` (type-only; no cycle — `theme.ts` imports nothing).
- `getTheme` / `getThemeSetting` deliberately **not** added: the full `GET /api/settings` already carries the theme, so a separate theme GET would be dead code.

### `src/shettyxtreme/terminal/web/src/components/SettingsView.svelte` (184 → 743 lines — owned)

Kept the existing auth/credentials card, then added three cards below it. Structure per card: `Card > CardHeader (CardTitle + one-line desc) > CardContent` with a `<form>` where a Save exists.

**Section 0 — Broker credentials (existing, lightly touched)**
- Wrapped in a `CardHeader`/`CardTitle` ("Broker credentials") so all four cards share one rhythm.
- Removed the global `Enter`-anywhere → Re-auth keydown handler (and the `rootEl` binding): with three independent forms on the page, a global Enter that triggers a network redirect/re-auth would be a footgun. Enter now submits natively within each form.
- `fmtExpiry` renamed to `fmtTs` (shared by the token-expiry row and scheduler status rows).
- Auth error now renders inline inside its card (`role="alert"`).

**Section 1 — Risk limits**
- **Daily loss limit**: number input, `step=500`, `min=0`, `max=10000000`, bound as a raw string. UX decision: the operator types a **positive magnitude** and a fixed `−` adornment sits inside the field (mono, `pointer-events: none`) — the wire value is `-abs(value)`. Hint states the cap in Indian grouping ("max ₹1,00,00,000") and that it is stored negative.
- **Max concurrent positions**: number input, `step=1`, `min=1`, `max=100`.
- **Save** → `PUT /api/settings` `{loss_limit, max_positions}` → on success re-seeds the whole form from the `SettingsResponse` snapshot and fires `toast.success("Risk limits saved — live in the risk engine")`; on failure the extracted 400 `detail` shows inline.

**Section 2 — Theme**
- Segmented control (two `role="radio"` buttons, 4px radius, hairline container, active segment = amber text on `surface-elevated`).
- On change: **optimistic local apply** — `theme` state + `applyTheme(next)` (writes `sx-theme` in localStorage and the `data-theme` attribute immediately) → `PUT /api/settings/theme` `{theme}` → reconcile with the server's response (`theme = r.theme; applyTheme(r.theme)`), which also triggers the backend's WS `theme` broadcast for other clients. On failure: revert state + `applyTheme(prev)` and show the error inline.

**Section 3 — Research scheduler**
- **Enabled toggle**: custom `<button role="switch">` built inline (no Switch primitive exists in the shadcn inventory) to the exact DESIGN §4 spec — off: `hairline-strong` track + `muted` knob; on: `accent` track + white knob; 100 ms transforms; 2px `focus-ring` on `:focus-visible`.
- **Interval (minutes)**: number input, `step=5`, `min=1`, `max=1440`. **Lenses / Tools**: comma-separated text inputs (parsed on save; empty → `[]`, which the store normalizes to `null`).
- Fields are `disabled`-free but visually gated — the interval/lens/tool fields only render while the toggle is on; values are preserved so re-enabling restores them.
- **Live status block** (below a hairline divider, from `GET /api/settings/scheduler`): a status chip — `RUNNING` (success) / `NOT RUNNING` (warning, enabled-but-idle) / `DISABLED` (secondary) — plus mono `Next run` / `Last run` timestamps and `Last result` (wrapping mono, right-aligned). Polled every 15 s while the view is mounted (timer cleared on destroy).
- **Honest notice**: when `enabled && !running`, an alert-bar-styled warning (status token at 10% on the card) reads: "Enabled but not running — set `DEEPSEEK_API_KEY` on the terminal process to activate." The save toast is equally honest: "Scheduler saved — not running (DEEPSEEK_API_KEY not set)".
- **Save** → `PUT /api/settings/scheduler` `{enabled, interval_minutes, lenses, tools}` → re-seeds from the `SchedulerResponse` and updates the status block.

**Loading/error shell**: before `GET /api/settings` resolves, "Loading settings…" shows; on failure an inline `role="alert"` error replaces the three sections. The auth card renders independently.

## 2. API calls made

| Call | Method | When | Notes |
|---|---|---|---|
| `/api/settings` | GET | on mount (`loadAll`) | one call seeds the entire form |
| `/api/settings` | PUT | Risk "Save risk limits" | `{loss_limit: -abs, max_positions}`; full snapshot returned |
| `/api/settings/theme` | PUT | theme segment click | `{theme}`; persisted + WS broadcast server-side |
| `/api/settings/scheduler` | GET | on mount + every 15 s | live status only (never clobbers in-progress edits) |
| `/api/settings/scheduler` | PUT | "Save scheduler" | `{enabled, interval_minutes, lenses, tools}` |
| `/auth/status` | GET | on mount | pre-existing auth card |

## 3. Form validation approach

Two layers, both surfaced inline per card (no blocking modal, `role="alert"` on error text):

1. **Client-side preflight** (`validateRisk`, `validateScheduler`) mirroring the backend `_SPECS` spec — loss limit finite/≥0/≤10 M; max positions integer 1–100; interval finite/>0/≤1440. Empty required field → field-specific message. Failing preflight never touches the network.
2. **Server-side 400s** — `describeError` extracts the pydantic `detail` string (e.g. "loss_limit magnitude too large (max 10,000,000)") and it renders inline in the originating card. The backend validates all-or-nothing, so a rejected batch leaves the store untouched and the form re-editable.

## 4. Design-contract compliance

- Tokens only via CSS vars / shadcn alias layer — no hard-coded hex except the DESIGN-mandated white toggle knob.
- No drop shadows, gradients, or glassmorphism anywhere (flat color-block elevation; hairline borders).
- Transitions are 100 ms (≤ 120 ms rule).
- Every numeral (limits, interval, timestamps, status values) in `.mono` (JetBrains Mono + tabular figures); labels in Inter; 11–13 px type; 28 px row rhythm preserved from the auth card.
- Single amber accent reserved for selected controls (theme segment, toggle-on, focus rings, links).
- Custom interactive controls have visible 2px focus rings on `:focus-visible`; the toggle has `aria-checked`/`aria-label`, segments have `role="radio"` + `aria-checked`.

## 5. Verification results

- `npm run check` (svelte-check) in `src/shettyxtreme/terminal/web/` → **0 errors, 0 warnings** (a transient unused-selector warning on `.prefix-input` was eliminated by switching to the Tailwind `pl-6` utility — `pl` sorts after `px` in the generated stylesheet, so it overrides the primitive's `px-2.5`).
- `npm run build` → **succeeded** (Vite 6.4.3, 4634 modules, bundle written to `src/shettyxtreme/terminal/static/` per AGENTS.md committed-bundle rule).
- `SettingsView.svelte` = **743 lines** (limit 1000 — no split needed); `api.ts` = 455 lines.
- Git diff scoped to the two owned source files (+682/−43 net across both) plus the regenerated static bundle; no backend/Python files touched.

## 6. Notes / follow-ups

- The old "Enter anywhere → Re-auth" behavior is gone by design (multi-form page); the primary re-auth path is the button.
- The scheduler status poll (15 s) is deliberately read-only — it never overwrites an operator's in-progress form edits.
- Other tabs receiving the WS `theme` broadcast is handled server-side; this view applies the change locally via `applyTheme`, consistent with the Header's behavior.
