# Phase 1: Standalone Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the core foundation: event bus, storage abstraction, configuration system, and basic Dhan integration adapters.

**Technology Stack:** Python 3.11+, Pydantic, DuckDB, SQLite, DhanHQ-py (pip).

## Global Constraints
- Core platform must have ZERO external imports.
- No direct `import openalgo` allowed.
- All broker/data integrations must be first-party code in `integration/` (absorbed patterns).

---
## Task 1: Core Platform Foundation
**Files:**
- Create: `src/shettyxtreme/core/event_bus.py`
- Create: `src/shettyxtreme/core/config.py`
- Create: `src/shettyxtreme/core/storage.py`

**Interfaces:**
- Produces: `EventBus` (asyncio-based), `BaseConfig` (Pydantic models), `StorageManager` (DuckDB/SQLite abstraction).

- [ ] Task 1.1: Implement `EventBus`
- [ ] Task 1.2: Implement `BaseConfig`
- [ ] Task 1.3: Implement `StorageManager`
- [ ] Task 1.4: Unit tests for core primitives
- [ ] Task 1.5: Commit

## Task 2: Dhan Integration Layer
**Files:**
- Create: `src/shettyxtreme/integration/dhan_adapter.py`
- Create: `src/shettyxtreme/integration/auth.py`

**Interfaces:**
- Consumes: `core/interfaces/*`
- Produces: `DhanBroker` interface implementation.

- [ ] Task 2.1: Implement Dhan Trading Adapter
- [ ] Task 2.2: Implement Dhan Data Adapter
- [ ] Task 2.3: Integrate `DhanHQ-py` as a lib
- [ ] Task 2.4: Integration Tests
- [ ] Task 2.5: Commit

## Task 3: Integration Supervisor & Resilience
**Files:**
- Create: `src/shettyxtreme/core/supervisor.py`

- [ ] Task 3.1: Implement `IntegrationSupervisor`
- [ ] Task 3.2: Implement Connection Watchdog
- [ ] Task 3.3: Integration Tests for resilience (WS reconnection)
- [ ] Task 3.4: Commit
