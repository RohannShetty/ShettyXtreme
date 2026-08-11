# Phase 7 Wave 4 — DECIDED-DEFER Re-evaluation (#13)

**Date:** 2026-08-06
**Status:** COMPLETE — all four DECIDED-DEFER items re-confirmed deferred; no spec/plan required
**Mission source:** `docs/superpowers/plans/2026-08-05-phase7-recon.md` §1.13
**Baseline:** Phase 7 Wave 3 in progress (settings form backend)

## 0. Conclusion (read this first)

No DECIDED-DEFER item graduates to implementation. All four recorded triggers remain un-fired in the live codebase — the recon's §1.13 verdict ("NO CHANGE, triggers un-fired") is re-confirmed by independent grep/glob/read evidence. Records were updated in place (issues/07, issues/08, wayfinder map, roadmap §17); mission task 4 (spec/plan) is a no-op by its own conditional ("if any item should now be implemented").

| Deferred item | Recorded trigger | Status today (2026-08-06) | Verdict |
|---|---|---|---|
| Multi-broker | concrete broker need / missing Fyers capability (`issues/07-multibroker-decision.md:16`) | Fyers migration complete — `integration/` is Fyers-only (11 modules); no second-broker need | **Keep deferred** |
| Backtest depth | comparison-surface need (`issues/08-backtest-depth-scope.md:16`) | Walkforward stays (`learning/walkforward.py`); no comparison surface in `src/` | **Keep deferred** |
| Critic pass | waits for order intents to gate (`map.md:51`) | `grep "intent"` in `src/` = 1 hit — the docstring word "intentionally" (`settings_router.py:5`); no order-intent concept | **Keep deferred** |
| Live `/optionchain` fixture | needs live credentials (`map.md:52`) | No fixture in repo; `get_option_chain` is live-only (`integration/fyers/data_adapter.py:425`); live creds env-gated | **Keep deferred** |

## 1. Evidence per item

### 1.1 Multi-broker — KEEP DEFERRED
- Trigger: concrete broker need or missing Fyers capability (`issues/07:16`).
- Today: Fyers migration complete. `src/shettyxtreme/integration/` contains only `integration/fyers/` (11 modules: client, session, trading_adapter, data_adapter, data_socket, ws_client, symbols, instrument_master, mappings, `_util`, `__init__`). Dhan remains only as legacy comments (`integration/order_validator.py:7-26`), credential migration (`auth/credential_store.py:89-103`), and the retained legacy `/api/postback/dhan` webhook (`terminal/api/postback_router.py:137-141`).
- Config default is Fyers (`core/config/config_manager.py:47` — `broker: str = "fyers"`); no second-broker adapter code exists anywhere in `src/`.
- No blockers removed that would change the decision (the Fyers migration completed, which is the record's context, but nothing created a *second*-broker need). Trigger NOT met.

### 1.2 Backtest depth — KEEP DEFERRED
- Trigger: comparison-surface need (`issues/08:16`).
- Today: walkforward unchanged — `learning/walkforward.py` (`WalkforwardEvaluator`, `WalkforwardResult`), covered by `tests/wave4/test_walkforward.py`. No strategy-comparison surface and no separate backtest runner exist in `src/`; Phase 4-6 built no comparison surface.
- Live edge = deterministic engine; backtest-theater risk unchanged. Trigger NOT met.

### 1.3 Critic pass — KEEP DEFERRED
- Trigger: waits for order intents to gate (`map.md:51`, roadmap §17).
- Today: `grep -r "intent" src/` = exactly 1 hit, and it is the docstring word "intentionally" in `terminal/api/settings_router.py:5` — unrelated. No `OrderIntent`/`order_intent` type, store, or event anywhere in `src/` (also matches recon §1.13).
- Order intents remain a future concept (architecture §12 "propose, never bind" doctrine, `BRIEF-anthropics-financial-services.md:59-60`); nothing exists to gate. Trigger NOT met.

### 1.4 Live `/optionchain` fixture — KEEP DEFERRED
- Trigger: needs live credentials (`map.md:52`).
- Today: no fixture files exist (`**/*optionchain*.json` = 0 matches; no `tests/fixtures/**/*optionchain*`). `FyersDataAdapter.get_option_chain` (`integration/fyers/data_adapter.py:425`) calls the live `/data/options-chain-v3` endpoint; key-name defensiveness is covered by tests only (`tests/wave2/test_strategy_hints.py:53`, `tests/integration/test_fyers_data_adapter.py:528-530`).
- Live Data-API credentials cannot be verified from code (env-gated; Fyers 403/-373 entitlement = Dhan-806 twin, surfaced as `FyersDataEntitlementError`). Trigger NOT met.

## 2. Process

1. Read all four DECIDED-DEFER records: `issues/07-multibroker-decision.md`, `issues/08-backtest-depth-scope.md`, `map.md:34-35,51-52`, roadmap §17 (`docs/architecture/v2/sections/17-delivery-roadmap.md:11`).
2. Re-checked each trigger against the live codebase (read-only grep + glob + read).
3. Updated the records in place with a dated re-evaluation status and evidence.
4. Created this findings report. No spec/plan created (no item graduated).

## 3. Files updated

- `.scratch/phase4-knowledge-dashboards/issues/07-multibroker-decision.md` — appended re-evaluation section.
- `.scratch/phase4-knowledge-dashboards/issues/08-backtest-depth-scope.md` — appended re-evaluation section.
- `.scratch/phase4-knowledge-dashboards/map.md` — lines 34-35, 51-52 annotated; line 52 corrected "Dhan" → "Fyers" (migration complete).
- `docs/architecture/v2/sections/17-delivery-roadmap.md:11` — Phase-4 status cell annotated. **NOTE:** the mission listed `.scratch/phase4-knowledge-dashboards/sections/17-delivery-roadmap.md`, which does not exist; the canonical DECIDED-DEFER record is the architecture roadmap (recon index line 208), so it was updated there.

## 4. Recorded re-open triggers (for future waves)

- Re-open multi-broker if a concrete second broker or a missing Fyers capability appears.
- Re-open backtest depth if a strategy-comparison surface becomes a concrete requirement.
- Re-open critic pass when order-intent plumbing exists (architecture §12 intent concept).
- Re-open the optionchain fixture when live Fyers Data-API credentials are available in this environment.