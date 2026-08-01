# Reference Repo Status

Status as of 2026-08-01. All clones are shallow (`--depth 1`); fincept-terminal additionally uses `--filter=blob:none` (large repo). Raw clones are gitignored under `references/` — durable knowledge lives in the BRIEF files in this directory.

## New references (added by the Aug-01 brief)

| Repo | Location | Commit | Notes |
|------|----------|--------|-------|
| awesome-design-md | references/awesome-design-md | 8147538 | DESIGN.md format source (Google Stitch spec); MIT |
| ai-hedge-fund | references/ai-hedge-fund | 6c41ae8 | Agentic hedge-fund reference (research-layer only decision) |
| anthropics/financial-services | references/anthropics-financial-services | eb0c1ea | Financial-services agentic patterns, human-in-the-loop controls |
| quant-developers-resources | references/quant-developers-resources | 2772004 | Curated resources checklist |

## Upstream mirrors (for diff review + vendoring)

| Repo | Location | Commit | Notes |
|------|----------|--------|-------|
| OpenAlgo (marketcalls) | references/upstream/openalgo | 3542a6e | **The only legal sync source for vendoring** (AGPL-3.0) |
| DhanHQ-py (dhan-oss) | references/upstream/dhanhq-py | 1670f81 | Latest upstream vs local D:\DhanHQ-py-2.2.0 under review |
| FinceptTerminal | references/upstream/fincept-terminal | 823f638 | AGPL — inspiration only, no code |
| ShettyBot V1 (RohannShetty) | references/upstream/shettybot-v1 | 92cff82 | Prior-version source of truth |
| FinceptTerminal fork (RohannShetty) | references/upstream/fincept-fork | 1511793 | Personal fork |

## Local working copies (NOT sync sources)

- **D:\OpenAlgo** — user's working copy (openalgoUI v2.0.1.4) **contaminated with personal strategy scripts** (live_dispatcher.py, voters.py, markov_regime.py, train_ml_ensemble*.py). Never used as a vendoring source.
- **D:\DhanHQ-py-2.2.0** — SDK under review (auth: single DhanContext; 806 = Data-API subscription entitlement).
- **D:\ShettyBot_V1_Core** + worktrees (accept_wave_a1, baseline_3e9e8de_diag2, ops_verify, sliceA, sliceD, worktree_infra_seam) — prior-version source; upstream mirror is authoritative for status.
