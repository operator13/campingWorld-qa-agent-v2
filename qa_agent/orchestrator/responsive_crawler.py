"""Responsive crawler — crawls pages at desktop and mobile viewports."""

from __future__ import annotations

import logging
from typing import Any

from qa_agent.orchestrator.crawler import PageCrawler
from qa_agent.orchestrator.models import PageConfig, PageSnapshot

logger = logging.getLogger(__name__)

VIEWPORTS = {
    "desktop": {"width": 1280, "height": 720},
    "mobile": {"width": 375, "height": 812},
}


class ResponsiveCrawler:
    """Crawls a page at multiple viewport sizes."""

    def __init__(self, call_tool_fn: Any) -> None:
        self._call_tool = call_tool_fn
        self._crawler = PageCrawler(call_tool_fn)

    async def crawl_responsive(
        self,
        config: PageConfig,
        viewports: list[str] | None = None,
    ) -> list[PageSnapshot]:
        """Crawl a page at each viewport size.

        Args:
            config: Page configuration.
            viewports: List of viewport names (default: ["desktop", "mobile"]).

        Returns:
            List of PageSnapshot, one per viewport.
        """
        viewport_names = viewports or ["desktop", "mobile"]
        snapshots = []

        for vp_name in viewport_names:
            vp = VIEWPORTS.get(vp_name)
            if not vp:
                logger.warning("Unknown viewport: %s, skipping", vp_name)
                continue

            logger.info("ResponsiveCrawler: %s at %s (%dx%d)", config.name, vp_name, vp["width"], vp["height"])

            # Resize browser
            await self._call_tool("browser_resize", vp)

            # Crawl at this viewport
            snapshot = await self._crawler.crawl_page(config)
            snapshot.viewport = vp_name

            snapshots.append(snapshot)

        return snapshots

    async def reset_viewport(self) -> None:
        """Reset to desktop viewport."""
        await self._call_tool("browser_resize", VIEWPORTS["desktop"])
