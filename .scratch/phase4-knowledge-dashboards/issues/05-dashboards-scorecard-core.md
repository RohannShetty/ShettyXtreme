# 05 — Dashboards scorecard-core design

Type: grilling
Status:
Blocked by: 06

## Question

What is the scorecard-core dashboards design — metrics, data sources, and zero-new-deps chart rendering?

Ground: section 16 scorecard (sessions logged, net EV per session cost-aware, win rate by regime, calibration error), section 14 walkforward honesty, existing endpoints (`/api/learning/calibration`, `/api/learning/shadows`, walkforward report), DESIGN.md (JetBrains Mono tabular numerals, one accent, red-up/green-down), ResearchPanel chart-free pattern.

Sharpen: which of the four metrics are computable TODAY from existing endpoints/stores vs need new plumbing (ticket 06's inventory decides), how net-EV-per-session is aggregated (rolling window semantics), chart primitives needed (line/bar/heatmap?) implemented with plain SVG/CSS — no chart lib — and where the dashboard mounts in the terminal layout.

## Answer
Dashboards v1: calibration curve renders real data now; other metrics render DESIGN.md empty states until data lands; recording track ships alongside: SessionLog (lifespan start/stop) + regime_at_decision recorded at decide time. Charts: plain SVG/CSS, zero new deps.
