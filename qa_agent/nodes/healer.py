"""Healer — re-grounds drifted locators in page objects.

Selectors & waits only — NEVER assertions. A guardrail validator enforces this.
After MAX_ATTEMPTS, escalates to Defect Report.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from qa_agent.config import get_model
from qa_agent.prompts.healer import SYSTEM_PROMPT
from qa_agent.state import QAState

logger = logging.getLogger(__name__)

# Patterns that indicate assertion code — Healer must never touch these
_ASSERTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bexpect\s*\("),
    re.compile(r"\.toBeVisible\s*\("),
    re.compile(r"\.toBeHidden\s*\("),
    re.compile(r"\.toBeEnabled\s*\("),
    re.compile(r"\.toBeDisabled\s*\("),
    re.compile(r"\.toHaveText\s*\("),
    re.compile(r"\.toHaveValue\s*\("),
    re.compile(r"\.toHaveURL\s*\("),
    re.compile(r"\.toHaveTitle\s*\("),
    re.compile(r"\.toHaveCount\s*\("),
    re.compile(r"\.toHaveAttribute\s*\("),
    re.compile(r"\.toContainText\s*\("),
    re.compile(r"\.toBeChecked\s*\("),
    re.compile(r"\.toBeTruthy\s*\("),
    re.compile(r"\.toBeFalsy\s*\("),
    re.compile(r"\.toEqual\s*\("),
    re.compile(r"\.toMatch\s*\("),
    re.compile(r"\.not\s*\."),
    re.compile(r"\bassert\b"),
]


class AssertionGuardError(Exception):
    """Raised when the Healer attempts to modify assertions."""


def validate_healer_diff(old_source: str, new_source: str) -> None:
    """Reject a Healer diff if it touches any assertion.

    Compares the assertion lines in old vs new source.
    Raises AssertionGuardError if any assertion line was added, removed, or modified.
    """
    old_assertions = _extract_assertion_lines(old_source)
    new_assertions = _extract_assertion_lines(new_source)

    if old_assertions != new_assertions:
        raise AssertionGuardError(
            f"Healer diff touches assertions — REJECTED.\n"
            f"Old assertions: {old_assertions}\n"
            f"New assertions: {new_assertions}"
        )


def _extract_assertion_lines(source: str) -> list[str]:
    """Extract all lines that contain assertion patterns, normalized."""
    lines = []
    for line in source.split("\n"):
        stripped = line.strip()
        if any(p.search(stripped) for p in _ASSERTION_PATTERNS):
            lines.append(stripped)
    return lines


async def healer(state: QAState) -> dict:
    """Fix a drifted locator in the page object and return patched source."""
    logger.info("Healer: attempt %d — fixing locator drift", state.attempts + 1)

    model = ChatAnthropic(
        model=get_model("healer"),
        temperature=0,
        max_tokens=8192,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_prompt(state)),
    ]

    response = await model.ainvoke(messages)
    result = _parse_response(response)

    patched_page_objects = result.get("page_objects", {})

    # Validate each patched page object against the guardrail
    validated_page_objects: dict[str, str] = {}
    for route, new_source in patched_page_objects.items():
        old_source = state.page_objects.get(route, "")
        try:
            validate_healer_diff(old_source, new_source)
            validated_page_objects[route] = new_source
            logger.info("Healer: patched page object for %s — guardrail passed", route)
        except AssertionGuardError as e:
            logger.error("Healer: guardrail REJECTED diff for %s: %s", route, e)
            # Keep the old source — don't apply the bad diff
            validated_page_objects[route] = old_source

    return {
        "page_objects": {**state.page_objects, **validated_page_objects},
        "attempts": 1,  # reducer will add this to current attempts
    }


def _build_prompt(state: QAState) -> str:
    """Build the human message prompt for the Healer."""
    parts = ["A test failed due to locator drift. Fix the broken locator(s) in the page object.\n"]

    if state.error:
        parts.append("## Error")
        parts.append(f"```\n{state.error}\n```\n")

    if state.dom_snapshot:
        snapshot = state.dom_snapshot[:3000]
        parts.append(f"## Current DOM (truncated)\n```html\n{snapshot}\n```\n")

    parts.append("## Current page objects")
    for route, source in state.page_objects.items():
        parts.append(f"\n### {route}")
        parts.append(f"```typescript\n{source}\n```")

    parts.append(f"\nAttempt: {state.attempts + 1}")
    parts.append("\nREMEMBER: Only fix locators and waits. NEVER change assertions.")

    return "\n".join(parts)


def _parse_response(response: Any) -> dict:
    """Parse the LLM response into patched page_objects."""
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
        logger.error("Healer: could not parse JSON from response")
        data = {}

    return {
        "page_objects": data.get("page_objects", {}),
        "changes": data.get("changes", []),
    }
