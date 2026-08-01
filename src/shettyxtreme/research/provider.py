"""LLM provider abstraction for the research layer.

provider.py is the ONLY module in the codebase that talks to an LLM
(D3 wall): nothing outside research/ imports it, and no LLM output
reaches the signal/gate/execution path. v2 (3C): generate() returns a
ProviderResponse that may carry tool_calls; tools + history are passed
through per the OpenAI-compatible function-calling contract.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


class ProviderError(Exception):
    """Raised when a provider call fails (network, HTTP, or parse)."""


@dataclass(frozen=True)
class ToolCall:
    """One function-call request emitted by the model."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    """A provider completion: text content and/or tool calls."""

    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class BriefProvider(Protocol):
    """A provider that turns a prompt into a structured response."""

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_output_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        """Return content and/or tool calls. Raises ProviderError on failure."""


class DeepSeekProvider:
    """OpenAI-compatible DeepSeek client via httpx (zero new deps)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEEPSEEK_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 90.0,
    ) -> None:
        self._explicit_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def _api_key(self) -> str:
        """Explicit constructor key wins; otherwise read env at call time."""
        if self._explicit_key:
            return self._explicit_key
        return os.environ.get("DEEPSEEK_API_KEY", "")

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_output_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        api_key = self._api_key()
        if not api_key:
            raise ProviderError("DEEPSEEK_API_KEY is not set")
        messages: list[dict[str, Any]] = list(history) if history else [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "max_tokens": max_output_tokens,
            "thinking": {"type": "disabled"},
            "stream": False,
        }
        if tools is not None:
            payload["tools"] = tools
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
            resp.raise_for_status()
            message = resp.json()["choices"][0]["message"]
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"DeepSeek HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"DeepSeek call failed: {exc}") from exc
        tool_calls = self._parse_tool_calls(message)
        if tool_calls:
            return ProviderResponse(
                content=message.get("content"), tool_calls=tool_calls
            )
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("DeepSeek returned an empty completion")
        return ProviderResponse(content=content.strip())

    @staticmethod
    def _parse_tool_calls(message: dict[str, Any]) -> list[ToolCall] | None:
        """Parse OpenAI-format `message.tool_calls` into ToolCall objects."""
        raw = message.get("tool_calls")
        if not raw:
            return None
        calls: list[ToolCall] = []
        for entry in raw:
            fn = entry.get("function", {})
            name = fn.get("name", "")
            try:
                args: Any = json.loads(fn.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {}
            if not isinstance(args, dict):
                args = {}
            calls.append(ToolCall(name=name, arguments=args))
        return calls or None


_DEFAULT_BRIEF = (
    '{"instruments": [], "direction": 0, "confidence": 0.5, '
    '"thesis": "No signal", '
    '"rationale": "simulated rationale ' + "x" * 340 + '", '
    '"evidence": [], "risks": []}'
)


class SimulatedProvider:
    """Deterministic test double with failure injection + scripted tool calls.

    fail: "network" -> ProviderError; "invalid_json" -> non-JSON content.
    Script entries are handed out in order; the last entry repeats; an
    empty script returns a schema-valid default brief. When
    simulate_tool_calls is non-empty the next generate() returns the next
    ToolCall (last repeats) with content=None; once exhausted (or never
    set), content behavior applies.
    """

    def __init__(
        self,
        script: list[str] | None = None,
        fail: str | None = None,
        fail_first: int = 0,
        fail_system_substring: str | None = None,
        simulate_tool_calls: list[ToolCall] | None = None,
    ) -> None:
        self._script = list(script) if script else []
        self.fail = fail
        self._fail_first = fail_first
        self._fail_system_substring = fail_system_substring
        self._tool_script = list(simulate_tool_calls) if simulate_tool_calls else []
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_output_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        self.calls.append(
            {
                "system": system,
                "prompt": prompt,
                "max_output_tokens": max_output_tokens,
                "tools": tools,
                "history": history,
            }
        )
        if self.fail == "network":
            raise ProviderError("simulated network failure")
        if self.fail == "invalid_json":
            return ProviderResponse(content="this is not json")
        if len(self.calls) <= self._fail_first:
            raise ProviderError("simulated network failure")
        if self._fail_system_substring and self._fail_system_substring in system:
            raise ProviderError("simulated network failure")
        if self._tool_script:
            if len(self._tool_script) == 1 and not self._script:
                return ProviderResponse(content=None, tool_calls=[self._tool_script[0]])
            return ProviderResponse(
                content=None, tool_calls=[self._tool_script.pop(0)]
            )
        if not self._script:
            return ProviderResponse(content=_DEFAULT_BRIEF)
        if len(self._script) == 1:
            return ProviderResponse(content=self._script[0])
        return ProviderResponse(content=self._script.pop(0))
