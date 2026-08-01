"""Tests for the research scheduler (spec §3.3)."""
from __future__ import annotations

import asyncio

import pytest

from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import SimulatedProvider
from shettyxtreme.research.scheduler import ResearchScheduler
from shettyxtreme.research.store import ResearchStore


async def _await_run(sched: ResearchScheduler, timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while sched.last_run_at is None:
        if loop.time() > deadline:
            raise AssertionError("scheduler never ran")
        await asyncio.sleep(0.01)


async def _await_next_run(
    sched: ResearchScheduler, previous: str, timeout: float = 3.0
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while sched.last_run_at == previous:
        if loop.time() > deadline:
            raise AssertionError("scheduler loop stopped after failure")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_scheduler_tick_persists_briefs(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    orch = ResearchOrchestrator(provider=SimulatedProvider(), store=store)
    sched = ResearchScheduler(orchestrator=orch, interval_minutes=0.0005)
    sched.start()
    assert sched.enabled is True
    try:
        await _await_run(sched)
        assert store.list().__len__() >= 1
        assert sched.last_result == "ok"
        assert sched.last_run_at is not None
        assert sched.next_run_at is not None
    finally:
        sched.stop()
    assert sched.enabled is False
    store.close()


@pytest.mark.asyncio
async def test_scheduler_partial_result_surfaces(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    orch = ResearchOrchestrator(
        provider=SimulatedProvider(fail="network"), store=store
    )
    sched = ResearchScheduler(orchestrator=orch, interval_minutes=0.0005)
    sched.start()
    try:
        await _await_run(sched)
        assert sched.last_result == "partial"
    finally:
        sched.stop()
    store.close()


@pytest.mark.asyncio
async def test_scheduler_exception_loop_continues(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    orch = ResearchOrchestrator(provider=SimulatedProvider(), store=store)
    # run() raises ValueError for the unknown tool — the loop must survive.
    sched = ResearchScheduler(
        orchestrator=orch, interval_minutes=0.0005, tools=["nope"]
    )
    sched.start()
    try:
        await _await_run(sched)
        assert sched.last_result is not None and "unknown tool" in sched.last_result
        first = sched.last_run_at
        assert first is not None
        await _await_next_run(sched, first)
    finally:
        sched.stop()
    store.close()


@pytest.mark.asyncio
async def test_scheduler_start_stop_idempotent(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    orch = ResearchOrchestrator(provider=SimulatedProvider(), store=store)
    sched = ResearchScheduler(orchestrator=orch, interval_minutes=0.0005)
    sched.start()
    sched.start()
    assert sched.enabled is True
    sched.stop()
    sched.stop()
    assert sched.enabled is False
    store.close()
