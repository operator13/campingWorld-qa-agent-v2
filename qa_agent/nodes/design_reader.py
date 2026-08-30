"""Step 1 · Design Reader — Figma MCP → ExpectedUI.

Optional step: skipped when a feature has no design (figma_ref is None).
The Planner then works from acceptance criteria alone.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from qa_agent.audit import AuditStore
from qa_agent.config import get_model
from pathlib import Path

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "DESIGN_READER.md").read_text()
from qa_agent.schemas.models import ExpectedUI, UIElement, UIFlow
from qa_agent.state import QAState

logger = logging.getLogger(__name__)


async def design_reader(state: QAState, *, tools: list[Any] | None = None) -> dict:
    """Read a Figma design and produce an ExpectedUI spec.

    If figma_ref is None, this step is skipped — returns empty updates.
    """
    if not state.figma_ref:
        logger.info("Design Reader: no figma_ref — skipping (Planner will use AC only)")
        return {}

    logger.info("Design Reader: reading Figma ref=%s", state.figma_ref)

    model = ChatAnthropic(
        model=get_model("design_reader"),
        temperature=0,
        max_tokens=4096,
    )

    # If MCP tools are provided, bind them
    if tools:
        model = model.bind_tools(tools)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_prompt(state)),
    ]

    response = await model.ainvoke(messages)
    AuditStore.record_llm_call(response, model=get_model("design_reader"))
    AuditStore.record_prompt_version(SYSTEM_PROMPT, "DESIGN_READER.md")
    AuditStore.record_prompt_data(
        raw_prompt=messages[-1].content,
        raw_response=response.content if hasattr(response, "content") else str(response),
    )
    result = _parse_response(response)

    return {
        "figma_spec": result.get("figma_spec"),
        "expected_ui": result.get("expected_ui"),
    }


def _build_prompt(state: QAState) -> str:
    """Build the human message prompt for the Design Reader."""
    parts = [
        f"Read the Figma design and produce a structured UI specification.",
        f"\nFigma reference: {state.figma_ref}",
        f"Goal: {state.goal}",
    ]
    if state.app_url:
        parts.append(f"App URL: {state.app_url}")
    if state.acceptance_criteria:
        parts.append(f"\nAcceptance criteria for context:")
        for ac in state.acceptance_criteria:
            parts.append(f"  - {ac}")
    return "\n".join(parts)


def _parse_response(response: Any) -> dict:
    """Parse the LLM response into figma_spec and ExpectedUI."""
    content = response.content if hasattr(response, "content") else str(response)

    # Try to extract JSON from the response
    try:
        if isinstance(content, str):
            # Find JSON block in the response
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]

            data = json.loads(json_str.strip())
        elif isinstance(content, list):
            # Tool call response
            for block in content:
                if hasattr(block, "text"):
                    data = json.loads(block.text)
                    break
            else:
                data = {}
        else:
            data = json.loads(content)
    except (json.JSONDecodeError, IndexError):
        logger.warning("Design Reader: could not parse JSON from response, using raw")
        data = {"route": "/", "elements": [], "flows": []}

    # Build ExpectedUI
    elements = [
        UIElement(**el) if isinstance(el, dict) else el
        for el in data.get("elements", [])
    ]
    flows = [
        UIFlow(**fl) if isinstance(fl, dict) else fl
        for fl in data.get("flows", [])
    ]

    expected_ui = ExpectedUI(
        route=data.get("route", "/"),
        elements=elements,
        flows=flows,
    )

    return {
        "figma_spec": data,
        "expected_ui": expected_ui,
    }
