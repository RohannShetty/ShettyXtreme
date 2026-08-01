"""ResearchBrief contract + strict payload validation (section 12).

The model may author only the fields in MODEL_AUTHORED_FIELDS; the harness
owns identity, provenance, and status. Strict pydantic validation with
`additionalProperties: false` semantics (unknown keys rejected) means
injected instructions cannot survive the channel.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

BriefStatus = Literal["proposed", "approved", "rejected"]

MODEL_AUTHORED_FIELDS = {
    "instruments",
    "direction",
    "confidence",
    "thesis",
    "rationale",
    "evidence",
    "risks",
    "validity_window_minutes",
}

DEFAULT_VALIDITY_MINUTES = 240


class ResearchBrief(BaseModel):
    """One briefer's schema-validated output for one lens."""

    brief_id: str
    lens: str
    as_of: str
    instruments: list[str] = Field(default_factory=list, max_length=10)
    direction: Literal[-1, 0, 1]
    confidence: float = Field(ge=0.0, le=1.0)
    thesis: str = Field(max_length=500)
    rationale: str = Field(min_length=300, max_length=1200)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    risks: list[str] = Field(default_factory=list, max_length=5)
    validity_window_minutes: int = DEFAULT_VALIDITY_MINUTES
    status: BriefStatus = "proposed"
    outcome: str | None = None
    decided_at: str | None = None

    def with_status(self, status: str) -> "ResearchBrief":
        """Return a copy with a new status (used only for decisions)."""
        return self.model_copy(update={"status": status})

    def is_expired(self, now: str | None = None) -> bool:
        """Proposed briefs expire after their validity window; decided briefs never do."""
        if self.status != "proposed":
            return False
        try:
            created = datetime.fromisoformat(self.as_of)
        except ValueError:
            return True
        expires = created + timedelta(minutes=self.validity_window_minutes)
        reference = datetime.fromisoformat(now) if now else datetime.now(UTC)
        return expires < reference


class BriefValidationError(Exception):
    """Raised when a provider payload fails strict validation."""


def parse_brief_payload(
    raw_text: str, *, lens: str, as_of: str, brief_id: str
) -> ResearchBrief:
    """Strict-parse a provider payload into a ResearchBrief.

    Steps: JSON parse -> object check -> unknown-field rejection -> pydantic
    validation with harness-owned fields injected. Raises BriefValidationError.
    """
    try:
        raw: Any = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise BriefValidationError(f"invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise BriefValidationError("payload must be a JSON object")
    unknown = set(raw) - MODEL_AUTHORED_FIELDS
    if unknown:
        raise BriefValidationError(f"unknown fields: {sorted(unknown)}")
    try:
        return ResearchBrief(brief_id=brief_id, lens=lens, as_of=as_of, **raw)
    except ValidationError as exc:
        raise BriefValidationError(f"schema violation: {exc}") from exc
