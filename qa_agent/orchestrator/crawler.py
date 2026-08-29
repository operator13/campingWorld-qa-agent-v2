"""Page crawler — navigates to a URL via Playwright MCP, dismisses popups, captures DOM snapshot."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from qa_agent.orchestrator.models import PageConfig, PageSnapshot
from qa_agent.orchestrator.popup_handler import PopupHandler
from qa_agent.orchestrator.site_map import BASE_URL

logger = logging.getLogger(__name__)


class PageCrawler:
    """Crawls a single page using Playwright MCP tools."""

    def __init__(self, call_tool_fn: Any) -> None:
        """
        Args:
            call_tool_fn: async callable to invoke MCP tools.
                          Signature: async (tool_name: str, args: dict) -> Any
        """
        self._call_tool = call_tool_fn
        self.popup_handler = PopupHandler(call_tool_fn)

    async def crawl_page(self, config: PageConfig) -> PageSnapshot:
        """Navigate to a page, dismiss popups, execute prerequisites, and snapshot the DOM.

        Args:
            config: Page configuration defining URL, prerequisites, etc.

        Returns:
            PageSnapshot with the accessibility tree text.
        """
        url = self._resolve_url(config)
        logger.info("Crawling: %s (%s)", config.name, url)

        # 1. Navigate to the page
        await self._call_tool("browser_navigate", {"url": url})

        # 2. Dismiss any popups (cookie consent, promo modals, etc.)
        dismissed = await self.popup_handler.dismiss_all()
        if dismissed:
            logger.info("Dismissed %d popup(s) on %s", dismissed, config.name)

        # 3. Execute prerequisites (hover, click, fill, etc.)
        for prereq in config.prerequisites:
            await self._execute_prerequisite(prereq)

        # 4. Snapshot the DOM (accessibility tree)
        snapshot_result = await self._call_tool("browser_snapshot", {})
        snapshot_text = str(snapshot_result) if snapshot_result else ""

        # 5. Take a screenshot for reference
        screenshot_path = None
        try:
            screenshot_result = await self._call_tool("browser_take_screenshot", {})
            if screenshot_result:
                screenshot_path = str(screenshot_result)
        except Exception:
            logger.debug("Screenshot capture failed for %s", config.name)

        return PageSnapshot(
            page_config=config,
            url=url,
            snapshot_text=snapshot_text,
            screenshot_path=screenshot_path,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
        )

    async def _execute_prerequisite(self, prereq: dict[str, str]) -> None:
        """Execute a single prerequisite action before snapshotting."""
        action = prereq.get("action", "")
        target = prereq.get("target", "")
        value = prereq.get("value", "")

        logger.debug("Executing prerequisite: %s on '%s'", action, target)

        if action == "hover":
            await self._call_tool("browser_hover", {"element": target})
        elif action == "click":
            await self._call_tool("browser_click", {"element": target})
        elif action == "fill":
            await self._call_tool("browser_click", {"element": target})
            await self._call_tool("browser_type", {"text": value})
        elif action == "add_to_cart":
            # Navigate to a product, add it to cart — handled by cart_handler in Phase O4
            logger.info("add_to_cart prerequisite — will be handled by cart_handler")
        else:
            logger.warning("Unknown prerequisite action: %s", action)

    def _resolve_url(self, config: PageConfig) -> str:
        """Build the full URL for a page config."""
        if config.url.startswith("http"):
            return config.url

        # For dynamic pages with sample URLs, use the first sample
        if config.dynamic_url and config.sample_urls:
            return BASE_URL + config.sample_urls[0]

        return BASE_URL + config.url
