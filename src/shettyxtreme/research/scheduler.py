"""Research scheduler — periodic research passes from env config (3C §3.3).

Env-gated: enabled/interval/lenses/tools from RESEARCH_SCHEDULE_*; the
lifespan wires it only when enabled AND DEEPSEEK_API_KEY is present. A
tick failure is logged and the loop continues — the scheduler never
crashes the app.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from shettyxtreme.research.orchestrator import ResearchOrchestrator

logger = logging.getLogger(__name__)


class ResearchScheduler:
    """Runs research passes on a fixed interval until stop()."""

    def __init__(
        self,
        orchestrator: ResearchOrchestrator,
        interval_minutes: float = 60.0,
        lenses: list[str] | None = None,
        tools: list[str] | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self.interval_minutes = interval_minutes
        self.lenses = list(lenses) if lenses else None
        self.tools = list(tools) if tools else None
        self._task: asyncio.Task | None = None
        self.next_run_at: str | None = None
        self.last_run_at: str | None = None
        self.last_result: str | None = None

    @property
    def enabled(self) -> bool:
        return self._task is not None

    def start(self) -> None:
        """Spawn the tick loop; no-op when already running."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

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

    def stop(self) -> None:
        """Cancel the tick loop; no-op when not running."""
        if self._task is None:
            return
        self._task.cancel()
        self._task = None
