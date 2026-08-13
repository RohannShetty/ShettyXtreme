# AGENTS.md — ShettyXtreme

India-first options intelligence workstation (FastAPI + Svelte 5, Python 3.11). The authoritative blueprints are [`docs/architecture/v2/ARCHITECTURE_V2.md`](docs/architecture/v2/ARCHITECTURE_V2.md) and [`DESIGN.md`](DESIGN.md) (binding for UI work). `CLAUDE.md` and `.projectos/identity/frozen-rules.md` hold the immutable constraints — read them before large changes.

## Commands

```powershell
# Tests — ALWAYS this exact form (verified):
#   - .venv\Scripts\python.exe: PATH `python` may be a different venv
#   - PYTHONPATH="": prevents stray site-packages being picked up
#   - --basetemp: avoids Windows session-teardown PermissionError quirk
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider

# Single test file / test:
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave7/test_credential_store.py -q --basetemp=... 

# Frontend (Svelte 5 + Vite, in src/shettyxtreme/terminal/web):
npm run dev      # vite on :3000, proxies /api + /ws to :8000
npm run check    # svelte-check type gate — 0 errors required before build
npm run build    # → src/shettyxtreme/terminal/static/ (COMMITTED bundle)

# Run the terminal:
.venv\Scripts\python.exe run.py --mode OBSERVER   # default; LIVE needs typed confirmation (D10)
```

## Test Gates (MANUAL — there is no CI in this repo)

Run after every change; the repo has no `.github/` so these are grep/wc/pytest checks, not automation:

1. Full suite passes (command above). Suite: **1012 passed / 0 failed / 0 skipped** (v0.12.0).
2. `grep -r "import openalgo\|from openalgo" src/` → ZERO matches (standalone rule)
3. No file > 1000 lines (god-module guard)
4. `core/` has zero external imports — **known violation**: `core/config/config_manager.py:10` imports `yaml` (pre-existing, slated for fix)

Tests live in `tests/wave1`–`wave8` (feature waves) plus per-module dirs (`core/`, `options/`, `execution/`, `terminal/`, `intelligence/`, `vendor/`). Match the closest existing location when adding tests.

## Architecture rules

- Layered modular monolith; import boundaries are law: `core/` → nothing external; `intelligence/` → core only; `integration/` → core/interfaces + external APIs; `knowledge/` → core only (must NOT import intelligence/ or execution/); `research/` is the only LLM-touching layer (D3 wall — `research/provider.py`).
- Modules communicate via the asyncio `EventBus` (`core/event_bus/`); no direct cross-layer module-to-module calls.
- Integration contracts are `typing.Protocol`s in `core/interfaces/`; adapters implement them (`integration/dhan/`).
- Execution is OBSERVER-first (D10): platform proposes, human approves. OBSERVER is the default mode; `--mode LIVE` requires typed confirmation and never auto-restores.
- `vendor/openalgo/` is AGPL-3.0 vendored plumbing for **private use only, never distributed**; `src/` must never import it (`scripts/sync_vendor.py` re-syncs, byte-idempotent).

## Docs conventions

- Binding: `docs/architecture/v2/ARCHITECTURE_V2.md` (master + 20 sections, decisions D1–D12, ADRs), `DESIGN.md` (UI design contract).
- **DESIGN.md is binding for all UI work**: near-black canvas, one accent, configurable price convention — **international default (green = up `#2ebd85`, red = down `#f6525c`)**, Indian legacy opt-in (red = up, green = down). Toggle in Settings. Numerals in JetBrains Mono tabular, labels in Inter.
- Feature work follows the superpowers convention: spec → plan → handoff in `docs/superpowers/{specs,plans,handoffs}/` (dated `YYYY-MM-DD-<topic>.md`). Check for existing specs/plans before starting work.
- **Tiny-fix exemption**: single-file fixes with no API/schema/behavior change and a small diff (< ~30 lines) skip the spec/plan/handoff ritual — fix, run the test suite, report. Docs stay mandatory for features, refactors, and multi-file work.
- `CHANGELOG.md` is maintained per release with suite counts.

## Version & release

Version is drifted across files — update ALL of these on a bump:
`src/shettyxtreme/__init__.py` (currently stale at 0.6.0), `src/shettyxtreme/terminal/api/app.py` (0.7.0), `pyproject.toml` (0.7.0), `CHANGELOG.md` (head: 0.8.0), frontend `package.json` (0.6.0).

## Credentials & Dhan

- Single primary consent token (OAuth) serves trading REST + feed WS (D8), Fernet-encrypted at `~/.shettyxtreme/credentials.enc` (machine-derived key). Setup wizard: `#/setup`.
- Dhan error **806 = Data-API entitlement**, not a credentials bug — surface it, never paper it over.
- `DEEPSEEK_API_KEY` (research briefers): env-only, read at call time, never logged. `/api/research/*` returns 503 without it.
- `configs/default.yaml` still carries legacy keys (`data_provider: openalgo`, `openalgo_base_url`) — vestigial, don't rely on them.

## Tooling & skills to use

- **graphify** (plugin, `.opencode/plugins/graphify.js`) — see full workflow below. After modifying code, run `graphify update .` to keep the graph current (AST-only, free).
- **codegraph** (MCP): `.codegraph/` index exists — call `codegraph_explore` before editing to see a symbol's source + blast radius instead of grep/read loops.
- **UI work**: use the repo-local `.skills/` skills (design-taste-frontend, ui-ux-pro-max, industrial-brutalist-ui, design-system, ui-styling) with DESIGN.md as the contract.
- **O2B memory**: project decisions live in the Obsidian Brain vaults — query before repeating past decisions.

## Gotchas

- `server.log` / `server.err` at repo root are runtime artifacts (gitignored); check `server.err` when diagnosing crashes.
- `.opencode/`, `.codegraph/`, `graphify-out/`, `data/`, `references/`, `.skills/` are gitignored — generated/index state, not source.
- `scripts/research_smoke.py` is env-gated manual DeepSeek run (exit 2 without key) — never called from tests.
- Windows: use `.venv\Scripts\python.exe` everywhere; `--basetemp` on pytest to avoid teardown PermissionError.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Graphify Impact Workflow

Use this when assessing the blast radius of a change before/after editing code. All commands are LLM-free and read-only except save-result/reflect (writes under graphify-out/, git-ignored).

```bash
# Who is impacted by a symbol? (reverse traversal, depth 2)
graphify affected "DhanTradingAdapter" --depth 2

# Ask a question over the graph; add --dfs for depth-first traversal
graphify query "Dhan adapter to execution" --dfs

# Shortest path between two nodes (use exact symbol names to avoid ambiguity)
graphify path "DhanTradingAdapter" "DhanDataAdapter"

# Plain-language explanation of a node and its neighbors
graphify explain "DhanClient"

# Architectural hubs
graphify god-nodes --top 10
```

Record useful answers so future sessions learn:

```bash
# Save a Q&A result to graphify-out/memory/ (feedback loop)
graphify save-result --question "how does DhanTradingAdapter reach EventBus" \
  --answer "Path: DhanTradingAdapter <-imports- app.py -imports-> DhanDataAdapter" \
  --type query --nodes DhanTradingAdapter app.py DhanDataAdapter --outcome useful

# Aggregate memory outcomes into a lessons doc (deterministic, no LLM)
graphify reflect
```

Notes: `graphify path` may warn "match was ambiguous" — prefer full symbol names. `graphify tree` writes `graphify-out/GRAPH_TREE.html` (D3 collapsible tree), `graphify export svg` writes `graphify-out/graph.svg`. Task 4/5 (LLM semantic extraction) is skipped: this build's `--backend openai` requires a non-empty API key, so it cannot use the auth-free local proxy or Zen endpoint.
