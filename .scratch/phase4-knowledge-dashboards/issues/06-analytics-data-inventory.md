# 06 — Analytics data plumbing inventory

Type: task
Status:
Blocked by:

## Question

What is actually queryable today for the scorecard-core metrics? Produce a data-source inventory.

Walk the codebase (read-only): which stores/endpoints expose sessions logged, per-session outcomes (net EV, cost), win rate by regime, calibration curve points + reliability. For each scorecard metric: source (module/table/endpoint), fields available, gaps (e.g. cost drag not captured anywhere), and whether a metric is computable with zero new plumbing.

Deliverable: inventory table appended to this ticket under `## Answer` with the gaps flagged — ticket 05 consumes it. Do not modify code.
