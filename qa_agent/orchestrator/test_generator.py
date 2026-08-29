"""Test Generator — takes POM source + page context, calls LLM to produce Playwright test spec."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from qa_agent.config import get_model
from qa_agent.orchestrator.models import PageConfig, PageSnapshot
from qa_agent.orchestrator.scenario_templates import SCENARIO_TEMPLATES

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "POM_TO_TESTS.md").read_text()


def _route_to_spec_filename(route: str) -> str:
    """Convert a route like '/sign-in' to 'sign-in.spec.ts'."""
    clean = route.strip("/") or "homepage"
    # Replace slashes with hyphens for nested routes
    clean = clean.replace("/", "-")
    return f"{clean}.spec.ts"


def _route_to_class_name(route: str) -> str:
    """Convert a route like '/sign-in' to 'SignInPage'."""
    clean = route.strip("/") or "homepage"
    parts = re.split(r"[-_/]", clean)
    return "".join(p.capitalize() for p in parts if p) + "Page"


def _build_prompt(
    pom_source: str,
    config: PageConfig,
    snapshot: PageSnapshot,
    scenarios: list[str],
) -> str:
    """Build the human message prompt for test generation."""
    class_name = _route_to_class_name(config.route)

    parts = [
        f"## Page: {config.name}",
        f"**Page type:** {config.name}",
        f"**Route:** `{config.route}`",
        f"**POM class:** `{class_name}`",
        f"**POM import path:** `../page_objects/{class_name}`",
    ]

    parts.append("\n## Page Object Source")
    parts.append("```typescript")
    parts.append(pom_source)
    parts.append("```")

    parts.append("\n## Test Scenarios to Cover")
    for i, scenario in enumerate(scenarios, 1):
        parts.append(f"{i}. {scenario}")

    # Include truncated DOM for additional context
    parts.append("\n## DOM Snapshot (for context)")
    parts.append("```")
    dom_text = snapshot.snapshot_text
    if len(dom_text) > 15000:
        dom_text = dom_text[:15000] + "\n... (truncated)"
    parts.append(dom_text)
    parts.append("```")

    parts.append(
        "\nGenerate the Playwright test spec file. "
        "Use the Page Object methods and locators — do NOT use inline selectors."
    )

    return "\n".join(parts)


async def generate_tests(
    pom_source: str,
    config: PageConfig,
    snapshot: PageSnapshot,
    scenarios: list[str] | None = None,
) -> str:
    """Generate a Playwright test spec from a POM and page context.

    Args:
        pom_source: TypeScript source of the Page Object class.
        config: Page configuration.
        snapshot: DOM snapshot for additional context.
        scenarios: Optional override for test scenarios (defaults to template).

    Returns:
        TypeScript source code string for the test spec file.
    """
    # Use template scenarios if not explicitly provided
    if scenarios is None:
        # Try to find matching template by site_map key
        page_key = _find_page_key(config.name)
        scenarios = SCENARIO_TEMPLATES.get(page_key, [
            f"{config.name} page renders correctly",
            f"key elements on {config.name} are visible",
            f"navigation from {config.name} works",
        ])

    class_name = _route_to_class_name(config.route)
    logger.info("Test Generator: generating tests for %s (%d scenarios)", class_name, len(scenarios))

    model = ChatAnthropic(
        model=get_model("generator"),
        temperature=0,
        max_tokens=8192,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_prompt(pom_source, config, snapshot, scenarios)),
    ]

    response = await model.ainvoke(messages)
    source = _extract_source(response)

    logger.info("Test Generator: produced %d bytes for %s", len(source), class_name)
    return source


def _find_page_key(page_name: str) -> str:
    """Find the scenario template key from a page name."""
    # Normalize: "Product Detail Page" → "product_detail"
    normalized = page_name.lower().replace(" ", "_").replace("-", "_")
    # Remove common suffixes
    for suffix in ["_page", "_pages"]:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]

    # Direct match
    if normalized in SCENARIO_TEMPLATES:
        return normalized

    # Fuzzy match: check if any key is a substring
    for key in SCENARIO_TEMPLATES:
        if key in normalized or normalized in key:
            return key

    return normalized


def _extract_source(response: object) -> str:
    """Extract TypeScript source from the LLM response, stripping markdown fences."""
    content = response.content if hasattr(response, "content") else str(response)

    if isinstance(content, list):
        for block in content:
            if hasattr(block, "text"):
                content = block.text
                break
        else:
            content = str(content)

    # Strip markdown code fences if present
    if "```typescript" in content:
        content = content.split("```typescript", 1)[1].split("```", 1)[0]
    elif "```ts" in content:
        content = content.split("```ts", 1)[1].split("```", 1)[0]
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0]

    return content.strip()
