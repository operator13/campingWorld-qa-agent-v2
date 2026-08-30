"""Step 2 · Planner — expected_ui + acceptance_criteria → list[TestCase].

Uses Opus for stronger reasoning about test case design.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from qa_agent.audit import AuditStore
from qa_agent.config import get_model
from qa_agent.memory import MemoryStore
from pathlib import Path

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "PLANNER.md").read_text()
from qa_agent.schemas.models import TestCase
from qa_agent.state import QAState

logger = logging.getLogger(__name__)


async def planner(state: QAState) -> dict:
    """Turn UI spec + acceptance criteria into categorized test cases."""
    logger.info("Planner: generating test cases for goal=%r", state.goal)

    # Gather memory context: volatile routes + flaky tests + lessons
    memory = MemoryStore()
    memory_context = memory.build_planner_memory_context()
    lessons_context = memory.build_lessons_context(max_tokens=250)
    if lessons_context:
        memory_context = (memory_context + "\n\n" + lessons_context).strip()

    model = ChatAnthropic(
        model=get_model("planner"),
        temperature=0,
        max_tokens=8192,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_prompt(state, memory_context=memory_context)),
    ]

    response = await model.ainvoke(messages)
    AuditStore.record_llm_call(response, model=get_model("planner"))
    test_cases = _parse_response(response)

    logger.info("Planner: generated %d test case(s)", len(test_cases))
    return {"plan": test_cases}


def _build_prompt(state: QAState, memory_context: str = "") -> str:
    """Build the human message prompt for the Planner."""
    parts = [f"Create test cases for: {state.goal}\n"]

    if state.acceptance_criteria:
        parts.append("## Acceptance Criteria")
        for i, ac in enumerate(state.acceptance_criteria, 1):
            parts.append(f"{i}. {ac}")
        parts.append("")

    if state.expected_ui:
        parts.append("## UI Specification (from Figma)")
        parts.append(f"Route: {state.expected_ui.route}")
        if state.expected_ui.elements:
            parts.append("\nElements:")
            for el in state.expected_ui.elements:
                parts.append(f"  - {el.role}: '{el.name}' (state: {el.state})"
                             + (f" [testid: {el.testid}]" if el.testid else ""))
        if state.expected_ui.flows:
            parts.append("\nFlows:")
            for flow in state.expected_ui.flows:
                parts.append(f"  - {flow.name}: {' → '.join(flow.steps)}")
        parts.append("")

    if state.app_url:
        parts.append(f"App URL: {state.app_url}")

    if memory_context:
        parts.append(f"\n{memory_context}")

    return "\n".join(parts)


def _parse_response(response: Any) -> list[TestCase]:
    """Parse the LLM response into a list of TestCase objects."""
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
                data = []
        else:
            data = json.loads(content)
    except (json.JSONDecodeError, IndexError):
        logger.error("Planner: could not parse JSON from response")
        return []

    # Handle both direct list and wrapped {"test_cases": [...]}
    if isinstance(data, dict):
        data = data.get("test_cases", data.get("plan", []))

    return [TestCase(**tc) if isinstance(tc, dict) else tc for tc in data]
