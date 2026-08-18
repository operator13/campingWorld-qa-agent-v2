"""Healer — re-grounds drifted locators in page objects.

Selectors & waits only — NEVER assertions. A guardrail validator enforces this.
After MAX_ATTEMPTS, escalates to Defect Report.

Memory-enhanced: checks for known fixes before calling the LLM.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from qa_agent.config import get_model
from qa_agent.memory import MemoryStore, extract_locator_from_error
from qa_agent.sanitizer import sanitize_text
from pathlib import Path

_SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "HEALER.md"
SYSTEM_PROMPT = _SYSTEM_PROMPT_PATH.read_text()
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


def _apply_known_fix(
    old_locator: str,
    new_locator: str,
    page_objects: dict[str, str],
) -> dict[str, str]:
    """Apply a known locator fix by replacing old_locator with new_locator in page objects."""
    patched = {}
    for route, source in page_objects.items():
        patched[route] = source.replace(old_locator, new_locator)
    return patched


async def healer(state: QAState) -> dict:
    """Fix a drifted locator in the page object and return patched source.

    Memory-enhanced flow:
    1. Extract broken locator from error
    2. Check memory for a known fix → apply instantly (no LLM)
    3. If no known fix → ask LLM with locator history context
    4. Record the fix in memory for next time
    """
    logger.info("Healer: attempt %d — fixing locator drift", state.attempts + 1)

    memory = MemoryStore()
    # Use route from the first failed test case, not just the first planned test
    route = "/"
    if state.run_results and state.run_results.failed_cases and state.plan:
        failed_id = state.run_results.failed_cases[0]
        for tc in state.plan:
            if tc.id == failed_id:
                route = tc.route
                break
        else:
            route = state.plan[0].route
    elif state.plan:
        route = state.plan[0].route
    old_locator = extract_locator_from_error(state.error or "")
    element = _identify_element(old_locator)

    # --- Fast path: known fix from memory ---
    if old_locator:
        known_new = memory.get_known_fix(route, element, old_locator)
        if known_new:
            patched = _apply_known_fix(old_locator, known_new, state.page_objects)

            # MUST validate through guardrail
            try:
                for r, new_src in patched.items():
                    validate_healer_diff(state.page_objects.get(r, ""), new_src)
                logger.info("Healer: applying known fix from memory (%s → %s)", old_locator, known_new)
                memory.record_healer_event("cache_hit")
                return {
                    "page_objects": {**state.page_objects, **patched},
                    "attempts": 1,
                }
            except AssertionGuardError:
                logger.warning("Healer: known fix touches assertions — marking failed, falling through to LLM")
                memory.mark_fix_failed(route, element, old_locator)

    # --- Slow path: ask LLM, with memory context + lessons ---
    memory.record_healer_event("llm_call")
    memory_context = sanitize_text(memory.build_healer_memory_context(route, element), field_type="description")
    lessons_context = sanitize_text(memory.build_lessons_context(route=route, max_tokens=250), field_type="description")
    if lessons_context:
        memory_context = (memory_context + "\n\n" + lessons_context).strip()

    model = ChatAnthropic(
        model=get_model("healer"),
        temperature=0,
        max_tokens=8192,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_prompt(state, memory_context=memory_context)),
    ]

    response = await model.ainvoke(messages)
    result = _parse_response(response)

    patched_page_objects = result.get("page_objects", {})
    changes = result.get("changes", [])

    # Validate each patched page object against the guardrail
    validated_page_objects: dict[str, str] = {}
    for r, new_source in patched_page_objects.items():
        old_source = state.page_objects.get(r, "")
        try:
            validate_healer_diff(old_source, new_source)
            validated_page_objects[r] = new_source
            logger.info("Healer: patched page object for %s — guardrail passed", r)
        except AssertionGuardError as e:
            logger.error("Healer: guardrail REJECTED diff for %s: %s", r, e)
            validated_page_objects[r] = old_source

    # Record fixes as UNVERIFIED — success=False until executor confirms
    # The executor will mark them as success=True if the re-run passes
    for change in changes:
        old_loc = change.get("old_locator", "")
        new_loc = change.get("new_locator", "")
        reason = change.get("reason", "")
        if old_loc and new_loc:
            memory.record_locator_change(route, element, old_loc, new_loc, reason, success=False)

    # Record failure pattern
    if state.error:
        memory.record_failure(
            error_signature=state.error,
            failure_class="locator_drift",
            resolution="healed:locator_update",
            route=route,
        )

    return {
        "page_objects": {**state.page_objects, **validated_page_objects},
        "attempts": 1,  # reducer will add this to current attempts
    }


def _identify_element(locator: str | None) -> str:
    """Derive an element identifier from a locator string."""
    if not locator:
        return "unknown"

    # Try to extract the name or testid
    name_match = re.search(r"name:\s*['\"]([^'\"]+)['\"]", locator)
    if name_match:
        return name_match.group(1)

    testid_match = re.search(r"getByTestId\(['\"]([^'\"]+)['\"]\)", locator)
    if testid_match:
        return testid_match.group(1)

    text_match = re.search(r"getByText\(['\"]([^'\"]+)['\"]\)", locator)
    if text_match:
        return text_match.group(1)

    return "unknown"


def _build_prompt(state: QAState, memory_context: str = "") -> str:
    """Build the human message prompt for the Healer."""
    parts = ["A test failed due to locator drift. Fix the broken locator(s) in the page object.\n"]

    if state.error:
        parts.append("## Error")
        parts.append(f"```\n{state.error}\n```\n")

    if memory_context:
        parts.append(memory_context)
        parts.append("")

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
