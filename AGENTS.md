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
