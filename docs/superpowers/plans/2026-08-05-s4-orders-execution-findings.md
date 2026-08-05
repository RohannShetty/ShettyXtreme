# S4 Findings — Phase 3 Cockpit Redesign: Orders + Execution UI Polish

**Date:** 2026-08-05
**Scope:** S4 of Phase 3 — `ProposalQueue.svelte` (execution approvals) + `ModeSwitcher.svelte` (mode control in the header strip)
**Status:** Complete — both verification gates pass (`npm run check` 0 errors, `npm run build` success)

---

## Deliverables

| File | Change |
|---|---|
| `src/shettyxtreme/terminal/web/src/components/ProposalQueue.svelte` | STALE chips (>30s), per-mode mode chip (OBSERVER=faint / PAPER=info / LIVE=accent pulsing), OBSERVER proposals-only notice + APPROVE disabled in OBSERVER, risk summary block (margin used/available, loss-limit-hit alert, Indian grouping, mono numerals), keyboard flow (row Enter/Space → confirm dialog, Enter approves, Esc closes), LIVE-confirm description + danger Confirm button |
| `src/shettyxtreme/terminal/web/src/components/ModeSwitcher.svelte` | Mode indicator (dot + label per DESIGN §4), typed "LIVE" confirm dialog (D10, matches KillSwitch pattern), LIVE session banner (full-width, 36px, fixed below header), Ctrl+M cycle with LIVE confirmation |

## Verification

- `npm run check` → **svelte-check: 0 errors, 2 warnings** (warnings are pre-existing a11y hints in ChainGrid.svelte / Watchlist.svelte — outside S4 scope, non-blocking).
- `npm run build` → **vite production build succeeds** (`✓ built in 44.77s`); `terminal/static/` bundle regenerated as a gate artifact, **not committed** per mission.

---

## 1. ProposalQueue.svelte

### 1.1 OBSERVER prominence (proposals-only workflow)

- In OBSERVER mode a full-width info notice renders under the panel head: *"OBSERVER — proposals only. Nothing is placed automatically; switch to PAPER or LIVE to execute."* (`color-mix` of `--info` 10% on `--surface-card`, `--info` text).
- **APPROVE is disabled in OBSERVER with a tooltip** explaining why. Verified against the backend contract (`execution_router.py:311-316`): `approve_proposal` returns 400 *"OBSERVER mode never places orders"*. Pre-empting with a disabled state avoids a guaranteed-failed call and a confusing error toast. REJECT stays enabled (backend allows rejection in any mode).
- Queue keeps its 5s poll of PENDING proposals; risk summary refreshes in the same cycle.

### 1.2 LIVE typed-confirm flow — verified working

The mission's "typed-confirm dialog for APPROVE (already exists, verify it works)" was verified end-to-end against `execution_router.py:296-335`:

- Arming LIVE requires `{"confirm": "LIVE"}` in the request body (F-EXEC-001, `set_mode` at `:211-217`) — the operator must **type LIVE** at mode switch; this mints the per-session CSRF token (`_mint_csrf_token`).
- `approveProposal(id, confirm=true, csrfToken)` sends `X-CSRF-Token` + `?confirm=true` only in LIVE mode — exactly what the backend requires (`_require_csrf_token(request)` + `confirm` at `:317-323`). **The existing approve path works and is contract-correct.**
- Polish added on top: the confirm dialog description is mode-aware (LIVE → *"places a REAL order… executes on confirmation"* with a danger-highlighted phrase; PAPER → *"routes to the PAPER engine"*), and the Confirm button switches to `variant="danger"` when LIVE.

### 1.3 STALE chip (>30s, warning)

- `STALE_MS = 30_000` matches the backend staleness threshold (`STALENESS_THRESHOLD_SEC = 30.0`). A 1s `now` tick re-renders chips live.
- Rows older than 30s get a `{colors.warning}` **STALE** badge in the badge cluster (DESIGN §4 table alignment rule: *staleness marker = warning micro "STALE" chip*) and the timestamp cell swaps to a warning `45s` age readout.
- Honest behavior: the backend expires stale PENDINGs on the next `list_proposals` call, so the chip is a visibility window before the proposal drops out — not a lie, just ahead of the server.

### 1.4 Mode chip

`chip-observer` (faint text/border) · `chip-paper` (info) · `chip-live` (accent, with a 1s pulsing dot). All tokens from `design.css` variables.

### 1.5 Risk summary block (confirm dialog)

Mono `tabular-nums`, all values via `fmtMoney` with `toLocaleString("en-IN")` (lakh/crore Indian grouping, DESIGN §7). Rows: DAILY P&L (red up / green down per Indian law), **MARGIN USED** (added), MARGIN AVAIL (`—` when null — never a fabricated ₹0), LOSS LIMIT, ACTIVE POS `n/max`. When `loss_limit_hit` is true a danger alert strip renders: *"LOSS LIMIT HIT — daily P&L is below the configured loss limit."*

### 1.6 Keyboard

- **Row level:** `tabindex=0` + `role="button"` + 2px `focus-ring` outline; Enter/Space on the focused row opens its confirm dialog (`e.target === e.currentTarget` guard so button-activation Enter isn't double-caught).
- **Dialog level:** a window `keydown` listener approves on Enter when the dialog is open (with `preventDefault` so a focused Confirm button doesn't double-fire; `busy`-guarded). Esc closes via the bits-ui dialog primitive's default `onOpenChange(false)`.

## 2. ModeSwitcher.svelte

### 2.1 Typed LIVE confirmation dialog (DESIGN §4 modal contract, D10)

- Mirrors the KillSwitch disarm pattern exactly: plain `<input>` (mono, uppercase) where the operator **types `LIVE`**; the **Arm LIVE** button (`variant="danger"`) stays disabled until the typed text matches. Enter in the input confirms.
- Prominence: danger callout block (danger at 10% on `surface-card`, 1px danger border), danger-highlighted description phrase, autofocus on open (`$effect` + `tick()` + 50ms settle so bits-ui's own focus trap doesn't win).
- Backend contract unchanged and correct: `postBody("/api/execution/mode?mode=LIVE", { confirm: "LIVE" })` — the query flag is never used (F-EXEC-001).

### 2.2 Mode indicator (header)

Dot + label readout left of the segmented buttons: OBSERVER = `--faint` dot, PAPER = `--info` dot, LIVE = `--accent` dot pulsing 1s (`mode-pulse`). Replaces the old static "MODE" text label. `prefers-reduced-motion` kills the pulses. The LIVE button also keeps its inline dot when live.

### 2.3 LIVE session banner

- Full-width, 36px, `position: fixed` at the **measured bottom edge of the header** (`document.querySelector(".head").getBoundingClientRect().bottom`, fallback 52px; re-measured on mount + resize), so it sits flush under the header across viewport widths and survives the S1 compaction cascade.
- DESIGN §4 alert bar contract: `color-mix(in srgb, var(--danger) 10%, var(--surface-card))` bg, `hairline-strong` border-bottom, leading danger dot (pulsing), body text, **no dismiss** (danger). `z-index: 25` — below the right-dock overlay drawer (30) and dialog scrim (40).
- `role="alert"`; `pointer-events: none` so the strip never blocks interaction with the panels it overlays.
- Escape from the header's `overflow: hidden` works because `.head` has no transform/filter/containing-block — verified in the compiled output.

### 2.4 Ctrl+M mode cycle

`Ctrl+M` (guarded: not while typing in an input/textarea/contenteditable, not while the confirm dialog is open; `preventDefault` to suppress any browser default) cycles OBSERVER → PAPER → LIVE → OBSERVER. Landing on LIVE routes through the typed-confirm dialog; leaving LIVE is a direct switch (safe direction). No conflict with existing Ctrl+R (App.svelte) or Ctrl+Shift+K (KillSwitch).

## 3. Design-contract compliance

- All colors via `design.css` variables; no new hex, no shadows, no gradients (the `color-mix` 10% tints are the documented alert-bar treatment, matching Header's existing pip/cred chips).
- Numerals in JetBrains Mono + `tabular-nums`; all money via `en-IN` grouping. **Indian price law untouched** — red up `#f6525c`, green down `#2ebd85` (P&L and side badges use `--price-up`/`--price-down`; status/stale use `--warning`/`--danger`/`--info`; no status token ever colors a price, no price token ever colors a status).
- Modal contract: the bits-ui dialog primitive supplies `surface-overlay` bg + `hairline-strong` border + `scrim` overlay + focus ring.

## 4. Technical notes / findings for later phases

1. **LIVE banner overlaps the workspace's top ~28px.** `App.svelte`'s grid has no banner row (`grid-template-rows: auto minmax(0,1fr) auto`); ModeSwitcher can only render the banner fixed below the header within its own scope, so the 36px bar sits over the top edge of the panels plus the 8px grid gap. `pointer-events: none` keeps everything clickable, and the visual prominence is arguably desirable for a LIVE session — but the clean fix is a 4th grid row for the banner, owned by whoever next touches App.svelte.
2. **Header measurement is selector-coupled.** The banner measures `.head` at runtime. Robust (44px header + 8px grid padding is constant, fallback 52px), but if the header class or grid padding ever changes, the measure keeps it honest; a CSS variable (`--header-bottom`) set on `:root` would be the cleaner long-term contract.
3. **OBSERVER APPROVE is intentionally disabled** because the backend rejects approvals in OBSERVER (400). If a future feature allows OBSERVER "paper-simulate" approvals, re-enable via `canApprove` and the backend route together.
4. **Parallel-lane WIP touched the same working tree mid-session.** While running the check gate, ChainGrid.svelte and KnowledgePanel.svelte were actively edited by sibling lanes (their `tabindex="0"`/`bind:this` type errors appeared then disappeared during my verification runs). S4 files were left untouched by others; the final `npm run check` is green. Recommend lanes coordinate commits to avoid the 3-error window seen mid-session.
5. The static bundle (`terminal/static/`) was regenerated by the mandatory build gate. **Not committed** per instructions.

## Files touched

- `src/shettyxtreme/terminal/web/src/components/ProposalQueue.svelte` (owned)
- `src/shettyxtreme/terminal/web/src/components/ModeSwitcher.svelte` (owned)
- `src/shettyxtreme/terminal/static/*` — regenerated build output (gate artifact, not a source change)

No other files were modified. DESIGN.md / design.css token changes in the working tree predate this task (prior session).
