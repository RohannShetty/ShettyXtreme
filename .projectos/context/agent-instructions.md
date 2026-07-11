# Agent Instructions for ShettyXtreme

## Before Acting

1. Read `.projectos/identity/project.md` — What is ShettyXtreme?
2. Read `.projectos/identity/frozen-rules.md` — Rules that must never be violated.
3. Read `.projectos/governance/boundaries.json` — Architectural boundaries.
4. Read `CLAUDE.md` — Project context for AI agents.

## Key Constraints

- **Do NOT** import OpenAlgo, dhanhq, or other external packages in core/ code.
- **Do NOT** fork or embed external repos — use as dependencies.
- **Do NOT** propose reimplementing features OpenAlgo already handles.
- **DO** use anti-corruption layers at all integration boundaries.
- **DO** write tests for integration contracts.
- **DO** record ADRs for significant architectural decisions.
