"""LLM provider abstraction for the research layer.

provider.py is the ONLY module in the codebase that talks to an LLM
(D3 wall): nothing outside research/ imports it, and no LLM output
reaches the signal/gate/execution path.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


class ProviderError(Exception):
    """Raised when a provider call fails (network, HTTP, or parse)."""


class BriefProvider(Protocol):
    """A provider that turns a prompt into a raw model response string."""

    async def generate(self, *, system: str, prompt: str, max_output_tokens: int) -> str:
        """Return the model's text output. Raises ProviderError on failure."""


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

    async def generate(self, *, system: str, prompt: str, max_output_tokens: int) -> str:
        api_key = self._api_key()
        if not api_key:
            raise ProviderError("DEEPSEEK_API_KEY is not set")
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_output_tokens,
            "thinking": {"type": "disabled"},
            "stream": False,
        }
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
            content = resp.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"DeepSeek HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"DeepSeek call failed: {exc}") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("DeepSeek returned an empty completion")
        return content.strip()


_DEFAULT_BRIEF = (
    '{"instruments": [], "direction": 0, "confidence": 0.5, '
    '"thesis": "No signal", '
    '"rationale": "simulated rationale ' + "x" * 340 + '", '
    '"evidence": [], "risks": []}'
)


class SimulatedProvider:
    """Deterministic test double with failure injection.

    fail: "network" -> ProviderError; "invalid_json" -> non-JSON text.
    Script entries are handed out in order; the last entry repeats; an
    empty script returns a schema-valid default brief.
    """

    def __init__(
        self,
        script: list[str] | None = None,
        fail: str | None = None,
        fail_first: int = 0,
        fail_system_substring: str | None = None,
    ) -> None:
        self._script = list(script) if script else []
        self.fail = fail
        self._fail_first = fail_first
        self._fail_system_substring = fail_system_substring
        self.calls: list[dict] = []

    async def generate(self, *, system: str, prompt: str, max_output_tokens: int) -> str:
        self.calls.append(
            {"system": system, "prompt": prompt, "max_output_tokens": max_output_tokens}
        )
        if self.fail == "network":
            raise ProviderError("simulated network failure")
        if self.fail == "invalid_json":
            return "this is not json"
        if len(self.calls) <= self._fail_first:
            raise ProviderError("simulated network failure")
        if self._fail_system_substring and self._fail_system_substring in system:
            raise ProviderError("simulated network failure")
        if not self._script:
            return _DEFAULT_BRIEF
        if len(self._script) == 1:
            return self._script[0]
        return self._script.pop(0)
