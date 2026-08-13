"""Research scheduler — periodic research passes from env config (3C §3.3).

Env-gated: enabled/interval/lenses/tools from RESEARCH_SCHEDULE_*; the
lifespan wires it only when enabled AND DEEPSEEK_API_KEY is present. A
tick failure is logged and the loop continues — the scheduler never
crashes the app.

P2-3.5: deterministic agents run on a separate, faster cadence (default 5 min)
because they have zero LLM cost. LLM lenses stay on the operator-chosen cadence.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from shettyxtreme.research.orchestrator import ResearchOrchestrator

logger = logging.getLogger(__name__)


class ResearchScheduler:
    """Runs research passes on a fixed interval until stop().

    P2-3.5: supports a dual-cadence model:
    - LLM lenses: operator-chosen interval (default 60 min)
    - Deterministic agents: fast interval (default 5 min, zero LLM cost)
    """

    def __init__(
        self,
        orchestrator: ResearchOrchestrator,
        interval_minutes: float = 60.0,
        agent_interval_minutes: float = 5.0,
        lenses: list[str] | None = None,
        tools: list[str] | None = None,
        agents: list[str] | None = None,
    ) -> None:
        if interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")
        if agent_interval_minutes <= 0:
            raise ValueError("agent_interval_minutes must be positive")
        self._orchestrator = orchestrator
        self.interval_minutes = interval_minutes
        self.agent_interval_minutes = agent_interval_minutes
        self.lenses = list(lenses) if lenses else None
        self.tools = list(tools) if tools else None
        self.agents = list(agents) if agents else None
        self._task: asyncio.Task | None = None
        self._agent_task: asyncio.Task | None = None
        self.next_run_at: str | None = None
        self.last_run_at: str | None = None
        self.last_result: str | None = None
        self.next_agent_run_at: str | None = None
        self.last_agent_run_at: str | None = None
        self.last_agent_result: str | None = None

    @property
    def enabled(self) -> bool:
        return self._task is not None

    def start(self) -> None:
        """Spawn the tick loop; no-op when already running."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())
        # P2-3.5: deterministic agent loop (fast cadence, no LLM cost)
        self._agent_task = asyncio.create_task(self._agent_loop())

    async def _loop(self) -> None:
        while True:
            self.next_run_at = (
                datetime.now(UTC) + timedelta(minutes=self.interval_minutes)
            ).isoformat()
            await asyncio.sleep(self.interval_minutes * 60)
            try:
                results = await self._orchestrator.run(
                    lenses=self.lenses, tools=self.tools
                )
                self.last_result = (
                    "ok" if all(r.error is None for r in results) else "partial"
                )
            except Exception as exc:
                logger.error("Research scheduled run failed: %s", exc)
                self.last_result = str(exc)
            self.last_run_at = datetime.now(UTC).isoformat()
            self.next_run_at = (
                datetime.now(UTC) + timedelta(minutes=self.interval_minutes)
            ).isoformat()

    async def _agent_loop(self) -> None:
        """P2-3.5: fast cadence loop for deterministic agents (no LLM cost)."""
        while True:
            self.next_agent_run_at = (
                datetime.now(UTC) + timedelta(minutes=self.agent_interval_minutes)
            ).isoformat()
            await asyncio.sleep(self.agent_interval_minutes * 60)
            try:
                results = await self._orchestrator.run_agents(
                    agent_names=self.agents,
                )
                self.last_agent_result = (
                    "ok" if all(r.error is None for r in results) else "partial"
                )
            except Exception as exc:
                logger.error("Agent scheduled run failed: %s", exc)
                self.last_agent_result = str(exc)
            self.last_agent_run_at = datetime.now(UTC).isoformat()
            self.next_agent_run_at = (
                datetime.now(UTC) + timedelta(minutes=self.agent_interval_minutes)
            ).isoformat()

    def stop(self) -> None:
        """Cancel the tick loop; no-op when not running."""
        if self._task is None:
            return
        self._task.cancel()
        self._task = None
        if self._agent_task is not None:
            self._agent_task.cancel()
            self._agent_task = None
