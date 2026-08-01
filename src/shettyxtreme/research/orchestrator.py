"""Research orchestrator — one-shot per-lens pipeline (5-stage loop, stage 1).

For each lens: digest -> prompt -> provider -> strict validate (reject-retry
once) -> persist. Lenses run concurrently; a failing lens surfaces partial
results + error and never auto-advances or crashes the run.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from shettyxtreme.research.briefs import (
    BriefValidationError,
    ResearchBrief,
    parse_brief_payload,
)
from shettyxtreme.research.digest import ContextDigest
from shettyxtreme.research.lenses import get_lens, list_lenses
from shettyxtreme.research.provider import BriefProvider, ProviderError
from shettyxtreme.research.store import ResearchStore

logger = logging.getLogger(__name__)

MAX_RETRIES = 1
DEFAULT_MAX_OUTPUT_TOKENS = 2000
DEFAULT_CALL_TIMEOUT = 90.0


@dataclass
class LensRunResult:
    """Outcome of one lens run: a brief, or a surfaced error."""

    lens: str
    brief: ResearchBrief | None = None
    error: str | None = None


@dataclass
class ResearchOrchestrator:
    """Runs one research pass across the requested lenses."""

    provider: BriefProvider
    store: ResearchStore
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    call_timeout: float = DEFAULT_CALL_TIMEOUT

    async def run(
        self,
        lenses: Sequence[str] | None = None,
        sources: Mapping[str, str] | None = None,
    ) -> list[LensRunResult]:
        """Run the requested lenses (all by default) and persist briefs.

        Raises ValueError on unknown lens names. Never raises for provider
        or validation failures — those become per-lens error entries.
        """
        names = list(lenses) if lenses is not None else [l.name for l in list_lenses()]
        valid = {l.name for l in list_lenses()}
        unknown = [n for n in names if n not in valid]
        if unknown:
            raise ValueError(f"unknown lens: {unknown}")
        digest_text = ContextDigest(dict(sources) if sources else None).build()
        results = await asyncio.gather(*(self._run_one(n, digest_text) for n in names))
        return list(results)

    async def _run_one(self, lens_name: str, digest_text: str) -> LensRunResult:
        lens = get_lens(lens_name)
        brief_id = str(uuid4())
        as_of = datetime.now(UTC).isoformat()
        prompt = lens.build_prompt(digest_text)
        last_error: str | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                raw = await asyncio.wait_for(
                    self.provider.generate(
                        system=lens.system_prompt,
                        prompt=prompt,
                        max_output_tokens=self.max_output_tokens,
                    ),
                    timeout=self.call_timeout,
                )
                brief = parse_brief_payload(
                    raw, lens=lens_name, as_of=as_of, brief_id=brief_id
                )
                self.store.insert(brief)
                return LensRunResult(lens=lens_name, brief=brief)
            except (ProviderError, BriefValidationError, asyncio.TimeoutError) as exc:
                last_error = str(exc)
                logger.warning("Lens %s attempt %d failed: %s", lens_name, attempt + 1, exc)
        return LensRunResult(lens=lens_name, error=last_error)
