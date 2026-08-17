"""Human Review surface — LangGraph interrupt() for low-confidence Triage calls.

When Triage isn't sure, the graph pauses here and waits for a human decision.
The human reviews the evidence and decides: heal or file a bug.

Memory-enhanced: every verdict is recorded for Triage calibration.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import Command, interrupt

from qa_agent.memory import MemoryStore
from qa_agent.state import QAState

logger = logging.getLogger(__name__)


def human_review(state: QAState) -> Command:
    """Pause the graph for human review of a low-confidence failure.

    Presents the Triage evidence to the human and waits for a decision.
    The human resumes with: {"decision": "heal"} or {"decision": "defect"}

    Records the decision in memory for Triage calibration.
    Returns a Command that routes to the appropriate next node.
    """
    logger.info(
        "Human Review: pausing for review (confidence=%.2f, class=%s)",
        state.confidence,
        state.failure_class,
    )

    # Build the review payload for the human
    review_payload = _build_review_payload(state)

    # Interrupt the graph — execution pauses here until a human resumes
    decision = interrupt(review_payload)

    # Process the human's decision
    human_decision = decision.get("decision", "defect") if isinstance(decision, dict) else "defect"
    reasoning = decision.get("reasoning", "") if isinstance(decision, dict) else ""

    logger.info("Human Review: decision=%s", human_decision)

    # Record in memory for Triage calibration
    memory = MemoryStore()
    route = state.plan[0].route if state.plan else "/"
    error_summary = (state.error or "")[:100]
    memory.record_human_decision(
        triage_guess=state.failure_class or "unknown",
        confidence=state.confidence,
        verdict=human_decision,
        error_summary=error_summary,
        reasoning=reasoning,
        route=route,
    )

    if human_decision == "heal":
        return Command(
            goto="healer",
            update={"failure_class": "locator_drift"},
        )
    else:
        return Command(
            goto="defect_report",
            update={"failure_class": "app_defect"},
        )


def _build_review_payload(state: QAState) -> dict[str, Any]:
    """Build the evidence payload presented to the human reviewer."""
    payload: dict[str, Any] = {
        "type": "human_review_request",
        "goal": state.goal,
        "triage_guess": state.failure_class,
        "confidence": state.confidence,
        "attempts": state.attempts,
    }

    if state.error:
        payload["error"] = state.error[:2000]

    if state.run_results:
        payload["failed_cases"] = state.run_results.failed_cases
        payload["logs_preview"] = state.run_results.logs[:1000]
        if state.run_results.screenshots:
            payload["screenshots"] = state.run_results.screenshots

    if state.dom_snapshot:
        payload["dom_snapshot_preview"] = state.dom_snapshot[:1000]

    payload["instructions"] = (
        'Respond with {"decision": "heal"} to fix the locator, '
        'or {"decision": "defect"} to file a bug report. '
        'Optionally include {"reasoning": "why"} to help Triage learn.'
    )

    return payload
