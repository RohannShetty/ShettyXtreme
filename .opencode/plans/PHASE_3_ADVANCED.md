# Phase 3: Advanced Intelligence & Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Execution Engine, Position Management (fixed TP3), and the Learning Loop for voter quality tracking.

**Architecture:** Transactional order execution, Event-sourced outcome tracking.

**Tech Stack:** Python 3.11+, Dhan Trading API (Integration Layer), SQLite.

## Global Constraints
- All broker commands pass through Transactional Risk Gates (entries only).
- All outcomes tracked in `learning/` (immutable signal_decisions).
- Core domain code has no external imports.

---

## Task 1: Execution Engine & Position Management
**Files:**
- Create: `src/shettyxtreme/execution/engine.py`
- Create: `src/shettyxtreme/execution/position_manager.py`

**Interfaces:**
- Consumes: `integration/dhan/trading_adapter.py`, `intelligence/risk/engine.py`
- Produces: `OrderPlaced` event, `PositionLifecycle` event.

- [ ] Task 1.1: Implement `PositionManager` (with FIXED TP1/TP2/TP3 + TSL logic).
- [ ] Task 1.2: Implement `ExecutionEngine` to bridge signal -> order placement.
- [ ] Task 1.3: Integration tests with Mock Dhan Adapter.

## Task 2: Learning Loop & Voter Calibration
**Files:**
- Create: `src/shettyxtreme/learning/outcome_tracker.py`
- Create: `src/shettyxtreme/learning/voter_calibrator.py`

**Interfaces:**
- Consumes: `execution/engine.py`, `intelligence/signals/signal_engine.py`
- Produces: `VoterWeightUpdated` event.

- [ ] Task 2.1: Implement `OutcomeTracker` (bind signals to execution intents and outcomes).
- [ ] Task 2.2: Implement `VoterCalibrator` (adjust voter weights based on conviction-outcome correlation).
- [ ] Task 2.3: Unit tests for learning loop logic.

- [ ] Task 3.1: Commit all phase 3 changes.
