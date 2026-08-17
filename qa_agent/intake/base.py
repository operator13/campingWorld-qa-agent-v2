"""Intake protocol — pluggable adapter that normalises any source into IntakeResult."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class IntakeResult(BaseModel):
    """Normalised starting state produced by any intake adapter."""

    goal: str = Field(description="What we're testing — one-line summary")
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Verifiable acceptance criteria / user stories",
    )
    figma_ref: Optional[str] = Field(
        default=None, description="Figma frame/node ID or URL"
    )
    app_url: Optional[str] = Field(
        default=None, description="URL of the app under test"
    )


@runtime_checkable
class Intake(Protocol):
    """Any intake source must implement this protocol."""

    async def load(self, ref: str) -> IntakeResult:
        """Load a source reference and return a normalised IntakeResult."""
        ...


def parse_source(source: str) -> tuple[str, str]:
    """Parse a CLI --source value like 'jira:QA-123' into (type, ref).

    Returns:
        Tuple of (source_type, reference). If no colon, type defaults to 'jira'.
    """
    if ":" in source:
        source_type, _, ref = source.partition(":")
        return source_type.lower(), ref
    return "jira", source
