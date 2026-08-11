# Mission Plan — Fyers Migration + Deep Audit + Cockpit Redesign

**Date:** 2026-08-04 · **Status:** Phase Zero complete — awaiting operator decisions (§9)
**Branch:** `fix/terminal-data-pipeline` · **Baseline:** `861 passed / 0 failed / 0 skipped` (39s, recorded 2026-08-04)

**Inputs reconciled:** 6 recon lanes (integration, core, intelligence+research+data+options+learning, knowledge, execution+auth, terminal), primary-source Fyers research (librarian), council of three (alpha/beta/gamma) + synthesis.

> **Baseline correction:** AGENTS.md states the suite at 599/0/3. Actual suite today is **861/0/0** (grew since the doc was written). The binding gate is "no regressions vs 861" plus new Fyers parity tests. AGENTS.md suite-count line is itself an audit finding.

---

## 1. Governance conflict (BLOCKING — operator decision required)

`.projectos/identity/frozen-rules.md` contains rules that legally contradict this mission:

- **FR-002 "Dhan-Native Integration":** "Dhan is the primary broker… Other brokers are secondary and routed through OpenAlgo's abstraction."
- **FR-003 "OpenAlgo Delegation":** "Order execution, broker abstraction, and WebSocket plumbing are delegated to OpenAlgo. We do NOT reimplement these."
- **BOUNDARY-003** (`boundaries.json`): DhanHQ isolation — already violated in practice by `data/pipeline/stream_manager.py` importing `dhanhq` inside `data/`.

The codebase already diverged from FR-002/FR-003 (direct `dhanhq` integration; OpenAlgo vendored but never imported from `src/`). Replacing Dhan with Fyers requires formally amending FR-002/FR-003 (and renaming BOUNDARY-003 → broker-SDK isolation). **No code work starts until the operator approves the amendment path.**

## 2. Codebase map (recon summary)

| Layer | State | Migration surface |
|---|---|---|
| `core/interfaces/` | 5 broker-neutral Protocols (`OrderExecutor`, `AccountInfo`, `MarketDataStream`, `DataProvider`, `BrokerGateway`); `DataFetcher` dead code | **None** (Fyers bends to them); optional `is_session_valid()` on `BrokerGateway` |
| `integration/dhan/` | `data_adapter.py` 683 ln, `trading_adapter.py` 615 ln (both >500, known violations); WS supervisor, 806/807 handling, `SessionHealth` token minting | **Replace wholesale** |
| `integration/` shared | `instrument_master.py` 360 ln (Dhan security IDs, `fetch_security_list`), `order_validator.py` 125 ln (Dhan-flavored value sets) | Rework |
| `data/pipeline/stream_manager.py` | **Second, parallel Dhan WS path** bypassing `MarketDataStream`; lazy `dhanhq` imports; feed code 17; layering violation | **Consolidate through the Protocol — migration is half-done without this** |
| `auth/` | Dhan-shaped: JWT `dhanClientId` parsing, 3-step consent, PIN/TOTP minting, `api.dhan.co/v2/fundlimit` probe, 300s health cadence | Near-total rewrite |
| `execution/` | Broker-agnostic; D10 OBSERVER gate intact; gaps: no proposal persistence (`db_path=None`), mode_router cancel/modify routing quirks | Minimal (add session-valid gate) |
| `intelligence/`, `options/`, `learning/` | Live pipeline, but audit whiffs: stub voters (`orb_breakout` never computed → constant votes), `tte=0.25` hardcoded greeks, bar-boundary double-count, `NIFTY=13/BANKNIFTY=25` hardcoded, layering violations (intelligence↔learning cycle) | Phase 2 audit scope |
| `knowledge/` | Clean, broker-agnostic, fully tested | None (cosmetic `NSE_FNO:` prefix in core lexicon) |
| `terminal/` | `app.py` 502 ln composition root; 40+ routes; Dhan leaks in routers (`EXCHANGE_MAP` imports, security IDs, 806 text) | Rework wiring + routers |
| Frontend (Svelte 5) | 39 files, design tokens faithful to DESIGN.md; gaps: no fetch timeouts, no stale indicators, regime/signal never displayed, right column hidden <1440px | Phase 3 redesign + Fyers wizard copy |
| Tests | ~10 Dhan-coupled files (~80+ tests) incl. `sys.modules` dhanhq mock in conftest | Two-wave port (§5 Phase 1) |
| Docs/config | README, ADR-007, ARCHITECTURE_V2 §11, CHANGELOG, `configs/default.yaml` (`broker: dhan` + vestigial openalgo keys), `default_watchlist.yaml` (Dhan security IDs), version drift across 5 files | Sweep + amend |

## 3. Fyers facts (primary-source verified, 2026-08-04)

- **Auth:** OAuth2 authorization-code. `GET /api/v3/generate-authcode` → browser login → callback `auth_code` (single-use, short-lived) → `POST /api/v3/validate-authcode` with `appIdHash = sha256(app_id:secret_id)` → `access_token` (+ `refresh_token` returned but refresh endpoint **undocumented, possibly discontinued**). Header `Authorization: <app_id>:<access_token>` everywhere incl. WS.
- **Token TTL unpublished.** Community "~6 AM IST" unverifiable. Design for **daily interactive re-auth as the reliable path**; liveness via `/profile` probe. Expiry errors: REST `-8/-15/-16/-17` or 401; data socket `11001`/`-99`; order socket 403 handshake. Community TOTP+PIN automation (sample-repo issue #44) ≈ our `DhanLogin.generate_token` fallback.
- **Error mapping:** Dhan 806 (data entitlement) → Fyers **HTTP 403 / `-373`** (app permission template lacks Market Data). Dhan 807 (silent renew) → Fyers interactive re-login. **No sandbox** (`uat-api.fyers.in` dead) → real account + OBSERVER mode + small notionals.
- **Rate limits:** 10 req/s · 200/min · 100k/day; order ops 10/s; **minute-cap breach >3×/day = blocked all day**. Token-bucket throttle (~8/s) mandatory day one.
- **REST:** `api-t1.fyers.in/api/v3` — profile/funds/holdings/positions/tradebook/orders; `POST /orders/sync` (type 1=Limit 2=Market 3=SL-M 4=SL-L; productType CNC/INTRADAY/MARGIN/MTF; side 1/-1; validity DAY/IOC). **CO/BO deprecated 2026-08-02** → `stopLoss`/`takeProfit` params. SEBI algo regs in effect since 2026-04-01 — re-check `/mandatory-regulatory-changes` before go-live.
- **Data API:** `/data/history` (resolutions 5S–240m/D/W/M; minute ≤100 days/req; daily ≤366 days; `oi_flag=1` appends OI); `/data/quotes` (≤50 symbols); `/data/depth`; `/data/options-chain-v3` (greeks, ≤50 strikes).
- **WS:** data socket `wss://socket.fyers.in/hsm/v1-5/prod` (**HSM binary protocol**, 5000 symbols/conn, 10s heartbeat); order socket `wss://socket.fyers.in/trade/v3` (**JSON**, `SUB_ORD` subscribe; replaces Dhan postback webhooks — fill fidelity improves); TBT protobuf (not needed).
- **Symbols:** `NSE:SBIN-EQ`, `NSE:NIFTY50-INDEX`, `NSE:NIFTY20OCTFUT`, weeklies use month codes `1-9/O/N/D` — **#1 `-300` gotcha**. Daily master `public.fyers.in/sym_details/<MASTER>_sym_master.json` (live-verified) → exact-match lookup, never hand-construct.
- **SDK `fyers-apiv3` 3.1.15** (MIT, 2026-08-02): sync/threading model, singleton data socket, junk deps (`asyncio==3.4.3` shadows stdlib, `aws-lambda-powertools`) → needs `--no-deps` + pinning if used at all.
- **`FyersDev/fyers-skills`** (MIT): condensed current operating manual as agent skills — vendor/adapt as Phase 1 reference material.

## 4. Council verdicts (alpha/beta/gamma → synthesis)

| Q | Verdict | Confidence |
|---|---|---|
| Q1 SDK vs raw | **Majority (2–1): raw** httpx + websockets. Alpha dissented (SDK-wrap). Dhan SDK pain is documented in-repo (`_DisconnectAwareFeed`, `feed._running` pokes, `_feed_supervisor`). Librarian data adds nuance: REST raw is unambiguous; market-data HSM socket is where SDK still has value → **hybrid option on the table** (§9 Q2) | High |
| Q2 Auth lifecycle | **Unanimous:** broker-discriminated credential store; delete JWT parsing; OAuth-code wizard; 60s health cadence + pre-market probe; no auto-browser-redirect mid-session; STALE-freeze with honest badge, never zeros | High |
| Q3 Contracts | **Unanimous:** zero Protocol changes; Dhan-shaped pain is in *callers* (`terminal_init.py:110-118`, `market_router.py:22`), not Protocols. Sole candidate addition: `is_session_valid()` on `BrokerGateway` for D10 LIVE gating | High |
| Q4 Sequencing | **Unanimous:** honesty fixes BEFORE migration ("Phase 1.0"). Migrating onto a health system that lies makes Fyers verification untrustworthy | High |
| Q5 Cockpit IA | **Unanimous:** connection/auth pip (4 distinct states), IST clock + session, positions/PnL + real margin, watchlist with stale-fade, regime+signal line at-a-glance; order entry keyboard-first modal, not permanent panel; vertical slices S0–S5, LIVE disabled until S0+S1 honesty guarantees hold | High |

**Convergent findings (independently discovered by ≥2 seats):** duplicate WS path (`stream_manager.py`), HealthProjection lies about data + trading health, hardcoded `margin_available=500000`, fake latency metrics, 44+ Dhan exchange-format refs, Dhan-JWT credential store, ~10 Dhan-coupled test files, UTC/IST mixing (`stream_manager.py:226` UTC vs `data_adapter.py:476` IST).

## 5. Phase plan (dependency-ordered)

### Phase 1.0 — Honesty hardening (prerequisite, est. 2–4 days)

Backend fixes (no broker dependency):
1. `HealthProjection`: wire `is_stale()`/`last_data_time` into data health (`projections.py:350-369`); trading health checks token validity, not object existence (`:372-384`).
2. Real margin: init "margin unknown" (never `500000.0`) in `projections.py:139` + `execution_router.py:125`; wire `get_margin()`.
3. Kill fake latency (`projections.py:340-341`, `:405`) — measure or remove.
4. UTC/IST convention: **UTC internal, IST display-only** (fix `stream_manager.py:226`, `market_router.py:138` naive `date.today()`, `trading_adapter.py:527`, `voter_quality.py:64,89`).
5. `TokenHealthMonitor` 60s cadence (prep for Fyers daily tokens).
6. Cockpit **S0** (Designer lane): connection pip with 4 visibly distinct states (LIVE/STALE/DISCONNECTED/TOKEN EXPIRED), watchlist stale-fade, honest empty/loading/error primitives.

**Entry:** baseline 861 recorded (done). **Exit:** health endpoint cannot lie; suite green vs 861 + new regression tests for each fix; `npm run check` clean; operator approval to start Phase 1.

### Phase 1 — Fyers migration (est. 1–3 weeks; lanes ordered by dependency)

- **F1 — Symbols + instrument master (FIRST):** Fyers master download → SQLite; resolver with weekly/monthly encoding; round-trip gate: every `default_watchlist.yaml` symbol resolves internal→Fyers→validate via `/quotes`. Also `order_validator.py` value sets.
- **F2 — Transport/session:** `client.py` (httpx, token-bucket ~8/s, 401→`AUTH_EXPIRED` classification, `Retry-After` backoff), `session.py` (expiry tracking, `/profile` probe, persist-to-store), `mappings.py`.
- **F3 — WS:** order socket (JSON, raw `websockets`) + data socket (per §9 Q2 decision: raw HSM or supervised SDK socket); reconnect test matrix (token-expiry-mid-feed, network drop, server disconnect, 403-on-reconnect = re-auth trigger); consolidate `IngestionPipeline` through `MarketDataStream`, delete `stream_manager.py` dhanhq coupling.
- **F4 — Adapters:** thin `trading_adapter.py` + `data_adapter.py` implementing the 4 Protocols; history chunking (≤100 days/req); options chain via `/data/options-chain-v3`; funds→`get_margin()` mapping.
- **F5 — Auth + wizard:** credential store (broker discriminator, delete JWT parsing), `FyersOAuthHelper` (auth-code flow, immediate exchange), `/fyers/callback`, validator probe → Fyers endpoint, 60s monitor + pre-market probe, frontend SetupWizard/SettingsView/Header de-Dhan.
- **F6 — Wiring:** `terminal_init.py` swap, routers de-Dhan (`market_router`, `watchlist_router`, `intelligence_router`), postback → order-WS fills (`ORDER_UPDATED`), `mode_router.py` session-valid gate, `config_manager.py`/`configs/default.yaml` (`broker: fyers`, drop vestigial openalgo keys), `pyproject.toml` (`dhanhq` out).
- **F7 — Tests + sweep + docs (parallel throughout):** two-wave port (adapter-unit first with mock transport; router/wiring last); delete `integration/dhan/` + Dhan wire-format tests in ONE commit only after zero-grep + green; README/ADR/CHANGELOG/ARCHITECTURE_V2 §11 updates; `.projectos` amendments per §1 decision; version alignment across the 5 drifted files.

**Exit gates:** full suite green (861 baseline − deleted Dhan tests + Fyers parity ≥ ported behavioral coverage); `grep dhanhq|dhan` in `src/` = zero (docs explaining history allowed); openalgo-import grep zero; no new file >500 lines; symbol round-trip test green; token-expiry + entitlement(403/-373) + WS-reconnect + rate-limit tests present; OBSERVER-first intact (LIVE typed-confirm, never auto-restored); `npm run check` clean; ADR written.

### Phase 2 — Deep audit (est. 1–2 weeks)

Per-layer audit Explorers seeded with recon suspicions (26 items already catalogued, incl.: stub voters dominating signals, `tte=0.25` greeks, bar-boundary double-count, `shadow_manager` sessions-vs-rows unit mix, `oi_tracker` subscribed to wrong event shape, `mode_router` KeyError on unknown status, ledger NULL-symbol fills → realized PnL silently zero, missing proposal persistence, `position_manager` EOD compares UTC hours against IST config). Oracle independently reviews findings. → categorized report `docs/superpowers/plans/2026-08-XX-audit-findings.md` (critical/major/minor, file:line, why wrong, fix). **Operator chooses tiers.** Critical (money-path/crash/corruption) fixable immediately after asking. Every executed fix gets a regression test; suite green at end.

### Phase 3 — Cockpit redesign (est. 3–4 weeks, approval-gated slices)

Brainstorm IA with operator first (2–3 density options via question tool). Slices: **S1** shell + clock + connection status (DESIGN.md token review gate) → **S2** watchlist + live ticks (gate: tick-to-pixel, Indian red=up) → **S3** positions/PnL/real margin (gate: matches broker console) → **S4** orders + execution (gate: OBSERVER proposals-only, LIVE typed-confirm) → **S5** chain/scanner/intelligence (gate: honesty guarantees hold) → **S6** depth (research/analytics/settings). Global fetch layer (AbortController timeouts + `Promise.allSettled`) in S1. DESIGN.md binding throughout; `npm run check` + build per slice.

## 6. Dependency graph

```
[§1 governance decision] ─┐
[§9 operator decisions] ──┤
                          ▼
              Phase 1.0 honesty hardening ──────────────┐
              (backend fixes ∥ cockpit S0)              │ operator approval
                          ▼                             │
   F1 symbols/master ──► F4 adapters ◄── F2 transport   │
                              ▲            F3 WS ───────┤
   F5 auth/wizard ────────────┘                         │
   F7 tests+sweep ∥ all lanes                           ▼
                          ▼
              F6 wiring (last) ──► Phase 1 exit gates
                          ▼
              Phase 2 audit ──► operator tier selection ──► fixes
                          ▼
              Phase 3 IA brainstorm (operator) ──► S1…S6 gated slices
```

## 7. File ownership (no two writers on one file)

| Lane | Owns |
|---|---|
| P1.0-backend | `terminal/projections.py`, `terminal/api/execution_router.py`, `terminal/api/models.py`, `auth/health_monitor.py`, `data/pipeline/stream_manager.py` (tz only), `terminal/api/market_router.py` (tz only), `learning/voter_quality.py`, `terminal/api/app.py` (margin-wiring slice only, ~10 lines) |
| P1.0-S0 (Designer) | `web/src/App.svelte`, `Header.svelte`, `Watchlist.svelte`, new shared state primitives |
| F1 | `integration/fyers/symbols.py`, `integration/fyers/instrument_master.py`, `integration/instrument_master.py`, `integration/order_validator.py`, `configs/default_watchlist.yaml` |
| F2 | `integration/fyers/{client,session,mappings,__init__}.py` |
| F3 | `integration/fyers/ws_client.py`, `data/pipeline/stream_manager.py`, `data/ingestion.py` |
| F4 | `integration/fyers/{trading_adapter,data_adapter}.py` |
| F5 | `auth/*`, `terminal/api/{auth_router,settings_router}.py`, frontend auth surfaces |
| F6 | `terminal/api/{terminal_init,instrument_init,app,market_router,watchlist_router,intelligence_router,postback_router}.py`, `terminal/projections.py`, `execution/mode_router.py`, `core/interfaces/broker_gateway.py`*, `core/config/config_manager.py`, `configs/default.yaml`, `pyproject.toml` |
| F7 | `tests/**`, docs, `.projectos` amendments |

*only if operator approves `is_session_valid()` addition.

## 8. Risk register

| # | Risk | Mitigation |
|---|---|---|
| R1 | Mid-session token expiry, no silent refresh | session-valid gate before LIVE; visible EXPIRED state + STALE freeze (never zeros); PAPER default; D10 no-auto-restore |
| R2 | Symbol-format cascade (44+ refs; weekly encoding `-300`) | master+resolver FIRST with round-trip gate; grep-categorize refs before touching |
| R3 | Test regression surface (~10 files) | baseline recorded; parallel adapters; two-wave port; delete Dhan in one commit at zero-grep+green |
| R4 | Rate limits (200/min; 3 strikes = day block) | token-bucket ~8/s day one; WS for ticks, never poll; order queue; honor `Retry-After` |
| R5 | WS reconnect semantics differ from Dhan | standalone ws client + reconnect test matrix before pipeline wiring |
| R6 | Half-migrated data path (`stream_manager.py`) | consolidation is Phase 1 exit criterion, not cleanup |
| R7 | No Fyers sandbox | OBSERVER-first + dry-run tooling + small notionals; pre-market probe gates ingestion |
| R8 | SEBI regulatory drift (CO/BO gone; more changes flagged) | re-check `/mandatory-regulatory-changes` before go-live; ADR records 2026-08 state |
| R9 | Frozen-rule amendment blocked by operator | decided up-front (§9 Q1) before any code |

## 9. Open operator decisions (asked via question tool)

1. Frozen rules FR-002/FR-003 amendment path.
2. Adapter substrate: full-raw vs hybrid (raw REST + raw order-WS + SDK data socket) vs SDK-wrap.
3. Confirm Phase 1.0 honesty-first ordering.
4. Dhan test strategy: gamma-split (delete wire-format, port behavioral) vs 1:1 port.
5. `is_session_valid()` addition to `BrokerGateway`.
6. `secret_id` at rest in Fernet store.
7. Cockpit reframe: S0 prerequisite + vertical slices vs big-bang.
8. Mid-migration gate: "no new failures" during coexistence vs strict-green throughout.

## 10. Verification gates (every phase exit)

```powershell
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider
```
plus: `grep -r "import openalgo\|from openalgo" src/` = zero · no new file >500 lines · `npm run check` 0 errors before `npm run build` · layering greps · `graphify update .` after code changes.
