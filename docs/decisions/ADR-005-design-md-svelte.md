# ADR-005: DESIGN.md Contract + Svelte Terminal

## Status
Accepted (2026-08-01).

## Context
The terminal is the product's face. v1 used FastAPI + static HTML/JS (3 pages) with taste-skill (industrial-brutalist-ui) and ui-ux-pro-max-skill referenced but not codified. The Aug-01 brief names awesome-design-md (DESIGN.md files, MIT, Google Stitch format) as the most important new reference.

## Decision
1. A custom `DESIGN.md` (repo root, 9 Stitch sections, 24 KB) is THE design contract for all terminal UI work: dark data-dense workstation language, semantic tokens (incl. Indian red=up/green=down price convention), JetBrains Mono for numerals, one cyan accent, hairline elevation, kill-switch rules, agent prompt guide.
2. Terminal migrates to Svelte + Vite served by FastAPI (D9) — component reuse for the cockpit panels; DESIGN.md governs styling; no new chart-library dependency without need.
3. Every future UI change follows the DESIGN.md contract (compliance pass in Phase 2).

## Consequences
- Consistent, agent-reproducible UI; the contract prevents design drift as panels grow past 10.
- Svelte migration is a Phase-2 deliverable with a bounded scope; existing static pages are replaced, not stretched.
