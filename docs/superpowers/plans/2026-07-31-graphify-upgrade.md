# Plan: Graphify Upgrade for ShettyXtreme

Date: 2026-07-31
Status: Approved — subagent-driven execution on `master`
Graph: 2423 nodes / 4601 edges / 152 communities / 87% EXTRACTED / 13% INFERRED / 0 tokens spent (fresh, matches HEAD `7c4db2b`)

## Confirmed Decisions (user)
- **Branch:** `master` (repo convention; all history commits straight to master).
- **`graphify-out/` stays git-ignored.** Graph artifacts are regenerable and served from disk. Commit steps in this plan that reference graphify-out artifacts are **adjusted to no-op / skip** — commits only ever include non-ignored files (AGENTS.md, docs, changelog). A `git add -A` inside a task MUST NOT stage graphify-out.

## Constraint Notes
- Full plan is 10 tasks. Tasks 1-7 are in-order sequential (each depends on prior state). Tasks 8-9 are optional standalone. Task 10 is the final gate.
- CI gate: `PYTHONPATH="" python -m pytest tests/ -v --tb=short` ALL PASS must hold at Task 10 (and must not be broken by anything before).
- Never modify `src/` or `tests/` in this plan — it is tooling/config only.

---

## Task 1 — Baseline snapshot & incremental-update sanity check
**DEPENDS ON:** nothing (except current graph).
**MODIFIES:** nothing (sanity + backup only).
**VERIFY:** `graphify update .` output shows an up-to-date/incremental pass with no errors; `graphify diagnose multigraph` returns no multigraph problems; backup file exists.
**COMMIT:** none (backup lives inside ignored `graphify-out/`).

1. Copy `graphify-out/graph.json` -> `graphify-out/.graphify_baseline.json` (safe fallback).
2. Run `graphify update .` — expect incremental, matches HEAD, no errors.
3. Run `graphify diagnose multigraph` — expect no multigraph issues.
4. Verify `graphify-out/.graphify_baseline.json` exists and is non-empty.
5. Record graph stats (nodes/edges/communities) in the task report.
6. NO COMMIT (graphify-out is ignored).

## Task 2 — OpenCode-native integration (AGENTS.md + plugin)
**DEPENDS ON:** Task 1.
**MODIFIES:** `AGENTS.md` (new, tracked), opencode plugin dir `C:\Users\rohan\.config\opencode\plugins\` (untracked).
**VERIFY:** AGENTS.md contains graphify section; plugin file exists in plugins dir.
**COMMIT:** AGENTS.md only (git add AGENTS.md; do NOT `git add -A`).

1. Run `graphify opencode install` (writes AGENTS.md section + opencode plugin with tool.execute.before hook).
2. Show/confirm the generated AGENTS.md section and plugin.
3. Commit: `git add AGENTS.md` then commit `docs: add graphify AGENTS.md integration via graphify opencode install`.

## Task 3 — Freshness automation (post-commit hook)
**DEPENDS ON:** Task 2.
**MODIFIES:** `.git/hooks/post-commit` (untracked by git).
**VERIFY:** `graphify hook status` shows the post-commit hook installed; a trivial commit triggers the hook (log line appears) without breaking.
**COMMIT:** the test commit itself (a no-op-ish commit that proves the hook fires).

1. Run `graphify hook install`.
2. Run `graphify hook status` — confirm post-commit hook present.
3. Inspect `.git/hooks/post-commit` to confirm it calls the right interpreter and `graphify update`.
4. Functional test: make one trivial tracked change (e.g. append a blank line to a harmless doc) and commit it; confirm the hook ran (check graphify log or updated-at stamp) and did NOT error.
5. Commit message: `chore: test graphify post-commit hook freshness automation`.

## Task 4 — Semantic extraction (LLM-enriched graph) — **SKIPPED (blocked on auth, low value)**
**DEPENDS ON:** Task 3.
**STATUS:** Attempted via opencode Zen; **skipped after verified blocker** — the `openai` backend of graphify requires `OPENAI_API_KEY` to be non-empty (cli.py gate), but the Zen endpoint accepts only an empty/no `Authorization` header (401 `AuthError` on any real key, whitespace keys rejected at the HTTP layer as illegal header values). The headroom proxy (`127.0.0.1:8787`) is not an LLM provider (401). The AST-only graph already satisfies the project's needs (labels, INFERRED edges, query tools, hook, MCP), so the marginal gain (conceptual names, cost.json demo) does not justify it.
**COMMIT:** none (ignored artifacts).

NOTE: While attempting this, the graphifyy uv-tool venv was repaired — `uv tool install "graphifyy[openai]" --force` (openai extra added, both executables restored). Verified: CLI works, hook interpreter imports graphify + openai, graph intact (2438/4615), hooks installed. This repair is required infrastructure, not a plan deviation.

## Task 5 — Community labeling (LLM) + cluster-only — **SKIPPED (same blocker as Task 4)**
**DEPENDS ON:** Task 4 (enriched graph) — not available.
**STATUS:** Skipped with Task 4. Deterministic labels (`.graphify_labels.json`) already present and human-readable. `--cluster-only` remains a valid no-LLM fallback if labels ever need regeneration.
**COMMIT:** none (ignored).

## Task 6 — Exports & artifacts
**DEPENDS ON:** Task 3 (Task 4/5 skipped — exports run fine on the AST-only graph).
**MODIFIES:** `graphify-out/` wiki + exports (ignored).
**VERIFY:** each artifact exists and is non-trivial (sizes listed in report); wiki/ contains per-community .md files; svg/callflow html render paths resolve.
**COMMIT:** none (ignored).

1. `graphify export wiki --out graphify-out/wiki`
2. `graphify tree` (graphify-out/tree.txt) + `graphify export callflow-html`
3. `graphify export svg`
4. `graphify benchmark` — record metric (node/edge recall/accuracy).
5. NO COMMIT.

## Task 7 — Impact-analysis workflow
**DEPENDS ON:** Task 3 (hook live).
**MODIFIES:** AGENTS.md (append workflow section), `graphify-out/` memory + reflections (ignored).
**VERIFY:** AGENTS.md workflow section present; `graphify affected`/`query --dfs`/`path`/`explain` output sensible on a real example; reflection file exists.
**COMMIT:** AGENTS.md only (do NOT `git add -A`).

1. Build the workflow: `graphify affected --base <BASE_SHA>` (use `git rev-parse HEAD~1` as an example base), `graphify query "Dhan adapter to execution" --dfs`, `graphify path` on a real symbol pair, `graphify explain`.
2. `graphify save-result` to record one real analysis; `graphify reflect` to write a reflection.
3. Append a "Graphify Impact Workflow" section to AGENTS.md documenting the exact commands.
4. Commit AGENTS.md: `docs: document graphify impact-analysis workflow`.

## Task 8 (OPTIONAL) — Global cross-repo graph
**DEPENDS ON:** Task 7.
**MODIFIES:** `~/.graphify/global-graph.json` (outside repo).
**VERIFY:** `graphify global list`/`status` shows shettyxtreme registered.
**COMMIT:** none.

1. `graphify global add . --as shettyxtreme --comment "ShettyXtreme trading OS"`
2. Verify registration + stats.
3. NO COMMIT.

## Task 9 (OPTIONAL) — HTTP MCP server
**DEPENDS ON:** Task 2 (MCP config awareness).
**MODIFIES:** `C:\Users\rohan\.config\opencode\opencode.jsonc` (add graphify-http remote entry).
**VERIFY:** server starts on :8080 and an MCP `initialize` handshake succeeds.
**COMMIT:** none (config outside repo).
**IMPORTANT:** start server, confirm handshake, then **stop it** so it does not linger.

1. Start `graphify serve --transport http --port 8080 --api-key <dev-key>` in background.
2. Test handshake (curl POST `/mcp` with initialize).
3. Optionally add `graphify-http` entry to opencode.jsonc (mark disabled/by-hand if user prefers manual start).
4. Stop the server; confirm port freed.

## Task 10 — Final verification gate
**DEPENDS ON:** all prior tasks.
**MODIFIES:** `CHANGELOG.md` (or docs/changelog if that's the convention — check first).
**VERIFY:** ALL of: (a) `graphify hook status` shows post-commit installed; (b) `graphify mcp stats`/diagnose healthy; (c) graph stats recorded; (d) `PYTHONPATH="" python -m pytest tests/ -v --tb=short` ALL PASS; (e) `grep -r "import openalgo\|from openalgo" src/` zero matches; (f) no file > 500 lines.
**COMMIT:** changelog + any AGENTS.md remainder.

1. Re-run all verification commands; capture full output in report.
2. Append a changelog entry for the graphify upgrade.
3. Commit: `docs: changelog for graphify upgrade (tasks 1-9)`.

---

## Out of scope (future)
- Any changes to `src/`, `tests/`, or runtime behavior.
- Committing graphify-out artifacts (decision above).
