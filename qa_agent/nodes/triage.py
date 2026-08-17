"""Step 5 · Triage — judges a failed run: broken test vs broken app.

Rates its own confidence. When unsure, the graph routes to Human Review
instead of auto-healing.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from qa_agent.config import get_model
from qa_agent.prompts.triage import SYSTEM_PROMPT
from qa_agent.state import QAState

logger = logging.getLogger(__name__)


async def triage(state: QAState) -> dict:
    """Classify a test failure and rate confidence."""
    logger.info("Triage: analyzing failure for goal=%r", state.goal)

    model = ChatAnthropic(
        model=get_model("triage"),
        temperature=0,
        max_tokens=2048,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_prompt(state)),
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


def _build_prompt(state: QAState) -> str:
    """Build the human message prompt for Triage."""
    parts = ["A test just failed. Analyze the failure and classify it.\n"]

    if state.error:
        parts.append("## Error message")
        parts.append(f"```\n{state.error}\n```\n")

    if state.run_results:
        parts.append("## Run results")
        parts.append(f"Passed: {state.run_results.passed}")
        if state.run_results.failed_cases:
            parts.append(f"Failed cases: {', '.join(state.run_results.failed_cases)}")
        if state.run_results.logs:
            # Truncate logs to avoid token overflow
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

    # Validate failure_class
    fc = data.get("failure_class", "unknown")
    if fc not in ("locator_drift", "app_defect", "unknown"):
        fc = "unknown"

    # Clamp confidence
    conf = float(data.get("confidence", 0.0))
    conf = max(0.0, min(1.0, conf))

    return {
        "failure_class": fc,
        "confidence": conf,
        "reasoning": data.get("reasoning", ""),
    }
