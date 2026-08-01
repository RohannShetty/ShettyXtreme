"""Context digest — as-of snapshot composed from injectable data sources.

The operator (or a later data-tool layer) attaches named text sources; the
digest renders them with provenance tags and never fabricates content.
"""
from __future__ import annotations

from datetime import UTC, datetime

MAX_SOURCES = 8
MAX_SOURCE_CHARS = 2000


class ContextDigest:
    """Builds the prompt context snapshot from named sources."""

    def __init__(self, sources: dict[str, str] | None = None) -> None:
        self._sources: dict[str, str] = {}
        if sources:
            for name, text in sources.items():
                self.add(name, text)

    @property
    def sources(self) -> dict[str, str]:
        return dict(self._sources)

    def add(self, name: str, text: str) -> None:
        """Add (or replace) one named source. Raises ValueError on bad name
        or when MAX_SOURCES is exceeded."""
        if not name or not name.strip():
            raise ValueError("source name must be non-empty")
        if len(self._sources) >= MAX_SOURCES:
            raise ValueError(f"at most {MAX_SOURCES} sources")
        self._sources[name.strip()] = text[:MAX_SOURCE_CHARS]

    def build(self) -> str:
        """Render the snapshot as markdown with [SOURCE: name] provenance."""
        parts = [f"# Research Context Snapshot (as of {datetime.now(UTC).isoformat()})"]
        if not self._sources:
            parts.append("[UNSOURCED] — no data sources attached to this run.")
        for name, text in self._sources.items():
            parts.append(f"## {name} [SOURCE: {name}]")
            parts.append(text if text else "[UNSOURCED] — no data")
        return "\n\n".join(parts)
