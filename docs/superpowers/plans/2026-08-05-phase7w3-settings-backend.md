# Phase 7 Wave 3 — Settings Backend (#1) — Findings

**Date:** 2026-08-06
**Status:** Complete — backend for the settings form
**Baseline:** Phase 7 Wave 2 complete — 1197 passed · this wave: **1241 passed / 0 failed / 0 skipped** (+44 regression tests)
**Predecessor recon:** `docs/superpowers/plans/2026-08-05-phase7-recon.md` §1.1

---

## 1. Storage strategy — decision: **Option A (SQLite KV), built on the existing `KVStore`**

| Option | Verdict | Why |
|---|---|---|
| **A — SQLite KV** | **CHOSEN** | stdlib-only → no new `core/` layering violation (the `yaml` import in `config_manager.py:11` is a known violation we must not extend); the repo already persists everything in `data/*.db`; runtime-mutable settings map naturally to a KV store. |
| B — YAML config file | Rejected | would require `yaml` in `core/` (or a `core/`→external dependency), extending the known violation. |
| C — env + config file hybrid | Rejected as primary | env is now only the *first-boot seed* for the scheduler (see §4); the store is authoritative afterwards. |

`core/settings.py` wraps the generic `core/storage/kv_store.py` (`SettingsStore` → per-operation `KVStore` connections, so it is thread-safe by construction — a naive persistent connection breaks under the Starlette TestClient portal thread, caught in CI-run and fixed).

## 2. Settings schema (validated on every write; failed batch leaves the store untouched)

| Key | Type | Default | Validation |
|---|---|---|---|
| `loss_limit` | float | `-5000.0` | finite, `<= 0`, magnitude ≤ 10M |
| `max_positions` | int | `5` | integer, 1–100 |
| `theme` | str | `"dark"` | `dark` \| `light` |
| `scheduler_enabled` | bool | `False` | bool |
| `scheduler_interval_minutes` | float | `60.0` | finite, `> 0`, ≤ 1440 (24 h) |
| `scheduler_lenses` / `scheduler_tools` | `list[str] \| None` | `None` | list of non-empty strings (or CSV string) |

## 3. API surface (`/api/settings`, `settings_router.py`)

| Endpoint | Behavior |
|---|---|
| `GET /api/settings` | all settings + scheduler summary |
| `PUT /api/settings` | update `loss_limit` / `max_positions` / `theme`; invalid → **400**, store untouched; publishes `config.changed` and (on risk-cap change) a `risk.decision` so `RiskProjection` / `/api/execution/risk` refresh immediately |
| `GET /api/settings/theme` | current theme |
| `PUT /api/settings/theme` | set theme, **broadcast** `{"theme": ...}` to connected WS clients (topic `theme`) |
| `GET /api/settings/scheduler` | stored config + live `running` / `next_run_at` / `last_run_at` / `last_result` |
| `PUT /api/settings/scheduler` | persist config and **apply to the live scheduler**: restart loop on interval change, stop on disable, start on enable (requires `DEEPSEEK_API_KEY`; honest `running=false` otherwise) |

## 4. Hardcoded settings eliminated (the 4 recon locations)

| Location (was) | Now |
|---|---|
| `risk_engine.py:75` `LossLimitFilter(loss_limit=-5000.0)` | settings-backed: `loss_limit=None` (default) resolves from the store **and re-reads on every `check`** — a runtime form change is honored by the live engine without restart; an explicit value pins the filter |
| `risk_engine.py:112` `MaxPositionFilter(max_positions=5)` | same settings-backed pattern |
| `bus_bridge.py:10-11` `_DEFAULT_LOSS_LIMIT` / `_MAX_POSITIONS` | **deleted**; `RISK_DECISION` payloads read `loss_limit` / `max_positions` live from the store each publish (prevents the bridge from regressing a form-updated projection to a stale cap) |
| `projections.py:157-159` `RiskProjection` initial `-5000.0` / `5` | initial state seeded from the store |
| `execution_router.py:198,207` fallback `-5000.0` / `5` | fall back to the store |

All four sites read the **same singleton** (`core.settings.get_settings_store()`), initialized by the app lifespan at `data/settings.db` before projections are built.

## 5. Scheduler: env-gating preserved, store now authoritative after first touch

- Lifespan `seed_if_absent(...)` writes the effective env config (`RESEARCH_SCHEDULE_ENABLED`, `INTERVAL_MINUTES`, `LENSES`, `TOOLS`) only for keys never written → **fresh installs behave exactly as before**.
- Once the operator changes anything via `PUT /api/settings/scheduler`, the store wins across restarts (the form is the source of truth).
- The live scheduler handle is wired to the settings router (`init_settings`) and kept in sync with `research_router` via the existing `init_research`.

## 6. Files changed / added (ownership scope only)

**Source**
- `src/shettyxtreme/core/settings.py` — **new**: `SettingsStore` + validators + singleton (`init_settings_store` / `get_settings_store` / `reset_settings_store`)
- `src/shettyxtreme/terminal/api/settings_router.py` — full router (was a 12-line stub)
- `src/shettyxtreme/intelligence/risk/risk_engine.py` — settings-backed `LossLimitFilter` / `MaxPositionFilter`
- `src/shettyxtreme/intelligence/risk/bus_bridge.py` — live caps from the store; dead constants removed
- `src/shettyxtreme/terminal/projections.py` — `RiskProjection` seeds from the store
- `src/shettyxtreme/terminal/api/execution_router.py` — risk fallbacks read the store
- `src/shettyxtreme/terminal/api/app.py` — settings-store init + scheduler block rework + `init_settings` wiring

**Tests (new, +44)**
- `tests/core/test_settings_store.py` — defaults, validation, all-or-nothing batches, persistence, seeding, singleton lifecycle
- `tests/terminal/test_settings_router.py` — every endpoint incl. invalid→400, theme WS broadcast, RISK_DECISION announce, scheduler restart/stop/start (fake handle + key-gated start)
- `tests/intelligence/test_risk_settings_backend.py` — regression net for all 4 hardcoded locations (filters, engine chain, projection, bus bridge, execution fallback)

## 7. Verification

- Full suite: **1241 passed / 0 failed / 0 skipped** (`pytest tests/` with the AGENTS.md command form).
- Gates: `grep "import openalgo|from openalgo" src/` → zero; no source file > 1000 lines; `core/` gains no external imports (only stdlib + internal `core/storage`).

## 8. Notes for the frontend follow-up task

- `GET /api/settings` returns `{loss_limit, max_positions, theme, scheduler:{...}}` — one call renders the whole form; `PUT /api/settings` accepts any subset.
- Theme: server persists it; `PUT /api/settings/theme` broadcasts a WS `theme` frame so the SPA can switch live — the SPA should reconcile with the existing `localStorage["sx-theme"]` (server wins on form save; store value is the seed on load).
- Scheduler enable may report `enabled: true, running: false` — show "not running (set DEEPSEEK_API_KEY)" honestly rather than claiming active.
- Risk caps are live end-to-end: form save → RISK_DECISION → risk strip updates without restart; the blocking filters re-read on each check.
