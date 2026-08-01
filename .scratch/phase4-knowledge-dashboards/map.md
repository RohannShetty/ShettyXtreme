# Phase 4 — Knowledge Layer (D12) + Analytics Dashboards

> Wayfinder map. Child tickets live in `issues/` (numbered, one question each, `Type:` + `Status:` + `Blocked by:` lines). Frontier = open + unblocked + unclaimed; first by number wins.

## Destination

The Phase 4 maturity destination, split into two parallel tracks:

1. **Knowledge flow end-to-end** (D12): a document store + tagger + heuristic extractor, physically separated from intelligence (`knowledge/` imports core ONLY), auto-ingesting research outputs (briefs + decisions), with a human-gated activation flow.
2. **Analytics dashboards**: scorecard-core metrics (sessions logged, net EV per session, win rate by regime, calibration curve) rendered in the existing Svelte terminal with **zero new charting deps** (DESIGN.md tokens).

Multi-broker and backtest depth are decided by tickets as they surface; the destination is reached when both tracks' decisions are locked and the way to implement them is clear.

## Notes

- Domain: India-first options workstation (NSE/BSE, Dhan). Binding: D1–D12, DESIGN.md, ADR-001..007, CLAUDE.md, frozen rules.
- D3/D12 walls: `knowledge/` imports core ONLY, physically separated; NO LLM inside knowledge/ — extractor is heuristic; LLM surface stays `research/provider.py`.
- Skills every session: brainstorming before any new surface, writing-plans, subagent-driven development with TDD on every task, code-review (code-reviewer subagent), wayfinder (this map), verification gates.
- Standing preferences: suite never shrinks / 0 skipped; ≤500 lines/file; grep gate zero; test runner `.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=... -p no:cacheprovider` with `PYTHONPATH=""`; distinct basetemps for parallel agents; subagents never commit (coordinator does); never stage `AGENTS.md` / `.opencode/opencode.json` / `docs/superpowers/plans/2026-07-31-graphify-upgrade.md`.
- Research outputs auto-ingest: ResearchBrief already carries brief_id/lens/as_of/status/decided_at/outcome/evidence — the ingest contract reuses these.

## Decisions so far

- (2026-08-01 chart) Destination named: knowledge layer + dashboards, two parallel tracks; multi-broker + backtest depth decided by tickets.
- (2026-08-01 chart) v1 ingest surface: **auto-ingest research outputs only** (no operator-notes folder in v1).
- (2026-08-01 chart) v1 extractor scope: **symbols + regimes + risk themes**, heuristic only.
- (2026-08-01 chart) v1 dashboards: **scorecard core** (sessions logged, net EV/session, win rate by regime, calibration curve), **zero-new-deps** Svelte rendering.

## Not yet specified

- Backtest-depth detail (what "beyond Phase-3 walkforward" concretely means; strategy-comparison surface shape) — ticket 08 graduates this.
- Multi-broker specifics (which broker, what protocol gaps) — ticket 07 graduates this.
- Knowledge activation UI surface (search + review + activate placement in the terminal; approval-card shape) — ticket 04 graduates this.
- Dashboards data plumbing (which endpoints/stores today can feed each scorecard metric; gaps like cost-drag data) — ticket 06 graduates this.

## Out of scope

- SaaS, multi-tenancy, external users (D2/D11 — never).
- Critic model pass (deferred until order intents exist to gate).
- Live `/optionchain` fixture (separate open question; needs live Dhan credentials).
- The never-stage dirty files listed in Notes.
