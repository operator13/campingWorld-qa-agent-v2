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

from qa_agent.audit import AuditStore
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


class HardWaitGuardError(Exception):
    """Raised when the Healer adds a hard wait (page.waitForTimeout)."""


_HARD_WAIT_PATTERN = re.compile(r"page\.waitForTimeout\s*\(", re.I)


def validate_timing_fix_diff(old_source: str, new_source: str) -> None:
    """Reject a timing fix if it adds hard waits or modifies assertions.

    Allows: waitFor(), waitForSelector(), waitForLoadState()
    Blocks: page.waitForTimeout() (hard wait anti-pattern)
    Blocks: any assertion modification (same as locator fix guardrail)
    """
    validate_healer_diff(old_source, new_source)

    old_lines = set(old_source.split("\n"))
    for line in new_source.split("\n"):
        if line not in old_lines and _HARD_WAIT_PATTERN.search(line):
            raise HardWaitGuardError(
                f"Healer added page.waitForTimeout() — REJECTED (hard wait anti-pattern).\n"
                f"Line: {line.strip()}"
            )


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
    """Dispatch to the appropriate healing strategy based on failure class."""
    failure_class = state.failure_class or "locator_drift"

    if failure_class == "test_flake":
        return await _heal_timing(state)
    return await _heal_locator(state)


async def _heal_timing(state: QAState) -> dict:
    """Fix a timing/race condition failure by adding synchronization waits.

    Patches SPEC FILES (not POMs) — timing waits go where the interaction happens.
    """
    logger.info("Healer: attempt %d — fixing timing flake", state.attempts + 1)

    memory = MemoryStore()
    route = _extract_route(state)
    old_locator = extract_locator_from_error(state.error or "")
    element = _identify_element(old_locator)
    error_pattern = _extract_error_pattern(state.error or "")

    # --- Fast path: known timing fix ---
    known_fix = memory.get_known_timing_fix(route, element, error_pattern)
    if known_fix:
        spec_key = _find_spec_key(state)
        if spec_key and spec_key in state.test_code:
            try:
                patched = _apply_timing_known_fix(state.test_code[spec_key], known_fix)
                validate_timing_fix_diff(state.test_code[spec_key], patched)
                memory.record_healer_event("cache_hit")
                AuditStore.record_cache_hit(True)
                logger.info("Healer: applying known timing fix from memory for %s", element)
                return {
                    "test_code": {**state.test_code, spec_key: patched},
                    "attempts": 1,
                }
            except (AssertionGuardError, HardWaitGuardError):
                logger.warning("Healer: known timing fix failed guardrail — falling through to LLM")
                memory.mark_timing_fix_failed(route, element, error_pattern)
                memory.record_healer_event("cache_miss", miss_reason="guardrail_reject")
    else:
        memory.record_healer_event("cache_miss", miss_reason="key_not_found")

    # --- Slow path: LLM ---
    memory.record_healer_event("llm_call")
    memory_context = sanitize_text(
        memory.build_healer_timing_context(route, element), field_type="description"
    )

    model = ChatAnthropic(model=get_model("healer"), temperature=0, max_tokens=8192)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_timing_prompt(state, memory_context=memory_context)),
    ]

    response = await model.ainvoke(messages)
    AuditStore.record_llm_call(response, model=get_model("healer"))
    AuditStore.record_cache_hit(False)
    AuditStore.record_prompt_version(SYSTEM_PROMPT, "HEALER.md")
    result = _parse_timing_response(response)

    patched_specs = result.get("spec_files", {})
    changes = result.get("changes", [])

    # Validate each patched spec
    validated_specs: dict[str, str] = {}
    for spec_key, new_source in patched_specs.items():
        old_source = state.test_code.get(spec_key, "")
        try:
            validate_timing_fix_diff(old_source, new_source)
            validated_specs[spec_key] = new_source
            logger.info("Healer: patched spec %s — guardrail passed", spec_key)
        except (AssertionGuardError, HardWaitGuardError) as e:
            logger.error("Healer: timing fix guardrail REJECTED for %s: %s", spec_key, e)
            validated_specs[spec_key] = old_source

    # Record fixes as unverified
    for change in changes:
        memory.record_timing_fix(
            route=route,
            element=change.get("element", element),
            error_pattern=error_pattern,
            strategy=change.get("strategy", "A"),
            fix_description=change.get("fix", ""),
            success=False,
        )

    if state.error:
        memory.record_failure(
            error_signature=state.error,
            failure_class="test_flake",
            resolution="healed:timing_fix",
            route=route,
        )

    return {
        "test_code": {**state.test_code, **validated_specs},
        "attempts": 1,
    }


async def _heal_locator(state: QAState) -> dict:
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
                AuditStore.record_cache_hit(True)
                AuditStore.record_memory_context(
                    files_read=[f"locators/{route.strip('/')}.md" if route else "locators/ROOT.md"],
                )
                return {
                    "page_objects": {**state.page_objects, **patched},
                    "attempts": 1,
                }
            except AssertionGuardError:
                logger.warning("Healer: known fix touches assertions — marking failed, falling through to LLM")
                memory.mark_fix_failed(route, element, old_locator)
                memory.record_healer_event("cache_miss", miss_reason="guardrail_reject")
        else:
            memory.record_healer_event("cache_miss", miss_reason="key_not_found")
    else:
        memory.record_healer_event("cache_miss", miss_reason="no_locator")

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
    AuditStore.record_llm_call(response, model=get_model("healer"))
    AuditStore.record_cache_hit(False)
    AuditStore.record_prompt_version(SYSTEM_PROMPT, "HEALER.md")
    AuditStore.record_prompt_data(
        raw_prompt=messages[-1].content,
        raw_response=response.content if hasattr(response, "content") else str(response),
    )
    AuditStore.record_memory_context(
        files_read=[f"locators/{route.strip('/')}.md" if route else "locators/ROOT.md", "LESSONS.md"],
    )
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


# ---------------------------------------------------------------------------
# Timing fix helpers
# ---------------------------------------------------------------------------


def _extract_route(state: QAState) -> str:
    """Extract route from state (shared between locator and timing heal)."""
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
    return route


def _extract_error_pattern(error: str) -> str:
    """Extract the error pattern type for timing fix lookup."""
    if re.search(r"scrollIntoViewIfNeeded.*Timeout", error, re.I):
        return "scrollIntoViewIfNeeded_timeout"
    if re.search(r"locator\.click.*Timeout", error, re.I):
        return "click_timeout"
    if re.search(r"locator\.fill.*Timeout", error, re.I):
        return "fill_timeout"
    if re.search(r"waiting for.*visible", error, re.I):
        return "visibility_wait"
    if re.search(r"beforeEach.*Timeout", error, re.I):
        return "beforeEach_timeout"
    return "generic_timeout"


def _find_spec_key(state: QAState) -> str | None:
    """Find the spec file key in test_code that corresponds to the failed test."""
    if not state.test_code:
        return None
    if state.run_results and state.run_results.failed_cases:
        for key in state.test_code:
            if any(fc in key for fc in state.run_results.failed_cases):
                return key
    return next(iter(state.test_code), None)


def _apply_timing_known_fix(source: str, fix_description: str) -> str:
    """Apply a known timing fix based on its description.

    Looks for the interaction line and adds waitFor before it.
    """
    # Parse the fix description for the wait line to add
    # Format: "waitFor({ state: 'visible', timeout: 20000 })"
    if "waitFor" not in fix_description:
        return source

    lines = source.split("\n")
    new_lines = []
    for line in lines:
        stripped = line.strip()
        # Add waitFor before scrollIntoViewIfNeeded, click, fill
        if (re.search(r"\.scrollIntoViewIfNeeded\s*\(", stripped) or
                re.search(r"\.(click|fill|type)\s*\(", stripped)):
            if "waitFor" not in stripped:
                indent = line[:len(line) - len(line.lstrip())]
                # Extract the element reference (everything before .scrollIntoViewIfNeeded/.click)
                el_match = re.match(r"(\s*(?:await\s+)?)(.+?)\.(?:scrollIntoViewIfNeeded|click|fill|type)\s*\(", line)
                if el_match:
                    prefix = el_match.group(1)
                    element_ref = el_match.group(2)
                    new_lines.append(f"{prefix}{element_ref}.waitFor({{ state: 'visible', timeout: 20_000 }});")
        new_lines.append(line)
    return "\n".join(new_lines)


def _build_timing_prompt(state: QAState, memory_context: str = "") -> str:
    """Build the human message prompt for timing fixes."""
    parts = [
        "A test failed due to a timing/race condition (test_flake). "
        "The locator is CORRECT — the element just wasn't ready when the test interacted with it.\n"
    ]

    if state.error:
        parts.append(f"## Error\n```\n{state.error}\n```\n")

    if memory_context:
        parts.append(memory_context + "\n")

    if state.dom_snapshot:
        parts.append(f"## Current DOM (truncated)\n```html\n{state.dom_snapshot[:3000]}\n```\n")

    parts.append("## Spec files")
    for key, source in state.test_code.items():
        parts.append(f"\n### {key}\n```typescript\n{source}\n```")

    parts.append(f"\nAttempt: {state.attempts + 1}")
    parts.append(
        "\nREMEMBER: Add waitFor() before the failing interaction. "
        "NEVER add page.waitForTimeout(). NEVER change assertions. "
        "DO NOT change any locators."
    )

    return "\n".join(parts)


def _parse_timing_response(response: Any) -> dict:
    """Parse the LLM response for timing fixes."""
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
        logger.error("Healer: could not parse timing fix JSON")
        data = {}

    return {
        "spec_files": data.get("spec_files", {}),
        "changes": data.get("changes", []),
    }
