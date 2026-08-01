"""Declarative lens registry — section 12 config-registry briefer discovery.

Adding a lens is declarative: one entry in LENSES. Each lens mirrors one
live shadow-voter philosophy so briefs read the same signals the engine does.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Lens:
    """A briefer configuration: identity + prompts."""

    name: str
    description: str
    system_prompt: str
    brief_prompt_template: str

    def build_prompt(self, digest_text: str) -> str:
        return self.brief_prompt_template.format(digest=digest_text)


_BRIEF_FORMAT = (
    "DATA SNAPSHOT:\n{digest}\n\n"
    "Respond with a single JSON object only: "
    '{{"instruments": [..max 10 NSE symbols..], "direction": -1|0|1, '
    '"confidence": 0.0-1.0, "thesis": "1-2 sentences, max 500 chars", '
    '"rationale": "300-1200 chars", '
    '"evidence": [{{"item": "...", "source": "...", "unsourced": bool}}] '
    "(max 10), "
    '"risks": ["..."] (max 5)}}'
)

LENSES: dict[str, Lens] = {
    "oi_iv_flow": Lens(
        name="oi_iv_flow",
        description="Smart-money positioning from OI buildup and IV posture.",
        system_prompt=(
            "You are an options research assistant for Indian NSE markets. "
            "Examine open-interest flow, IV rank, and put/call buildup, and "
            "write one structured brief. Research-only: you never place "
            "orders or instruct trading. Tie every claim to the provided "
            "data; mark anything not in the data as unsourced."
        ),
        brief_prompt_template=(
            "Write a research brief for the OI/IV-flow lens: where is "
            "positioning building, and what does it imply?\n\n" + _BRIEF_FORMAT
        ),
    ),
    "directional_momentum": Lens(
        name="directional_momentum",
        description="Is a directional move building? Momentum, breakouts, gaps.",
        system_prompt=(
            "You are an options research assistant for Indian NSE markets. "
            "Evaluate momentum, breakout, and gap conditions and write one "
            "structured brief. Research-only: you never place orders or "
            "instruct trading. Tie every claim to the provided data; mark "
            "anything not in the data as unsourced."
        ),
        brief_prompt_template=(
            "Write a research brief for the directional-momentum lens: is a "
            "directional move building, and at what conviction?\n\n"
            + _BRIEF_FORMAT
        ),
    ),
    "tail_risk": Lens(
        name="tail_risk",
        description="Stretched conditions and what could break.",
        system_prompt=(
            "You are an options research assistant for Indian NSE markets. "
            "Hunt for stretched conditions, crowding, and tail risks, and "
            "write one structured brief. Research-only: you never place "
            "orders or instruct trading. Tie every claim to the provided "
            "data; mark anything not in the data as unsourced."
        ),
        brief_prompt_template=(
            "Write a research brief for the tail-risk lens: what is "
            "stretched, crowded, or likely to break?\n\n" + _BRIEF_FORMAT
        ),
    ),
}


def list_lenses() -> list[Lens]:
    """All registered lenses, in registry order."""
    return list(LENSES.values())


def get_lens(name: str) -> Lens:
    """Look up a lens by name; raises KeyError for unknown names."""
    if name not in LENSES:
        raise KeyError(name)
    return LENSES[name]
