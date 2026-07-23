# Cockpit UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Workflow-Prioritized Cockpit UI using the data-dense blueprint.

**Architecture:** Tailwind CSS components with a split-workflow layout.

**Tech Stack:** FastAPI, Tailwind, shadcn/ui.

## Global Constraints
- Data-Dense Dashboard style (Fira Code/Sans).
- No emojis (use Lucide icons).
- Cursor-pointer on all interactive elements.

---

## Task 1: UI Shell & Top Bar
**Files:**
- Create: `terminal/ui/components/Navbar.tsx`
- Modify: `terminal/ui/App.tsx` (Root layout)

- [ ] Task 1.1: Implement `App` shell with `Navbar` (System health, mode selector).
- [ ] Task 1.2: Style with Fira Sans (Data-Dense specs).
- [ ] Task 1.3: Commit.

## Task 2: Market Surveillance View
**Files:**
- Create: `terminal/ui/pages/SurveillanceView.tsx`

- [ ] Task 2.1: Implement Watchlist & Scanner list modules using shadcn/ui.
- [ ] Task 2.2: Add scanner alert pop-ins.
- [ ] Task 2.3: Commit.

## Task 3: Execution Cockpit
**Files:**
- Create: `terminal/ui/pages/ExecutionView.tsx`

- [ ] Task 3.1: Implement Position Management card (TP/TSL controls).
- [ ] Task 3.2: Implement Risk/MTM display.
- [ ] Task 3.3: Task 3.2: Implement Alert-Triage Tray workflow.
- [ ] Task 3.4: Commit.
