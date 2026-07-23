# Learning System Design

## Goal
Implement `OutcomeTracker` and `VoterCalibrator` to enable learning from trading outcomes and calibrating voter conviction.

## Architecture
- `OutcomeTracker`: Records signal decisions and their eventual trade outcomes (win/loss).
- `VoterCalibrator`: Uses `OutcomeTracker` data to adjust voter weights based on conviction/outcome correlations.
- Integration: `EventBus` signals trigger `OutcomeTracker` record creation. Trade fills/exits from `ExecutionEngine` trigger completion of outcomes via `EventBus`.

## Decisions
1. `OutcomeTracker` will mirror `VoterQualityTracker` structure but for decision-level lifecycle, not just voter/outcome rows.
2. `VoterCalibrator` will compute correlation coefficient between voter `confidence` and `OutcomeLabel`.
3. `EventBus` handlers will bind signals to decisions in `OutcomeTracker`.

## Approval
User has not yet approved. Presenting for approval.
