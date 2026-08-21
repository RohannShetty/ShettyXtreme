# Phase 5: Research & Knowledge Panel Enhancements

**Date:** 2026-08-21  
**Status:** Planning  
**Branch:** `master` (post-PR #1 merge)  
**Baseline:** v0.16.0, 1823 tests passing

---

## Executive Summary

Phase 5 delivers three major enhancements to the Research & Knowledge panels:
1. **Export to PDF/Markdown** — both research briefs and knowledge docs
2. **Knowledge graph visualization** — D3 force-directed graph of tag relationships
3. **Related concepts linking** — discover and navigate related documents

**Current State:**
- Research panel: functional (lens/tool toggles, brief generation, approve/reject, WS updates)
- Knowledge panel: functional (FTS5 search, sync from briefs, activate, notes)
- Missing: export, graph viz, related concepts

**Target State:**
- Export buttons in both detail panes (MD/PDF)
- Interactive knowledge graph (D3 force layout, zoom/pan, click-to-search)
- Related docs section in knowledge detail (shared tags, BM25 neighbors)

---

## Implementation Strategy

### Wave 1: Export Infrastructure (Parallel)
- **S1:** Research Export (backend + frontend + tests)
- **S2:** Knowledge Export (reuse S1 renderer pattern)

### Wave 2: Graph Data API (Sequential after Wave 1)
- **S3:** Graph Data API (store queries + routers + tests)

### Wave 3: Graph UI (Sequential after Wave 2)
- **S4:** Graph UI (D3 component + wiring)

### Wave 4: Polish & Integration (Sequential after Wave 3)
- **S5:** Polish/E2E (keyboard, STALE, WS, DESIGN.md compliance)

---

## Detailed Task Specifications

### S1: Research Export

**Backend:**
- File: `src/shettyxtreme/terminal/api/research_router.py` (extend)
- Endpoint: `GET /api/research/briefs/{id}/export?format=md|pdf`
- Renderer: Pure Python markdown generator (no external deps)
  - Markdown: thesis, rationale, evidence table, risks, meta
  - PDF: convert markdown → PDF via `markdown` + `weasyprint` (or `fpdf2` if weasyprint unavailable)
- Response: `Content-Disposition: attachment; filename="brief-{id}.md|pdf"`
- Error handling: 404 if brief not found, 400 if format unsupported

**Frontend:**
- File: `src/shettyxtreme/terminal/web/src/components/ResearchBriefDetail.svelte`
- Add export button (Dropdown: Markdown | PDF)
- File: `src/shettyxtreme/terminal/web/src/lib/api.ts`
- Helper: `exportResearchBrief(id: string, format: 'md' | 'pdf'): Promise<Blob>`
- Pattern: copy `exportAnalytics` (fetchWithTimeout → blob → File)

**Tests:**
- File: `tests/terminal/test_research_export.py`
- Test markdown output (thesis, rationale, evidence, risks present)
- Test PDF output (non-empty, valid PDF header)
- Test 404 for unknown brief
- Test 400 for unsupported format

**Quality Gates:**
- `grep -r "import openalgo" src/` → 0 matches
- `research_router.py` < 1000 lines
- DESIGN.md tokens used (no hardcoded colors)
- All tests pass

---

### S2: Knowledge Export

**Backend:**
- File: `src/shettyxtreme/terminal/api/knowledge_router.py` (extend)
- Endpoint: `GET /api/knowledge/docs/{id}/export?format=md|pdf`
- Renderer: Reuse S1 markdown pattern
  - Markdown: title, body, tags, evidence, meta (status, kind, source_ref, activated_at)
  - PDF: same conversion
- Response: `Content-Disposition: attachment; filename="doc-{id}.md|pdf"`

**Frontend:**
- File: `src/shettyxtreme/terminal/web/src/components/knowledge/KnowledgeDetail.svelte`
- Add export button (Dropdown: Markdown | PDF)
- File: `src/shettyxtreme/terminal/web/src/lib/api.ts`
- Helper: `exportKnowledgeDoc(id: string, format: 'md' | 'pdf'): Promise<Blob>`

**Tests:**
- File: `tests/terminal/test_knowledge_export.py`
- Test markdown output (title, body, tags, evidence present)
- Test PDF output (non-empty, valid PDF header)
- Test 404 for unknown doc
- Test 400 for unsupported format

**Quality Gates:**
- Same as S1
- `knowledge/` does NOT import `research/` (D12)

---

### S3: Graph Data API

**Backend:**
- File: `src/shettyxtreme/knowledge/store.py` (extend)
- Method: `related(doc_id: str, limit: int = 5) -> list[dict]`
  - Query: find docs sharing ≥1 tag with doc_id
  - Rank by: shared_tag_count DESC, bm25_score DESC
  - Exclude: self
  - Return: `[{doc_id, title, shared_tags: [tag], score}]`
- Method: `graph(kind: str | None = None, limit: int = 100) -> dict`
  - Nodes: `SELECT tag, kind, count(*) as count FROM tags GROUP BY tag, kind`
  - Edges: implied via doc co-occurrence (two tags connected if they appear in same doc)
  - Return: `{nodes: [{id, label, kind, count}], edges: [{source, target, weight}]}`

- File: `src/shettyxtreme/terminal/api/knowledge_router.py` (extend)
- Endpoint: `GET /api/knowledge/docs/{id}/related?limit=5`
- Endpoint: `GET /api/knowledge/graph?kind=symbol|regime|risk&limit=100`

**Tests:**
- File: `tests/knowledge/test_graph_api.py`
- Test related docs (shared tags, ranking, exclude self)
- Test graph nodes (aggregation, kind filter)
- Test graph edges (co-occurrence, weight)
- Test empty graph (no docs)

**Quality Gates:**
- Same as S1
- `knowledge/` does NOT import `research/` or `terminal/` (D12)
- SQL queries use parameterized inputs (no injection)

---

### S4: Graph UI

**Frontend:**
- File: `src/shettyxtreme/terminal/web/src/components/knowledge/KnowledgeGraph.svelte` (new)
- Library: D3 v7 (force-directed graph)
- Features:
  - Nodes: circles sized by count, colored by kind (symbol=accent, regime=warning, risk=danger)
  - Edges: lines with opacity by weight
  - Zoom/pan: d3.zoom()
  - Tooltip: tag label + count on hover
  - Click tag: set search query + trigger search()
  - Click doc: select in knowledge panel
- Data: fetch from `/api/knowledge/graph` + `/api/knowledge/docs/{id}/related`

- File: `src/shettyxtreme/terminal/web/src/components/KnowledgePanel.svelte` (extend)
- Add "Graph" tab (Tabs: All | Strategies | Patterns | Notes | Graph)
- Mount KnowledgeGraph component in Graph tab
- Pass search query setter for click-to-search

- File: `src/shettyxtreme/terminal/web/src/lib/api.ts` (extend)
- Types: `GraphNode`, `GraphEdge`, `GraphResponse`, `RelatedDoc`
- Helpers: `getKnowledgeGraph(kind?, limit?)`, `getRelatedDocs(id, limit?)`

**Tests:**
- File: `src/shettyxtreme/terminal/web/src/components/knowledge/KnowledgeGraph.test.ts`
- Test graph renders (nodes, edges present)
- Test click tag triggers search
- Test zoom/pan (basic smoke test)

**Quality Gates:**
- `npm run check` → 0 errors
- `npm run build` → success
- DESIGN.md tokens used (no hardcoded colors)
- D3 imported from CDN or bundled (no global script tag)
- Responsive (works in narrow right dock)

---

### S5: Polish & Integration

**Frontend:**
- Keyboard navigation:
  - Graph tab: Tab to focus, Arrow keys to navigate nodes, Enter to select
  - Export buttons: keyboard accessible (Enter/Space to open dropdown)
- STALE handling:
  - Export button disabled if brief/doc is STALE (>1h old)
  - Tooltip: "Cannot export stale documents"
- WS updates:
  - Graph refreshes on `knowledge:activated` (new doc may add edges)
  - Related docs refresh on `knowledge:activated`
- DESIGN.md compliance:
  - All colors from design tokens (--accent, --warning, --danger)
  - Typography: Inter for labels, JetBrains Mono for numerals
  - Spacing: 8px grid, 16px gutters
  - Borders: hairline (1px var(--hairline))

**Tests:**
- Manual E2E:
  - Export research brief (MD + PDF) → opens correctly
  - Export knowledge doc (MD + PDF) → opens correctly
  - Graph renders with nodes/edges
  - Click tag → search populates
  - Related docs show in knowledge detail
  - Keyboard nav works (Tab, Arrow, Enter)
  - STALE docs cannot be exported

**Quality Gates:**
- All previous gates
- No console errors
- No accessibility violations (axe-core scan)
- Performance: graph renders <2s for 100 nodes

---

## Execution Order

```
Wave 1 (Parallel):
  S1: Research Export ──┐
  S2: Knowledge Export ─┴─→ Wave 2

Wave 2 (Sequential):
  S3: Graph Data API ──→ Wave 3

Wave 3 (Sequential):
  S4: Graph UI ──→ Wave 4

Wave 4 (Sequential):
  S5: Polish & Integration ──→ Phase 5 Complete
```

**Estimated effort:** 5-7 days (1 day per subagent + integration)

---

## Risk Mitigation

### PDF Generation
**Risk:** weasyprint may not be available on Windows  
**Mitigation:** Fallback to fpdf2 (pure Python, cross-platform)

### D3 Bundle Size
**Risk:** D3 v7 is ~90KB gzipped  
**Mitigation:** Import only d3-force + d3-selection + d3-zoom (not full D3)

### Graph Performance
**Risk:** Large graphs (>500 nodes) may lag  
**Mitigation:** Limit to 100 nodes by default, add "Load More" button

### Export File Size
**Risk:** PDF export may be slow for large briefs  
**Mitigation:** Stream PDF generation, show progress indicator

---

## Success Criteria

- ✅ Research briefs exportable to MD/PDF
- ✅ Knowledge docs exportable to MD/PDF
- ✅ Knowledge graph visualizes tag relationships
- ✅ Related docs discoverable via shared tags
- ✅ All tests pass (1823 + new tests)
- ✅ DESIGN.md compliance verified
- ✅ No accessibility violations
- ✅ Performance <2s for graph render

---

## Next Steps

1. Dispatch S1 (Research Export) + S2 (Knowledge Export) in parallel
2. Wait for Wave 1 completion
3. Dispatch S3 (Graph Data API)
4. Wait for Wave 2 completion
5. Dispatch S4 (Graph UI)
6. Wait for Wave 3 completion
7. Dispatch S5 (Polish & Integration)
8. Final verification + Phase 5 handoff

---

## Appendix: Current File Locations

**Research:**
- UI: `src/shettyxtreme/terminal/web/src/components/ResearchPanel.svelte` (682L)
- Detail: `src/shettyxtreme/terminal/web/src/components/ResearchBriefDetail.svelte` (142L)
- Backend: `src/shettyxtreme/terminal/api/research_router.py`
- Store: `src/shettyxtreme/research/store.py`
- Models: `src/shettyxtreme/research/briefs.py`

**Knowledge:**
- UI: `src/shettyxtreme/terminal/web/src/components/KnowledgePanel.svelte` (683L)
- Detail: `src/shettyxtreme/terminal/web/src/components/knowledge/KnowledgeDetail.svelte` (146L)
- Backend: `src/shettyxtreme/terminal/api/knowledge_router.py`
- Store: `src/shettyxtreme/knowledge/store.py`
- Models: `src/shettyxtreme/knowledge/schemas.py`

**Shared:**
- API client: `src/shettyxtreme/terminal/web/src/lib/api.ts`
- Design tokens: `src/shettyxtreme/terminal/web/src/lib/design.css`
- WS manager: `src/shettyxtreme/terminal/ws_manager.py`
