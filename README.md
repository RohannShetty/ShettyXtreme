# ShettyXtreme

**India-first options intelligence workstation** — a standalone, Dhan-connected terminal for NSE/BSE index options (NIFTY/BANKNIFTY weeklies), with equities as market breadth.

v0.7.0 · Python 3.11 + FastAPI + Svelte 5 · 527 tests passing · [Changelog](CHANGELOG.md)

ShettyXtreme turns live Dhan market data into a single cockpit: option chain with greeks and IV, strategy hints with expected-value line items, regime and signal intelligence, positions/risk, and OBSERVER-first execution — the platform watches and proposes; you approve.

---

## Quickstart

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
python run.py --mode OBSERVER
```

Your browser opens `http://127.0.0.1:8000/`. First run: connect credentials at the setup view (`#/setup`), then the cockpit (`#/`) renders watchlist, chain, hints, positions/risk, and the logs drawer.

`run.py` flags:

| Flag | Meaning |
|---|---|
| `--mode OBSERVER\|PAPER\|LIVE` | Execution mode. **OBSERVER is the default** (D10) |
| `--no-browser` | Don't auto-open the browser |
| `--port 8000` | Uvicorn port |

**LIVE is an explicit per-session action**: `--mode LIVE` prompts for typed confirmation; switching LIVE in the terminal shows a confirmation dialog; a persisted LIVE mode never auto-restores on restart.

## The Cockpit

A dark, data-dense Svelte SPA governed by [DESIGN.md](DESIGN.md) (binding token contract: price-up = red `#f6525c`, price-down = green `#2ebd85` — Indian convention — JetBrains Mono numerals):

- **Watchlist** (left rail) — LTP, change%, tick flashes
- **Option chain** — strike / CE-PE / LTP / IV / greeks / OI (min 720px)
- **Strategy hints** — direction, strategy, strike EV line, rationale (min 320px)
- **Scanner** — gaps, clusters, alerts
- **Positions / risk strip** (bottom) — P&L, margin vs limits, loss-limit breach chip
- **Logs / alerts drawer** (right, min 320px)
- **Session controls** (header) — mode switcher, kill switch (`Ctrl+Shift+K`, never disabled), health strip incl. Dhan Data-API entitlement state

Frontend dev (Vite on :3000, proxies `/api` + `/ws` to :8000):

```powershell
cd src/shettyxtreme/terminal/web
npm install
npm run dev      # live-reload dev server
npm run check    # svelte-check type gate (0 errors required)
npm run build    # build → terminal/static/ (committed bundle)
```

## Architecture

The v2 blueprint is the authoritative spec: [`docs/architecture/v2/ARCHITECTURE_V2.md`](docs/architecture/v2/ARCHITECTURE_V2.md) (master doc + 20 sections, decisions D1–D12, ADR-002…007). In one paragraph:

A layered modular monolith. **FastAPI** (`terminal/api/`) is the only REST/WS surface; the **EventBus** (`core/event_bus/`) carries ticks/signals/orders; **Dhan adapters** (`integration/dhan/`) implement `core/interfaces` protocols (single `DhanContext` per D8 — one consent token, optional `data_access_token` fallback); the **intelligence pipeline** (`intelligence/`) runs features → regime → signal (D/P/G conviction voters) → options EV → risk; the **execution engine** (`execution/`) is semi-auto with a mode gate; the **options module** (`options/`) is pure-Python pricing (Black-76, greeks, IV rank, OI tracking, strategy analyzer) with an optional QuantLib backend.

```
src/shettyxtreme/
  core/            Event bus, storage (KV/time-series), config, interfaces (Protocols)
  auth/            Fernet credential store, OAuth + PIN/TOTP flows, health monitor
  integration/     Anti-corruption layer: Dhan data + trading adapters (D1: no vendor imports)
  data/            Ingestion pipeline (watchlist → ticks/bars → stores)
  intelligence/    Features, regime, signals (VoterRegistry), voters, options (IV rank/PCR/EV),
                   hints, conviction, risk, scanners
  execution/       ExecutionEngine (semi-auto approval), PositionManager (TP/TSL/EOD), paper trading
  options/         Greeks, IV rank, OI tracker, QuantLib pricer, strategy analyzer
  learning/        Outcome tracking, calibration, walkforward, voter quality, MFE/MAE
  terminal/        FastAPI routers + projections + Svelte web app (built to static/)
  observability/   Health, metrics
```

## Credentials & Dhan

- **Single primary** consent token (OAuth) serves trading REST + the feed WS (D8); stored Fernet-encrypted at `~/.shettyxtreme/credentials.enc` (machine-derived key).
- **Optional data fallback**: a separate `data_access_token` provisioned via PIN/TOTP (`generateAccessToken`) is used by the data adapter only if the feed rejects the consent token.
- **Dhan error 806 = Data-API entitlement**, not a credentials bug: surfaced as "subscribe to Data APIs" on the health strip, REST errors, and the feed guard — never papered over.
- DhanHQ-py pinned to 2.2.0; WS v2 subscription request codes 15/17/21 (Ticker/Quote/Full).

## Vendored components (AGPL, private use)

OpenAlgo execution plumbing is vendored into `vendor/openalgo/` (origin-stamped, AGPL-3.0) per D1/D2 — **private use only, never distributed**. `src/` never imports it (grep-gated); `scripts/sync_vendor.py` re-syncs from the upstream mirror with byte-idempotent output. Evidence and upstream facts: `docs/references/` (7 briefs).

## Testing

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=C:\Users\<you>\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider
```

**527 passed / 0 failed / 3 skipped.** (Windows note: always use `.venv\Scripts\python.exe` — the PATH `python` may be a different venv — and an explicit `--basetemp` to avoid a session-teardown PermissionError quirk.)

## Roadmap

| Phase | Status |
|---|---|
| 0 — References + vendoring | **DONE** |
| 1 — Blueprint v2 + DESIGN.md + ADRs | **DONE** |
| 2 — Usable MVP: pipeline completion + Svelte terminal | **DONE** |
| 3 — Advanced intelligence | **3A done** (session-gated shadow graduation, calibration→sizing, correlation caps, D/P/G live, walkforward breakdowns, `/api/learning/*`); **3B done** (DeepSeek briefer harness — OI/IV-flow, directional-momentum, tail-risk lenses → schema-validated briefs, human approve/reject, `/api/research/*`); **3C done** (read-only data tools w/ mid-run function calling, env-config scheduler, ResearchPanel + WS live updates, outcome scoring + decided_at) |
| 4 — Maturity (knowledge layer, analytics, optional multi-broker) | **4A/4B done (v1)** — D12 knowledge layer (FTS5 store + tagger + activation → `knowledge_search` tool), scorecard dashboards + recording track; multi-broker + backtest depth deferred |

Full detail: [`docs/architecture/v2/sections/17-delivery-roadmap.md`](docs/architecture/v2/sections/17-delivery-roadmap.md).

## License

Proprietary — All Rights Reserved © Rohan Shetty. Vendored OpenAlgo files under AGPL-3.0 (private use, see [`vendor/openalgo/README.md`](vendor/openalgo/README.md) and ADR-003).
