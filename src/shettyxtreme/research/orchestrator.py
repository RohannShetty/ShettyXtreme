"""Research orchestrator — one-shot per-lens pipeline with bounded tool loop.

For each lens: digest -> prompt -> provider (tools allowed) -> strict
validate (reject-retry once) -> persist. Lenses run concurrently; a
failing lens surfaces partial results + error and never auto-advances or
crashes the run. Tool calls are capped at MAX_TOOL_CALLS per lens; when
the budget is exhausted without final content the lens errors out.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping, Sequence
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
from shettyxtreme.research.provider import BriefProvider, ProviderError, ToolCall
from shettyxtreme.research.store import ResearchStore
from shettyxtreme.research.tools import TOOLS, list_tools, run_tool

logger = logging.getLogger(__name__)

MAX_RETRIES = 1
MAX_TOOL_CALLS = 3
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
    on_brief: Callable[[ResearchBrief], None] | None = None

    async def run(
        self,
        lenses: Sequence[str] | None = None,
        sources: Mapping[str, str] | None = None,
        tools: Sequence[str] | None = None,
    ) -> list[LensRunResult]:
        """Run the requested lenses (all by default) and persist briefs.

        Raises ValueError on unknown lens or tool names. Never raises for
        provider or validation failures — those become per-lens errors.
        """
        names = list(lenses) if lenses is not None else [l.name for l in list_lenses()]
        valid = {l.name for l in list_lenses()}
        unknown = [n for n in names if n not in valid]
        if unknown:
            raise ValueError(f"unknown lens: {unknown}")
        tool_names = list(tools) if tools else []
        valid_tools = {t.name for t in list_tools()}
        unknown_tools = [n for n in tool_names if n not in valid_tools]
        if unknown_tools:
            raise ValueError(f"unknown tool: {unknown_tools}")
        provider_tools: list[dict] | None = None
        if tool_names:
            provider_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.params_schema,
                    },
                }
                for t in (TOOLS[n] for n in tool_names)
            ]
        digest_text = ContextDigest(dict(sources) if sources else None).build()
        results = await asyncio.gather(
            *(self._run_one(n, digest_text, provider_tools) for n in names)
        )
        return list(results)

    async def _run_one(
        self, lens_name: str, digest_text: str, provider_tools: list[dict] | None
    ) -> LensRunResult:
        lens = get_lens(lens_name)
        brief_id = str(uuid4())
        as_of = datetime.now(UTC).isoformat()
        prompt = lens.build_prompt(digest_text)
        messages: list[dict] = [
            {"role": "system", "content": lens.system_prompt},
            {"role": "user", "content": prompt},
        ]
        last_error: str | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                tool_calls_used = 0
                while True:
                    resp = await asyncio.wait_for(
                        self.provider.generate(
                            system=lens.system_prompt,
                            prompt=prompt,
                            max_output_tokens=self.max_output_tokens,
                            tools=provider_tools,
                            history=list(messages) if tool_calls_used else None,
                        ),
                        timeout=self.call_timeout,
                    )
                    if resp.tool_calls:
                        tool_calls_used += len(resp.tool_calls)
                        if tool_calls_used > MAX_TOOL_CALLS:
                            return LensRunResult(
                                lens=lens_name, error="tool call budget exceeded"
                            )
                        messages.append(self._assistant_tool_message(resp.tool_calls))
                        for i, tc in enumerate(resp.tool_calls):
                            messages.append(self._tool_result_message(tc, f"call_{i}"))
                        continue
                    if not resp.content:
                        return LensRunResult(
                            lens=lens_name, error="empty provider response"
                        )
                    brief = parse_brief_payload(
                        resp.content, lens=lens_name, as_of=as_of, brief_id=brief_id
                    )
                    try:
                        self.store.insert(brief)
                    except Exception as exc:
                        logger.warning("Lens %s persist failed: %s", lens_name, exc)
                        return LensRunResult(
                            lens=lens_name, error=f"persist failed: {exc}"
                        )
                    if self.on_brief is not None:
                        self.on_brief(brief)
                    return LensRunResult(lens=lens_name, brief=brief)
            except (ProviderError, BriefValidationError, asyncio.TimeoutError) as exc:
                last_error = str(exc)
                logger.warning("Lens %s attempt %d failed: %s", lens_name, attempt + 1, exc)
        return LensRunResult(lens=lens_name, error=last_error)

    @staticmethod
    def _assistant_tool_message(calls: Sequence[ToolCall]) -> dict:
        """OpenAI-format assistant message carrying tool_calls."""
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": c.name,
                        "arguments": json.dumps(c.arguments),
                    },
                }
                for i, c in enumerate(calls)
            ],
        }

    @staticmethod
    def _tool_result_message(call: ToolCall, call_id: str) -> dict:
        try:
            result = run_tool(call.name, call.arguments)
        except Exception as exc:
            result = f"TOOL ERROR: {exc}"
        return {"role": "tool", "tool_call_id": call_id, "content": result}
