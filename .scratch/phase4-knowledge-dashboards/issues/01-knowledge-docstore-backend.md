# 01 — Knowledge doc-store backend choice

Type: research
Status: claimed
Blocked by:

## Question

Which backend should the D12 knowledge-layer document store use, given: small single-operator corpus (hundreds to low thousands of documents), auto-ingested research briefs (JSON payloads with provenance fields), full-text search + tag/regime filtering + provenance joins, Python 3.11 / stdlib + pydantic, and a strong preference for zero new runtime dependencies (existing: sqlite3, httpx, pydantic)?

Evaluate honestly: **sqlite3 + FTS5** (stdlib, no new dep) vs alternatives (SQLite FTS5 with trigram/porter, duckdb, tantivy, whoosh, plain jsonl + in-memory index). For each: search capability (phrase match, prefix, stemming), tag/metadata filtering, provenance integrity (append-only records, referential links to brief_id), concurrent-access story, deployment weight, and testability. Recommend ONE option with the decision criteria explicit.

Deliverable: findings markdown at `docs/references/BRIEF-knowledge-docstore.md` (or `docs/knowledge/` if created), linked from this ticket.
