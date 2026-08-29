"""POM Generator — takes a DOM snapshot, calls LLM to produce a TypeScript Page Object class."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from qa_agent.config import get_model
from qa_agent.orchestrator.models import PageSnapshot

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "DOM_TO_POM.md").read_text()


def _route_to_class_name(route: str) -> str:
    """Convert a route like '/sign-in' to 'SignInPage'."""
    clean = route.strip("/") or "homepage"
    parts = re.split(r"[-_/]", clean)
    return "".join(p.capitalize() for p in parts if p) + "Page"


def _build_prompt(snapshot: PageSnapshot) -> str:
    """Build the human message prompt for POM generation."""
    parts = [
        f"## Page: {snapshot.page_config.name}",
        f"**Route:** `{snapshot.page_config.route}`",
        f"**URL:** `{snapshot.url}`",
        f"**Class name:** `{_route_to_class_name(snapshot.page_config.route)}`",
    ]

    if snapshot.page_config.regions:
        parts.append(f"\n**Regions of interest:** {', '.join(snapshot.page_config.regions)}")

    parts.append("\n## DOM Accessibility Tree Snapshot")
    parts.append("```")
    # Truncate very long snapshots to stay within token limits
    text = snapshot.snapshot_text
    if len(text) > 30000:
        text = text[:30000] + "\n... (truncated)"
    parts.append(text)
    parts.append("```")

    parts.append(
        "\nGenerate the TypeScript Page Object class for this page. "
        "Focus on interactive and assertable elements visible in the DOM."
    )

    return "\n".join(parts)


async def generate_pom(snapshot: PageSnapshot) -> str:
    """Generate a TypeScript Page Object class from a DOM snapshot.

    Args:
        snapshot: PageSnapshot with the accessibility tree text.

    Returns:
        TypeScript source code string for the Page Object class.
    """
    class_name = _route_to_class_name(snapshot.page_config.route)
    logger.info("POM Generator: generating %s from %s", class_name, snapshot.page_config.name)

    model = ChatAnthropic(
        model=get_model("generator"),
        temperature=0,
        max_tokens=8192,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_prompt(snapshot)),
    ]

    response = await model.ainvoke(messages)
    source = _extract_source(response)

    logger.info("POM Generator: produced %d bytes for %s", len(source), class_name)
    return source


def _extract_source(response: object) -> str:
    """Extract TypeScript source from the LLM response, stripping markdown fences."""
    content = response.content if hasattr(response, "content") else str(response)

    if isinstance(content, list):
        # Handle list of content blocks (e.g. TextBlock)
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
