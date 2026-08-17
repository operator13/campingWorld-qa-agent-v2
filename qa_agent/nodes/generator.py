"""Step 3 · Generator — plan + figma_route_map → page objects + test code.

Builds a page object per route (locators + actions) and the test files that
call them — resilient role/text/testid locators, web-first assertions, no
inline selectors.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from qa_agent.config import FIGMA_ROUTE_MAP, get_model
from qa_agent.prompts.generator import SYSTEM_PROMPT
from qa_agent.state import QAState

logger = logging.getLogger(__name__)


async def generator(state: QAState) -> dict:
    """Generate page objects and test specs from the test plan."""
    logger.info("Generator: building tests for %d case(s)", len(state.plan))

    model = ChatAnthropic(
        model=get_model("generator"),
        temperature=0,
        max_tokens=16384,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_prompt(state)),
    ]

    response = await model.ainvoke(messages)
    result = _parse_response(response)

    page_objects = result.get("page_objects", {})
    test_code = result.get("test_code", {})

    logger.info(
        "Generator: produced %d page object(s) and %d test file(s)",
        len(page_objects),
        len(test_code),
    )

    return {
        "page_objects": page_objects,
        "test_code": test_code,
    }


def _build_prompt(state: QAState) -> str:
    """Build the human message prompt for the Generator."""
    parts = [f"Generate Playwright TypeScript page objects and tests for: {state.goal}\n"]

    # Test plan
    parts.append("## Test Plan")
    for tc in state.plan:
        parts.append(f"\n### {tc.id}: {tc.title}")
        parts.append(f"Feature: {tc.feature} | Route: {tc.route} | Tags: {tc.tags}")
        parts.append("Steps:")
        for i, step in enumerate(tc.steps, 1):
            parts.append(f"  {i}. {step}")
        parts.append("Expected:")
        for exp in tc.expected:
            parts.append(f"  - {exp}")

    # Route map for testid conventions
    if FIGMA_ROUTE_MAP:
        parts.append("\n## Route → testid mapping")
        for node_id, mapping in FIGMA_ROUTE_MAP.items():
            parts.append(f"  {node_id}: route={mapping.route}, prefix={mapping.testid_prefix}")

    # UI spec for grounding selectors
    if state.expected_ui:
        parts.append("\n## UI Elements (for selector grounding)")
        for el in state.expected_ui.elements:
            line = f"  - {el.role}: '{el.name}'"
            if el.testid:
                line += f" [data-testid='{el.testid}']"
            parts.append(line)

    if state.app_url:
        parts.append(f"\nBase URL: {state.app_url}")

    return "\n".join(parts)


def _parse_response(response: Any) -> dict:
    """Parse the LLM response into page_objects and test_code dicts."""
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
                data = {"page_objects": {}, "test_code": {}}
        else:
            data = json.loads(content)
    except (json.JSONDecodeError, IndexError):
        logger.error("Generator: could not parse JSON from response")
        data = {"page_objects": {}, "test_code": {}}

    return {
        "page_objects": data.get("page_objects", {}),
        "test_code": data.get("test_code", {}),
    }
