# 02 — Knowledge schema + auto-ingest contract

Type: grilling
Status:
Blocked by: 01

## Question

What is the v1 document schema for the knowledge store, and what is the auto-ingest contract from research outputs?

Ground: D12 (knowledge/ imports core ONLY), ResearchBrief fields (brief_id, lens, as_of, status, decided_at, outcome, evidence, thesis, rationale), append-only + provenance discipline (store.py patterns), 0-skipped gate.

Sharpen: which brief states auto-ingest (proposed only? decided only? all?), idempotency (re-ingest of the same brief_id), how evidence `[UNSOURCED]` flags carry provenance, what the doc record exposes to search vs the tagger, and whether the research store stays the source of truth (knowledge store = derived projection) or knowledge becomes the archive.
