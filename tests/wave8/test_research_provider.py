"""Tests for the research provider abstraction (spec §3.1)."""
from __future__ import annotations

import pytest

from shettyxtreme.research.provider import (
    DeepSeekProvider,
    ProviderError,
    SimulatedProvider,
)


@pytest.mark.asyncio
async def test_simulated_default_brief() -> None:
    p = SimulatedProvider()
    out = await p.generate(system="s", prompt="p", max_output_tokens=100)
    assert '"direction": 0' in out


@pytest.mark.asyncio
async def test_simulated_script_cycle() -> None:
    p = SimulatedProvider(script=["one", "two", "three"])
    got = [await p.generate(system="s", prompt="p", max_output_tokens=1) for _ in range(4)]
    assert got == ["one", "two", "three", "three"]
    assert len(p.calls) == 4


@pytest.mark.asyncio
async def test_simulated_failure_injection() -> None:
    p = SimulatedProvider(fail="network")
    with pytest.raises(ProviderError, match="network"):
        await p.generate(system="s", prompt="p", max_output_tokens=10)
    p2 = SimulatedProvider(fail="invalid_json")
    out = await p2.generate(system="s", prompt="p", max_output_tokens=10)
    assert out == "this is not json"


@pytest.mark.asyncio
async def test_deepseek_provider_no_key(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = DeepSeekProvider(api_key="")
    with pytest.raises(ProviderError, match="DEEPSEEK_API_KEY"):
        await p.generate(system="s", prompt="p", max_output_tokens=10)


def test_deepseek_uses_env_key(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    p = DeepSeekProvider()
    assert p._api_key == "sk-test"
