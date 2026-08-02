# Terminal Remediation — Design Spec

**Date:** 2026-08-02 · **Status:** Approved (user) · **Owner:** ShettyXtreme platform
**Scope:** P1 credential onboarding UI, P2 Tier-1 quick fixes, P3 hygiene, P5 UI redesign (shadcn-svelte + dual theme + tab consolidation), P4 pipeline rewiring, P6 layman manual.
**Binding contracts:** DESIGN.md (must be amended in P5 step 0 BEFORE code), ARCHITECTURE_V2.md (D1–D12), AGENTS.md.

---

## 1. Background — audit findings this plan fixes

Four-agent audit (2026-08-02) found three tiers of issues:

- **Tier 1 (user-visible):** `#/setup` and `#/settings` are text-only stubs while AGENTS.md/CHANGELOG claim a working wizard; research brief Approve/Reject 404s (`/approved` vs backend `/approve`); positions strip AVG column hardcoded `—`; watchlist selection consumed by nothing.
- **Tier 2 (silent):** SignalEngine/FeatureEngine/voters never instantiated → regime/signal/voters serve defaults; PAPER/LIVE modes are shells; ExecutionEngine has zero runtime callers; learning/shadow DBs never populated; `options_posture` always `[UNSOURCED]`; `intelligence/options` returns silent empty 200.
- **Tier 3 (hygiene):** duplicate `/api/settings/*` twins of `/auth/*`; `GET /api/settings` placeholder; vestigial WS subscription API; stale ARCHITECTURE_V2 phase map + roadmap rows; loose `dhanhq>=0.1.0` pin; dual-credential stale docstrings.

**Verified good:** all handoff claims (3A/3B/3C/4, v0.11.0) match code; all 29 consumed endpoints + 8 WS topics exist; bundle current; DhanPy request codes already fixed (15/17/21 outbound, 2/4/8 inbound parse).

---

## 2. Non-negotiable gates (every step)

1. `npm run check` → 0 errors; `npm run build` → **committed** bundle in `terminal/static/`.
2. Full pytest suite green (`732 passed` baseline; `PYTHONPATH=""` + `--basetemp` form per AGENTS.md).
3. No `openalgo` imports; no file > 500 lines; `core/` no external imports.
4. Contracts frozen: 29 endpoints + 8 WS topics keep exact paths/shapes; vite proxy unchanged.
5. Indian price convention law: red `#f6525c` = up, green `#2ebd85` = down — in **both** themes. Never "fixed".
6. DESIGN.md amended **before** code that contradicts it (contract's own rule).
7. D10: OBSERVER default; LIVE needs typed confirmation; kill switch never hidden.
8. Credentials stay Fernet-encrypted; no secrets in logs.

---

## 3. P1 — Credential onboarding UI (build first)

### 3.1 Backend — 3 new endpoints in `auth_router.py` (wrap existing helpers, no new auth logic)

| Endpoint | Body | Behavior |
|---|---|---|
| `POST /auth/token` | `{access_token}` | Decode JWT via `CredentialStore._extract_client_id_from_token`, extract `exp` for expiry; `store.update_token(token, expiry, client_id)`; save. 400 on undecodable token. |
| `POST /auth/token/pin-totp` | `{client_id, pin, totp}` | Call existing `DhanOAuthHelper.generate_access_token()` (currently unexposed, dhan_oauth.py:120); on ok → `update_token`; map 401/400 to clear messages (already in helper). |
| `POST /auth/data-token` | `{access_token, expiry?}` | `store.update_data_token()` (credential_store.py:110); save. |

Extend `CredentialStatusResponse` with `data_token_valid: bool = False` and `data_token_expiry: str | None`. `/auth/status` computes it via store expiry check.

Update `tests/wave7/test_auth_router.py` with coverage for all three + status extension.

### 3.2 Frontend

- **`components/SetupWizard.svelte`** (new, replaces App.svelte:79-92 stub):
  - On mount `GET /auth/status` → three states: not-set-up (show form) / token-expired (warn + re-auth) / connected (banner + return link).
  - Tabs (per DESIGN.md tab spec): **App credentials** (`client_id`, `api_key`, `api_secret` — frontend joins `client_id:::api_key`; Test → `POST /auth/test`; primary Connect → `POST /auth/start-consent` → same-tab redirect to `login_url`) · **Direct token** (paste field → `POST /auth/token` → shows extracted client_id + expiry) · **PIN + TOTP** (`client_id`, `pin`, `totp` → `POST /auth/token/pin-totp`).
  - Optional advanced section: **Data token** (paste → `POST /auth/data-token`), only needed for 806/separate-entitlement case.
  - Preserve the existing `?connected=true` / `?error=…` banner contract (moved into component).
- **`components/SettingsView.svelte`** (new, replaces App.svelte:73-78 stub): status card (client name, masked key from `GET /api/settings/credentials`, both token rows w/ validity + expiry in mono timestamps), **Re-auth** (`POST /api/settings/reauth` → redirect), **Logout** (`POST /auth/logout`).
- **`Header.svelte`**: credential chip → connected (success dot + CONNECTED → `#/settings`) / expired (warning REAUTH → `#/settings`) / none (muted SETUP → `#/setup`). Reuses existing health fetch pattern.
- **`App.svelte`**: routes render components; fix `/api/auth` → `/auth` text.
- **`lib/api.ts`**: typed wrappers — `AuthStatus`, `authStatus()`, `saveCredentials()`, `testCredentials()`, `startConsent()`, `saveDirectToken()`, `savePinTotp()`, `saveDataToken()`, `reauth()`, `logout()`.

### 3.3 DhanPy auth coverage (brief §2)

Wizard exposes all three DhanPy flows: consent (`generate_login_session`/`consume_token_id`), PIN+TOTP (`generate_token`), direct token (any existing accessToken, incl. `RenewToken` output). One token serves trading REST + data WS (SDK fact).

---

## 4. P2 — Tier-1 quick fixes

1. ResearchPanel.svelte:115: `/approved`|`/rejected` → `/approve`|`/reject` (backend research_router.py:221,227).
2. PositionsRiskStrip: add `buy_avg` to `Position` type (backend returns it), render mono right-aligned, `—` fallback.
3. Watchlist → chain: new `lib/selection.ts` Svelte `writable` store; Watchlist click writes `selectedSymbol`; ChainGrid subscribes → sets `symbol` + `load()`.

---

## 5. P3 — Hygiene

1. **Retire twins:** delete `/api/settings/{reauth,test,credentials}` + placeholder `GET /api/settings`; keep `POST /api/settings/postback-url`. Canonical surface = `/auth/*`. Update tests referencing deleted endpoints.
2. **WS subscriptions:** implement per-client topic subscriptions in `ws_manager.py` (subscribe/unsubscribe messages from client; `broadcast` filters by `_topics`); update `ws.ts` to send subscribe on connect; keep ping.
3. **Stale docs:** ARCHITECTURE_V2 phase map, `17-delivery-roadmap.md` rows (net-EV deferred, Phase-1 CURRENT header), `data_adapter.py` dual-credential docstrings (→ single-token + optional data fallback).

---

## 6. P5 — UI redesign (shadcn-svelte, dual theme, tab consolidation)

### 6.0 DESIGN.md amendment (BEFORE any code)

- **Palette:** warm near-black canvas `#0d0c0a` (dark) / warm paper `#f7f5f1` (light); single accent amber `#f5b942` (dark) with dark-on-amber text; light-theme accent adjusted for contrast. Price tokens unchanged hues: up `#f6525c`, down `#2ebd85`; light theme may darken the green shade for WCAG AA (hue stays green).
- **Themes contract:** dual-theme replaces "never a light mode" rule. Dark = default + operator norm; light = opt-in, both must pass contrast, price convention law in both.
- **Layout:** tab consolidation (scanner/hints/analytics behind chain zone) becomes the standard cockpit; panel taxonomy otherwise unchanged.
- **Component contract:** shadcn-style primitives (Button, Input, Tabs, Dialog, Tooltip, Toast, Badge, Table) with documented default/hover/active/disabled/focus-ring states; drop-shadow ban re-affirmed (fixes existing LogDrawer violation).

### 6.1 Stack

`npx shadcn init` (Svelte 5 + Tailwind v4 + `@tailwindcss/vite`). Deps: `tailwindcss`, `@tailwindcss/vite`, `bits-ui`, `lucide-svelte`, `clsx`, `tailwind-merge`, `class-variance-authority`. Fallback if CLI fights Svelte 5: hand-port shadcn components (copy-paste model) on Tailwind v4.

### 6.2 Migration

- `design.css` → token blocks per theme (`:root[data-theme="dark"]` / `[data-theme="light"]`); fix 5 hardcoded colors (KillSwitch `#fff`, pulse rgba, ModeSwitcher `#fff`, LogDrawer box-shadow → elevation).
- Migrate all 14 components to `$lib/components/ui/*` primitives — **preserving every data binding, endpoint call, and WS subscription** (contract-frozen list in audit).
- Theme toggle: header right side, `localStorage`, default dark.

### 6.3 Verification

All 29 endpoints + 8 WS topics render correctly in both themes; `npm run check` + build + committed bundle; pytest unaffected (frontend-only).

---

## 7. P4 — Pipeline rewiring

- **P4a Intelligence:** instantiate `SignalEngine` + register 4 live voters (`intelligence/voters/__init__.py`) + `FeatureEngine` in lifespan → `SIGNAL_V2`/`FEATURES_COMPUTED` → regime bridge (already started) alive; `/api/intelligence/{regime,signal,voters}` + WS topics real; `intelligence/options` silent empty 200 → surfaced 503.
- **P4b Execution:** PAPER → `PaperTradingEngine`; OBSERVER proposal queue (signals/hints → proposals) → human approve/reject → risk check → `OrderValidator` → `DhanTradingAdapter.place_order`; new `/api/execution/*` endpoints; proposal panel + DESIGN.md order-confirm modal (built on shadcn components post-P5). LIVE keeps typed gate (D10).
- **P4c Learning:** outcome recording (decisions → fills → outcome), shadow voter registration + graduation cadence → `learning.db`/`shadow.db` populated; `options_posture` renderer in `research_source.py`; `data/learning.db` + `shadow.db` now created.
- **P4d DhanPy hardening:** pin `dhanhq>=2.2.0,<2.3.0` (pyproject.toml:14); disconnect-code-aware reconnect in `data_adapter.py` (806 stop / 807 renew / 805 backoff+jitter); `SessionHealth.refresh()` mints fresh token via `renew_token`/`generate_token` before rebuilding `DhanContext`; fix stale 41/51 feed-code comment if still present.

---

## 8. P6 — Layman manual

`docs/OPERATOR_MANUAL.md`: plain-language panel-by-panel guide (what each panel shows, in one paragraph), the three auth methods ("connect your Dhan account — 3 ways"), OBSERVER/PAPER/LIVE in simple words, kill switch, error 806 in plain words, first-run checklist. Written AFTER P5/P4 so it documents final state.

---

## 9. Execution order & handoff

P1 → P2 → P3 → P5 → P4 → P6. Each phase: spec self-review + user checkpoint via handoff docs in `docs/superpowers/handoffs/`. Tests added per phase in closest existing wave/module dir.
