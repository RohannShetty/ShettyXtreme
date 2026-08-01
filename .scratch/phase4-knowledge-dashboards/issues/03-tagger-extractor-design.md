# 03 — Tagger / heuristic extractor v1 design

Type: grilling
Status:
Blocked by: 01

## Question

What does the heuristic extractor (symbols + regimes + risk themes) look like, given D12 (knowledge/ imports core ONLY, NO LLM inside knowledge/)?

Ground: existing symbol/regime vocabularies in `core/` and `intelligence/` (regime enum RANGE_BOUND/TRENDING_UP/etc.), RESEARCH briefs as input docs, design tokens, 0-skipped gate, ≤500 lines/file.

Sharpen: extraction dictionaries (curated NSE symbol list + regime terms + risk-theme lexicon — where do they live? core/?), matching rules (case-insensitive, NSE symbol disambiguation vs words like "IT"), what the tagger writes (tags on the doc record? separate link table?), how tags feed search/filtering, and the v1 accuracy bar (unit-tested lexicon, no ML).

## Answer
Tagger: core/ lexicons (NSE symbols + regime terms + risk themes; knowledge cannot import intelligence so vocabularies live in core); case-insensitive dict matching + symbol disambiguation; tags stored as (doc_id, tag, kind) table, FTS5-searchable, unit-tested.
