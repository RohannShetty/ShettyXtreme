# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`docs/architecture/v2/ARCHITECTURE_V2.md`** at the repo root of the docs tree — the master blueprint with the binding decisions pack D1–D12.
- **`docs/decisions/ADR-*.md`** — read ADRs that touch the area you're about to work in (ADR-001..007).
- **`DESIGN.md`** — binding for all UI work.
- **`CLAUDE.md`** and **`.projectos/identity/frozen-rules.md`** — immutable constraints.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront.

## File structure

Single-context repo (most repos):

```
/
├── docs/architecture/v2/ARCHITECTURE_V2.md   ← master blueprint + D1–D12
├── docs/decisions/                           ← ADR-001..007
├── DESIGN.md                                 ← UI design contract
└── src/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in the blueprint and ADRs. Don't drift to synonyms the docs explicitly avoid (e.g. "shadow voter", "lens", "regime", "conviction D/P/G", "brief", "OBSERVER-first").

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-004 (research-layer AI) — but worth reopening because…_
