# 04 — Human-gated activation flow

Type: prototype
Status:
Blocked by: 02, 03

## Question

What is the human-gated activation flow for knowledge — search, review, and activate — and where does it live in the terminal?

Ground: section 12 stop-and-surface checkpoints + one-approval-card pattern, section 05 knowledge layer (human-gated activation), DESIGN.md, existing panel patterns (ResearchPanel / approval cards in research).

Sharpen: what "activation" means in v1 (make a tagged document searchable+digestible? promote an extracted tag to a live surface? link to research tools?), the approval card fields (doc excerpt, tags, provenance refs), API shape (`/api/knowledge/*`), WS events, and whether the review surface is a new panel or extends ResearchPanel. Prototype the review card UI first.

## Answer
Activation = operator approves a tagged doc -> it becomes a research tool source (knowledge_search tool via DataSource.knowledge_summary). UI: KnowledgePanel (search + review + activate card, ResearchPanel pattern).
