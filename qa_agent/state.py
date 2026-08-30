"""Shared graph state — the single typed object every node reads/writes.

Reducers define how state merges inside the loop (e.g. `attempts` increments
instead of overwriting).
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from qa_agent.schemas.models import ExpectedUI, RunResult, TestCase


class QAState(BaseModel):
    """The shared state passed through every node in the graph.

    Between nodes it's in-memory typed Pydantic objects, not JSON.
    LangGraph passes this to each node; the node returns a partial update
    (only the fields it changed) which is merged back via the reducers.
    """

    # --- Intake ---
    goal: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    figma_ref: str | None = None
    app_url: str | None = None

    # --- Design Reader output ---
    figma_spec: dict | None = None  # type: ignore[type-arg]
    expected_ui: ExpectedUI | None = None

    # --- Planner output ---
    plan: list[TestCase] = Field(default_factory=list)

    # --- Generator output ---
    page_objects: dict[str, str] = Field(
        default_factory=dict,
        description="route -> page object class source (Healer edits here)",
    )
    test_code: dict[str, str] = Field(
        default_factory=dict,
        description="path -> spec file source (imports page objects)",
    )

    # --- Executor output ---
    run_results: RunResult | None = None
    dom_snapshot: str | None = None

    # --- Triage output ---
    failure_class: Literal["locator_drift", "app_defect", "test_flake", "unknown"] | None = None
    confidence: float = 0.0

    # --- Loop control ---
    attempts: Annotated[int, operator.add] = 0
    error: str | None = None
