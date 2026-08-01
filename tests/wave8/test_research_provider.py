"""Tests for the research provider abstraction (spec §3.1, §3.2 v2)."""
from __future__ import annotations

import pytest

from shettyxtreme.research.provider import (
    DeepSeekProvider,
    ProviderError,
    ProviderResponse,
    SimulatedProvider,
    ToolCall,
)


@pytest.mark.asyncio
async def test_simulated_default_brief() -> None:
    p = SimulatedProvider()
    out = await p.generate(system="s", prompt="p", max_output_tokens=100)
    assert out.tool_calls is None
    assert out.content is not None and '"direction": 0' in out.content


@pytest.mark.asyncio
async def test_simulated_script_cycle() -> None:
    p = SimulatedProvider(script=["one", "two", "three"])
    got = [
        await p.generate(system="s", prompt="p", max_output_tokens=1) for _ in range(4)
    ]
    assert [g.content for g in got] == ["one", "two", "three", "three"]
    assert len(p.calls) == 4


@pytest.mark.asyncio
async def test_simulated_failure_injection() -> None:
    p = SimulatedProvider(fail="network")
    with pytest.raises(ProviderError, match="network"):
        await p.generate(system="s", prompt="p", max_output_tokens=10)
    p2 = SimulatedProvider(fail="invalid_json")
    out = await p2.generate(system="s", prompt="p", max_output_tokens=10)
    assert out.content == "this is not json"


@pytest.mark.asyncio
async def test_simulated_tool_script() -> None:
    tc = ToolCall(name="chain_snapshot", arguments={"symbol": "NIFTY"})
    p = SimulatedProvider(script=["final"], simulate_tool_calls=[tc])
    first = await p.generate(system="s", prompt="p", max_output_tokens=10)
    assert first.content is None
    assert first.tool_calls == [tc]
    second = await p.generate(system="s", prompt="p", max_output_tokens=10)
    assert second.content == "final"
    assert second.tool_calls is None


@pytest.mark.asyncio
async def test_simulated_tool_script_single_repeats() -> None:
    tc = ToolCall(name="regime_snapshot", arguments={})
    p = SimulatedProvider(simulate_tool_calls=[tc])
    for _ in range(3):
        out = await p.generate(system="s", prompt="p", max_output_tokens=10)
        assert out.content is None
        assert out.tool_calls == [tc]


@pytest.mark.asyncio
async def test_simulated_records_tools_and_history() -> None:
    p = SimulatedProvider()
    await p.generate(
        system="s",
        prompt="p",
        max_output_tokens=10,
        tools=[{"type": "function", "function": {"name": "x"}}],
        history=[{"role": "user", "content": "h"}],
    )
    assert p.calls[-1]["tools"] == [{"type": "function", "function": {"name": "x"}}]
    assert p.calls[-1]["history"] == [{"role": "user", "content": "h"}]


@pytest.mark.asyncio
async def test_deepseek_provider_no_key(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = DeepSeekProvider(api_key="")
    with pytest.raises(ProviderError, match="DEEPSEEK_API_KEY"):
        await p.generate(system="s", prompt="p", max_output_tokens=10)


@pytest.mark.asyncio
async def test_deepseek_reads_env_at_call_time(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = DeepSeekProvider()
    with pytest.raises(ProviderError, match="DEEPSEEK_API_KEY"):
        await p.generate(system="s", prompt="p", max_output_tokens=10)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    try:
        await p.generate(system="s", prompt="p", max_output_tokens=10)
    except ProviderError as exc:
        assert "DEEPSEEK_API_KEY is not set" not in str(exc)


def test_deepseek_parses_tool_calls() -> None:
    msg = {
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "chain_snapshot",
                    "arguments": '{"symbol": "NIFTY"}',
                },
            }
        ],
    }
    calls = DeepSeekProvider._parse_tool_calls(msg)
    assert calls == [ToolCall(name="chain_snapshot", arguments={"symbol": "NIFTY"})]


def test_deepseek_parses_empty_arguments() -> None:
    msg = {"content": None, "tool_calls": [{"function": {"name": "regime_snapshot"}}]}
    assert DeepSeekProvider._parse_tool_calls(msg) == [
        ToolCall(name="regime_snapshot", arguments={})
    ]


def test_deepseek_no_tool_calls_returns_none() -> None:
    assert DeepSeekProvider._parse_tool_calls({"content": "hi"}) is None


def test_provider_response_shapes() -> None:
    assert ProviderResponse(content="x") == ProviderResponse(content="x")
    assert ProviderResponse(content=None, tool_calls=[ToolCall(name="a", arguments={})]).tool_calls is not None
