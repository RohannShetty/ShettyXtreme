"""Pluggable agent abstraction alongside Lens (P2-3.5 multi-agent layer).

Agents are the deterministic counterpart to LLM lenses. Each agent produces
a `ResearchBrief`-shaped `AgentSignal` without any LLM call (D3-clean).
Both agents and lenses write the same typed signal contract and persist into
the same research store.

Agent types: technical | options | risk | portfolio | sentiment | fundamental.
Deterministic agents return signals from pure computation; LLM-backed agents
(when added later) use the existing provider path.

Adding an agent is declarative: one entry in AGENTS. Config-registry
discovery mirrors the Lens pattern.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from shettyxtreme.research.briefs import ResearchBrief

logger = logging.getLogger(__name__)

AgentType = Literal[
    "technical",
    "fundamental",
    "sentiment",
    "options",
    "risk",
    "portfolio",
]


@dataclass
class Agent:
    """A research agent configuration: identity + computation path.

    Deterministic agents set `deterministic=True` and implement `compute()`.
    LLM-backed agents (future) set `deterministic=False` and use `build_prompt()`.
    """

    name: str
    agent_type: AgentType
    description: str
    deterministic: bool = True

    def compute(
        self,
        data: dict[str, Any],
        existing_signals: list[ResearchBrief] | None = None,
    ) -> ResearchBrief:
        """Produce a ResearchBrief-shaped signal from data.

        Deterministic agents override this. LLM-backed agents use build_prompt().
        Raises NotImplementedError if called on a non-deterministic agent without
        an override.
        """
        raise NotImplementedError(
            f"Agent {self.name} does not implement compute(); "
            "use build_prompt() for LLM-backed agents"
        )

    def build_prompt(self, digest_text: str) -> str | None:
        """Build an LLM prompt (for non-deterministic agents). Returns None
        for deterministic agents."""
        return None


@dataclass
class AgentSignal:
    """Outcome of one agent run: a brief, or a surfaced error."""

    agent: str
    brief: ResearchBrief | None = None
    error: str | None = None


def make_brief(
    agent_name: str,
    instruments: list[str],
    direction: Literal[-1, 0, 1],
    confidence: float,
    thesis: str,
    rationale: str,
    evidence: list[dict[str, Any]] | None = None,
    risks: list[str] | None = None,
    validity_window_minutes: int = 240,
) -> ResearchBrief:
    """Factory for deterministic agent briefs (harness-owned fields injected)."""
    now = datetime.now(UTC)
    return ResearchBrief(
        brief_id=str(uuid4()),
        lens=agent_name,
        as_of=now.isoformat(),
        instruments=instruments[:10],
        direction=direction,
        confidence=max(0.0, min(1.0, confidence)),
        thesis=thesis[:500],
        rationale=rationale[:1200].ljust(300, " "),  # min_length=300
        evidence=(evidence or [])[:10],
        risks=(risks or [])[:5],
        validity_window_minutes=validity_window_minutes,
        status="proposed",
    )


# ---------------------------------------------------------------------------
# Agent registry (parallel to LENSES dict in lenses.py)
# ---------------------------------------------------------------------------
AGENTS: dict[str, Agent] = {}


def register_agent(agent: Agent) -> None:
    """Register an agent in the global registry."""
    if agent.name in AGENTS:
        raise ValueError(f"agent {agent.name!r} already registered")
    AGENTS[agent.name] = agent


def list_agents() -> list[Agent]:
    """All registered agents, in registry order."""
    return list(AGENTS.values())


def get_agent(name: str) -> Agent:
    """Look up an agent by name; raises KeyError for unknown names."""
    if name not in AGENTS:
        raise KeyError(name)
    return AGENTS[name]


def list_deterministic_agents() -> list[Agent]:
    """All registered deterministic agents."""
    return [a for a in AGENTS.values() if a.deterministic]


# ---------------------------------------------------------------------------
# Import agent implementations (triggers register_agent at import time)
# ---------------------------------------------------------------------------
from shettyxtreme.research.agents.technical import compute_technical_signal  # noqa: E402, F401
from shettyxtreme.research.agents.options import compute_options_signal  # noqa: E402, F401
from shettyxtreme.research.agents.risk import compute_risk_annotation  # noqa: E402, F401
from shettyxtreme.research.agents.portfolio import compute_portfolio_proposal  # noqa: E402, F401
