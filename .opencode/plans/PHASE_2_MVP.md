# Phase 2: Usable MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Intelligence Layer (Signal Engine, Features, Regime) and the basic Terminal UI (Cockpit).

**Architecture:** Event-sourced intelligence; Data-dense web terminal.

**Tech Stack:** FastAPI, Tailwind CSS, shadcn/ui, Pydantic, DuckDB.

## Global Constraints
- Core intelligence depends on `core/` only.
- Intelligence layer uses Event-Bus-Only communication.
- Web terminal follows Data-Dense design system.

---

## Task 1: Intelligence Layer - Signal & Feature Engine
**Files:**
- Create: `src/shettyxtreme/intelligence/features/engine.py`
- Create: `src/shettyxtreme/intelligence/signals/signal_engine.py`

**Interfaces:**
- Consumes: `core/event_bus/*`
- Produces: `Signal` event, `Feature` emission.

- [ ] Task 1.1: Implement `FeatureEngine` (On-demand/Plugin basis).
- [ ] Task 1.2: Implement `SignalEngine` (Conviction-weighted logic).
- [ ] Task 1.3: Implement basic Voter Plugins (e.g., ORB, IV Rank).
- [ ] Task 1.4: Unit tests for signal scoring and feature computation.

## Task 2: Terminal UI (Cockpit)
**Files:**
- Create: `terminal/main.py` (FastAPI)
- Create: `terminal/ui/` (Frontend - Tailwind/shadcn)

**Interfaces:**
- Consumes: `core/*`, `intelligence/*`

- [ ] Task 2.1: Implement FastAPI backend endpoints.
- [ ] Task 2.2: Implement Data-Dense Dashboard (Watchlist, Cockpit, Positions).
- [ ] Task 2.3: Implement Alert-Triage Tray workflow.
- [ ] Task 2.4: Commit.
