"""Core Pydantic models used as structured I/O across all nodes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TestCase(BaseModel):
    """A single planned test case produced by the Planner."""

    id: str
    title: str
    feature: str = Field(
        description="Functional area: 'checkout', 'login' — from Jira epic/component or Figma frame"
    )
    route: str = Field(description="App route this case exercises — groups by page object")
    tags: list[str] = Field(default_factory=list, description="e.g. ['@smoke','@checkout']")
    steps: list[str]
    expected: list[str]
    source: Literal["figma", "jira", "both"] = "jira"


class UIElement(BaseModel):
    """A single UI element extracted from a design."""

    role: str
    name: str
    state: str = ""
    testid: str | None = None


class UIFlow(BaseModel):
    """A user flow extracted from a design."""

    name: str
    steps: list[str]


class ExpectedUI(BaseModel):
    """Structured UI spec derived from a Figma frame or design."""

    route: str = Field(description="App URL path this frame maps to")
    elements: list[UIElement] = Field(default_factory=list)
    flows: list[UIFlow] = Field(default_factory=list)


class RunResult(BaseModel):
    """Result of executing a test suite."""

    passed: bool
    failed_cases: list[str] = Field(default_factory=list)
    logs: str = ""
    screenshots: list[str] = Field(default_factory=list)
