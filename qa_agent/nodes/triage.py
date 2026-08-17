"""Step 5 · Triage — judges a failed run: broken test vs broken app.

Rates its own confidence. When unsure, the graph routes to Human Review
instead of auto-healing.

Memory-enhanced: checks for similar past failures and injects human
calibration context into the prompt.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from qa_agent.config import get_model
from qa_agent.memory import MemoryStore
from qa_agent.prompts.triage import SYSTEM_PROMPT
from qa_agent.state import QAState

logger = logging.getLogger(__name__)


async def triage(state: QAState) -> dict:
    """Classify a test failure and rate confidence.

    Memory-enhanced:
    1. Checks for similar past failures → fast classification hint
    2. Injects human calibration context → few-shot corrections
    """
    logger.info("Triage: analyzing failure for goal=%r", state.goal)

    memory = MemoryStore()

    # Check memory for similar past failure
    similar = None
    if state.error:
        similar = memory.find_similar_failure(state.error)
        if similar:
            logger.info(
                "Triage: found similar past failure %s (class=%s, resolution=%s)",
                similar.get("id"), similar.get("failure_class"), similar.get("resolution"),
            )

    # Build calibration context from human decisions
    calibration_context = memory.build_triage_calibration_context()

    model = ChatAnthropic(
        model=get_model("triage"),
        temperature=0,
        max_tokens=2048,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_prompt(state, similar=similar, calibration=calibration_context)),
    ]

    response = await model.ainvoke(messages)
    result = _parse_response(response)

    failure_class = result.get("failure_class", "unknown")
    confidence = result.get("confidence", 0.0)
    reasoning = result.get("reasoning", "")

    logger.info(
        "Triage: class=%s confidence=%.2f reason=%s",
        failure_class,
        confidence,
        reasoning[:100],
    )

    return {
        "failure_class": failure_class,
        "confidence": confidence,
    }


def _build_prompt(
    state: QAState,
    similar: dict[str, Any] | None = None,
    calibration: str = "",
) -> str:
    """Build the human message prompt for Triage."""
    parts = ["A test just failed. Analyze the failure and classify it.\n"]

    if state.error:
        parts.append("## Error message")
        parts.append(f"```\n{state.error}\n```\n")

    # Memory: similar past failure
    if similar:
        parts.append("## Memory: Similar past failure")
        parts.append(f"This error pattern has been seen before ({similar.get('occurrences', 1)} time(s)).")
        parts.append(f"Previous classification: **{similar.get('failure_class', 'unknown')}**")
        parts.append(f"Previous resolution: {similar.get('resolution', 'unknown')}")
        parts.append("Use this as a hint, but verify against the current evidence.\n")

    # Memory: human calibration
    if calibration:
        parts.append(calibration)
        parts.append("")

    if state.run_results:
        parts.append("## Run results")
        parts.append(f"Passed: {state.run_results.passed}")
        if state.run_results.failed_cases:
            parts.append(f"Failed cases: {', '.join(state.run_results.failed_cases)}")
        if state.run_results.logs:
            logs = state.run_results.logs[:3000]
            parts.append(f"\n### Logs (truncated)\n```\n{logs}\n```\n")

    if state.dom_snapshot:
        snapshot = state.dom_snapshot[:2000]
        parts.append(f"## DOM snapshot (truncated)\n```html\n{snapshot}\n```\n")

    if state.expected_ui:
        parts.append("## Expected UI elements")
        for el in state.expected_ui.elements:
            parts.append(f"  - {el.role}: '{el.name}' (testid: {el.testid or 'none'})")

    parts.append(f"\nAttempts so far: {state.attempts}")

    return "\n".join(parts)


def _parse_response(response: Any) -> dict:
    """Parse the LLM response into failure_class + confidence."""
    content = response.content if hasattr(response, "content") else str(response)

    try:
        if isinstance(content, str):
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            data = json.loads(json_str.strip())
        elif isinstance(content, list):
            for block in content:
                if hasattr(block, "text"):
                    data = json.loads(block.text)
                    break
            else:
                data = {}
        else:
            data = json.loads(content)
    except (json.JSONDecodeError, IndexError):
        logger.error("Triage: could not parse JSON, defaulting to unknown/low confidence")
        data = {"failure_class": "unknown", "confidence": 0.0}

    fc = data.get("failure_class", "unknown")
    if fc not in ("locator_drift", "app_defect", "unknown"):
        fc = "unknown"

    conf = float(data.get("confidence", 0.0))
    conf = max(0.0, min(1.0, conf))

    return {
        "failure_class": fc,
        "confidence": conf,
        "reasoning": data.get("reasoning", ""),
    }
