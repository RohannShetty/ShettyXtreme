# Section 10 — OpenAlgo Utilization

> The vendor contract, per D1 and D2: ShettyXtreme is **standalone** — no OpenAlgo server, no `import openalgo` anywhere in `src/`. A curated 10-file slice of OpenAlgo's execution plumbing is vendored at `vendor/openalgo/` as *adaptation source only*, synced from the fresh upstream mirror `references/upstream/openalgo` (v2.0.1.7, per corrected fact 3). Evidence: `docs/references/BRIEF-openalgo-upstream.md`. This section rewrites `docs/architecture/v1/sections/10-openalgo-utilization.md`.

## 1. What is vendored (exact 10-file list)

`scripts/sync_vendor.py` pulls these files from the mirror; `vendor/openalgo/FILES.yaml` records each source path + version so the diff review is scriptable. Files keep their AGPL-3.0 headers and an origin stamp (source version + sync date).

| # | Vendored file | What it provides | Internal deps (all within the set) |
|---|---|---|---|
| 1 | `vendor/openalgo/utils/constants.py` | **Single source of truth** for order validation: `VALID_EXCHANGES`, `VALID_PRODUCT_TYPES`, `VALID_PRICE_TYPES`, `VALID_ACTIONS`, `REQUIRED_*_FIELDS`, defaults | none (stdlib only) |
| 2 | `vendor/openalgo/broker/dhan/plugin.json` | Dhan broker metadata: `supported_exchanges`, `broker_type: IN_stock`, `leverage_config: false` — the discovery contract for the adapter pattern | none |
| 3 | `vendor/openalgo/broker/dhan/api/baseurl.py` | Dhan REST base URL + `get_url()` builder | none |
| 4 | `vendor/openalgo/broker/dhan/api/auth_api.py` | OAuth consent flow: `generate_consent`, `get_login_url`, `get_access_token`, `authenticate_broker` (client_id `:::` api_key split) | 3, 6, 9 |
| 5 | `vendor/openalgo/broker/dhan/mapping/transform_data.py` | **Order mapping + SL-M → protective STOP_LOSS conversion** (2.0.1.6 MPP fix, issue #1647) + tick snapping; also applied on modify | 8, 7, 9 |
| 6 | `vendor/openalgo/utils/httpx_client.py` | Shared timeout'd HTTP client (fixes the missing-timeout class of bugs) | 9 |
| 7 | `vendor/openalgo/utils/mpp_slab.py` | MPP slab table — protective-price calculation and tick rounding used by #5 | 9 |
| 8 | `vendor/openalgo/database/token_db.py` | Symbol ↔ token mapping API (`get_symbol/get_token/get_br_symbol/get_oa_symbol`) | **Shim caveat:** this file is a backward-compat re-export; its substance lives in `database/token_db_enhanced.py`, which is **not** in the vendored set. Phase 2 must vendor or reimplement the enhanced module so the vendored shim resolves — tracked as an open item |
| 9 | `vendor/openalgo/utils/logging.py` | Centralized JSON logging (`get_logger()`, 2.0.1.7 hardening) | stdlib |
| 10 | `vendor/openalgo/database/symbol.py` | `SymToken` model (14.7 KB) imported by #8 and the Dhan mapping files | none |

**Explicitly NOT vendored** (server/Flask/ZMQ/DB layer, per brief): `app.py`, `blueprints/`, `restx_api/`, `database/auth_db.py` (48.9 KB Flask-SQLAlchemy tangle — we have our own Fernet `CredentialStore`), `sandbox/`, `websocket_proxy/server.py`, all order *services, `broker/dhan/api/order_api.py` and `api/data.py` (B-tier, Phase-2 candidates if adapter work shows value), options *services, `utils/plugin_loader.py` (Flask `current_app` coupling — the *pattern* is copied, not the code).

## 2. What only wraps (adaptation, not importation)

The vendored files are **never importable** from `src/` (D1; enforced by a CI grep rule per [Section 07 — Update-Resilient Design](07-update-resilient-design.md)). First-party adaptations live in `integration/` and implement `core/interfaces` Protocols:

| Vendored source | Adaptation in `src/` | Implemented protocol |
|---|---|---|
| `utils/constants.py` | `integration/dhan/order_validator.py` consumes the constants (validation logic is ours, constants are theirs) | `core/interfaces` order validation contract |
| `mapping/transform_data.py` (+ `mpp_slab.py`) | Dhan order-mapping module behind an `OrderMapper` interface | `core/interfaces` mapping contract |
| `api/auth_api.py`, `api/baseurl.py` | `auth/DhanOAuthHelper` consent flow (D8 single-primary + fallback slot) | `core/interfaces` auth contract |
| `plugin.json` + the plugin-discovery *pattern* | Capability discovery on the Dhan adapter ([Section 11 — Dhan Integration](11-dhan-integration.md)) | `core/interfaces` capability contract |
| `utils/logging.py`, `utils/httpx_client.py` | Patterns reviewed and reimplemented in `observability/` + adapter HTTP layer where our own abstractions are cleaner | — |

## 3. What NEVER builds from scratch

1. **Order validation constants for Indian exchanges** — NSE/BSE/NFO exchange, product, price-type, action membership and required-field sets already exist and are battle-tested upstream; vendored as-is (file #1).
2. **The broker adapter interface pattern** — plugin.json discovery + `authenticate_broker` entry point + capability registry is proven across 35 brokers; we copy the *pattern* and implement it first-party.
3. **Dhan order mapping (order dict → Dhan payload, incl. SL-M protective conversion)** — the 2.0.1.6 protective-limit math is subtle (MPP slabs, tick snapping) and must-vendor; rewriting it from scratch invites silent order-routing regressions.

## 4. What stays independent (the whole moat)

| Domain | Reason it stays ours |
|---|---|
| ALL core domain models + event bus + Protocols | Stable layer A, zero external imports ([Section 05 — System Boundaries](05-system-boundaries.md)) |
| ALL intelligence (signal engine, voters, regime, options, risk, scanners) | The edge; OpenAlgo has no analogue |
| ALL execution logic (order lifecycle, PositionManager, semi-auto approval) | Our risk posture (D10, kill switch) is not theirs |
| ALL learning (outcome tracking, walkforward, calibration) | Feedback loop is ours |
| ALL UI | Svelte terminal per D9, governed by DESIGN.md (D4) |
| ALL storage | SQLite KV + DuckDB TS, our schema |
| ALL config | Our YAML + env system (pydantic) |

## 5. Used heavily without becoming a tangle

OpenAlgo's value (order validation, Dhan mapping, SL-M math) is absorbed so thoroughly that the platform *is* Dhan-first and correct on day one — while the coupling surface stays at exactly 10 files:

1. **Origin markers** — every vendored file carries an AGPL notice + origin stamp; every `integration/` adaptation carries a comment naming the source file and version.
2. **No imports** — `import openalgo` anywhere in `src/` fails CI (D1). `vendor/` is a source tree, not a package on `sys.path`.
3. **Monthly diff review** — upstream ships ~3 releases/month (v2.0.1.4 → 2.0.1.7 in 28 days); review release notes first (`docs/releases/version-2.0.1.X-released.md` in the mirror), then diff the 10 vendored files. Watch list: `transform_data.py` + `mpp_slab.py` (protective-limit math), `utils/logging.py`/`httpx_client.py` (reliability hardening), `auth_api.py` (token flows).
4. **Sync script** — `scripts/sync_vendor.py` + `vendor/openalgo/FILES.yaml` make the pull mechanical; the diff review is the human gate.
5. **Adaptation-not-importation** — vendored code implements `core/interfaces` Protocols; swapping or dropping a vendored file never ripples past `integration/dhan/`.

## 6. AGPL boundary (D2)

- **Private use only:** ShettyXtreme is never distributed or sold; monetization is personal trading edge + prop-scale own-capital (D2, D11). Vendoring without conveyance is covered by AGPL s2 ("make, run and propagate covered works that you do not convey, without conditions"); the s13 source-offering obligation attaches only if the modified code is ever offered as a network service to users — which D2 forbids.
- **Housekeeping (enforced):** AGPL notices intact on every vendored file (s4); origin stamp shows the work is modified + date (s5a); **`vendor/openalgo/LICENSE` ships the AGPL-3.0 text** with the repo.
- **Boundary if intent changes:** if ShettyXtreme were ever distributed, the vendored subtree and any derivative must remain AGPL-3.0; separate legal review would be required. This is the only condition under which the current posture changes.

Cross-references: [Section 01 — Reverse-Engineering Lens](01-reverse-engineering-lens.md) (OpenAlgo role table), [Section 07 — Update-Resilient Design](07-update-resilient-design.md) (ACLs, sync workflow), [Section 18 — Repo Codebase Strategy](18-repo-codebase-strategy.md) (vendor/ + references/ zones).
