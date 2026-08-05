# ShettyXtreme — non-negotiable project rules

You are operating in the ShettyXtreme repository (India-first options intelligence workstation, FastAPI + Svelte 5). These rules are binding and override generic defaults. The authoritative blueprints are `docs/architecture/v2/ARCHITECTURE_V2.md` and `DESIGN.md`; read them before large changes. `AGENTS.md` and `.projectos/identity/frozen-rules.md` hold immutable constraints.

## Verification gates (manual — there is no CI)

Every task that touches code must end with the project's test command, EXACTLY as written:

```
$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider
```

- Full suite must pass: 1012 passed / 0 failed / 0 skipped.
- Use `.venv\Scripts\python.exe` everywhere (PATH `python` may be a different venv) and `--basetemp` on pytest (Windows teardown PermissionError quirk).
- Frontend: `npm run check` (svelte-check, 0 errors) before `npm run build`.
- NEVER assume a test framework or script — verify against the repo's actual commands.

## Hard constraints

- `grep -r "import openalgo\|from openalgo" src/` must return ZERO matches — `src/` must never import the vendored AGPL `vendor/openalgo/`.
- No file may exceed 500 lines. Known violations exist (`integration/dhan/trading_adapter.py`, `integration/dhan/data_adapter.py`, `terminal/api/app.py`) — never introduce new ones.
- `core/` has zero external imports.
- Layered architecture is law: `core/` → nothing external; `intelligence/` → core only; `integration/` → core/interfaces + external APIs; `knowledge/` → core only (never intelligence/ or execution/); `research/` is the only LLM-touching layer. Modules communicate via the asyncio `EventBus` (`core/event_bus/`); no direct cross-layer module-to-module calls. Integration contracts are `typing.Protocol`s in `core/interfaces/`.
- Execution is OBSERVER-first: platform proposes, human approves. OBSERVER is the default; `--mode LIVE` requires typed confirmation and never auto-restores. Never bypass this.

## UI design contract (DESIGN.md is binding)

- Near-black canvas, ONE accent.
- Indian price convention: **red = up `#f6525c`, green = down `#2ebd85`** — never "fix" this.
- Numerals in JetBrains Mono (tabular), labels in Inter.

## Credentials & Dhan

- Dhan error 806 = Data-API entitlement, NOT a credentials bug — surface it, never paper it over.
- `DEEPSEEK_API_KEY` is env-only, read at call time, never logged; `/api/research/*` returns 503 without it.

## Working conventions

- Do not commit unless explicitly asked.
- After modifying code, keep the knowledge graph current: `graphify update .` (AST-only).
- Feature work follows spec → plan → handoff in `docs/superpowers/{specs,plans,handoffs}/` (dated `YYYY-MM-DD-<topic>.md`).

## Graph-first policy (token discipline)

For ANY question about codebase structure, dependencies, or "how does X work":
- PREFER graph tools first: `graphify query "<question>"`, `graphify path "<A>" "<B>"`, `graphify explain "<symbol>"`, and `codegraph_explore` (verbatim symbol source + callers + blast radius in one call).
- Direct tools (grep/glob/read) are allowed for quick TARGETED lookups — e.g. you already know the exact symbol or token name. Do not read files one-by-one for discovery when a graph call answers it.
- Full file reads are for CONTENT the graph can't provide, not for finding things.

## Durable artifacts (background specialists)

- EVERY background specialist task MUST end with its complete output written to a file: `docs/superpowers/plans/YYYY-MM-DD-<topic>-findings.md` (or the mission's designated artifact path).
- The orchestrator reads the FILE for full content — never trust a truncated task notification.
- If a specialist's result was truncated in the notification and no file exists: re-dispatch ONE focused follow-up asking it to write the file. If still unusable, mark the task blocked and move on — do NOT keep retrying.

## Result recovery & headroom discipline

- NEVER call `headroom_retrieve` with a session ID, task ID, or filename — it accepts ONLY hashes returned by `headroom_compress` in THIS session. Wrong hash → "Content not found" → do not retry with other IDs; compress again if needed.
- NEVER search `~/.opencode/sessions` or similar filesystem locations for task results — results live in the durable artifact files, not there.
- If a background result is truncated: read the durable file (rule above) or re-dispatch once. Stop after one retry.

## Brevity

- User-facing updates: max ~5 bullets or ~150 words. Internal reasoning: keep lean; do not narrate every tool call.
- Full detail goes into the durable artifact files, not the chat.

## Session rituals

- Session start: run `graphify update .` before substantive work (unless just resumed mid-task).
- Session close / checkpoint: run `graphify update .` and confirm all outstanding specialist reports are on disk.

## Model fallback (insurance)

- If a model call fails with a usage-limit or service error, retry the same call on the next available model in this chain: primary → `opencode-go/hy3` → `opencode-go/deepseek-v4-flash`. Surface it in your update if a fallback was used.
