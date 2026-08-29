"""Memory integration — updates APP_STRUCTURE.md with discovered routes and elements."""

from __future__ import annotations

import logging
import re

from qa_agent.memory import MemoryStore
from qa_agent.orchestrator.models import GeneratedOutput

logger = logging.getLogger(__name__)


def update_memory_from_crawl(outputs: list[GeneratedOutput]) -> int:
    """Update APP_STRUCTURE.md with routes and testids discovered during crawl.

    Args:
        outputs: List of GeneratedOutput from the orchestrator.

    Returns:
        Number of routes updated.
    """
    store = MemoryStore()
    updated = 0

    for output in outputs:
        route = output.page_config.route
        testids = extract_testids(output.pom_source)
        components = extract_components(output.pom_source)

        logger.info(
            "Memory: updating route %s — %d testids, %d components",
            route,
            len(testids),
            len(components),
        )

        store.update_route(
            route=route,
            testids=testids if testids else None,
            components=components if components else None,
        )
        updated += 1

    logger.info("Memory: updated %d route(s) in APP_STRUCTURE.md", updated)
    return updated


def extract_testids(pom_source: str) -> list[str]:
    """Extract data-testid values from a POM source file.

    Looks for getByTestId('...') patterns and extracts the testid strings.
    """
    pattern = r"getByTestId\(['\"]([^'\"]+)['\"]\)"
    matches = re.findall(pattern, pom_source)
    return list(dict.fromkeys(matches))  # deduplicate, preserve order


def extract_components(pom_source: str) -> list[str]:
    """Extract component/region names from POM source comment blocks.

    Looks for '// RegionName' comment patterns used to group locators.
    """
    pattern = r"^\s*//\s+(\w[\w\s]*\w)\s*$"
    matches = re.findall(pattern, pom_source, re.MULTILINE)
    return list(dict.fromkeys(matches))
