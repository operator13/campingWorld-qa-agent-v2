"""Dynamic page resolver — discovers real URLs for pages with dynamic segments."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class DynamicPageResolver:
    """Resolves dynamic page URLs by crawling listing pages and extracting real links."""

    def __init__(self, call_tool_fn: Any, base_url: str = "https://www.campingworld.com") -> None:
        self._call_tool = call_tool_fn
        self._base_url = base_url
        self._cache: dict[str, str] = {}

    async def resolve(self, page_key: str) -> str | None:
        """Resolve a dynamic URL for a given page type.

        Args:
            page_key: One of 'product_detail', 'rv_detail', etc.

        Returns:
            Full URL string, or None if resolution failed.
        """
        if page_key in self._cache:
            return self._cache[page_key]

        resolver_map = {
            "product_detail": self._resolve_product_url,
            "rv_detail": self._resolve_rv_url,
        }

        resolver = resolver_map.get(page_key)
        if not resolver:
            logger.warning("DynamicPageResolver: no resolver for '%s'", page_key)
            return None

        url = await resolver()
        if url:
            self._cache[page_key] = url
        return url

    async def _resolve_product_url(self) -> str | None:
        """Navigate to a category page, extract the first product link."""
        logger.info("DynamicPageResolver: resolving product URL from /rv-parts")

        await self._call_tool("browser_navigate", {"url": f"{self._base_url}/rv-parts"})

        snapshot = await self._call_tool("browser_snapshot", {})
        snapshot_text = str(snapshot) if snapshot else ""

        # Look for product links in the snapshot
        url = self._extract_link(snapshot_text, pattern=r"/product/[^\s\"']+")
        if url:
            full_url = self._base_url + url if not url.startswith("http") else url
            logger.info("DynamicPageResolver: resolved product URL: %s", full_url)
            return full_url

        # Fallback: try clicking the first product link and capturing the URL
        try:
            await self._call_tool("browser_click", {"element": "product"})
            snapshot_after = await self._call_tool("browser_snapshot", {})
            # The URL is now the product page
            snapshot_text_after = str(snapshot_after) if snapshot_after else ""
            url = self._extract_link(snapshot_text_after, pattern=r"/product/[^\s\"']+")
            if url:
                return self._base_url + url if not url.startswith("http") else url
        except Exception:
            logger.debug("DynamicPageResolver: click fallback failed for product")

        logger.warning("DynamicPageResolver: could not resolve product URL")
        return None

    async def _resolve_rv_url(self) -> str | None:
        """Navigate to RV listings, extract the first RV detail link."""
        logger.info("DynamicPageResolver: resolving RV URL from /rvs-for-sale")

        await self._call_tool("browser_navigate", {"url": f"{self._base_url}/rvs-for-sale"})

        snapshot = await self._call_tool("browser_snapshot", {})
        snapshot_text = str(snapshot) if snapshot else ""

        url = self._extract_link(snapshot_text, pattern=r"/rvs-for-sale/[^\s\"']+")
        if url:
            full_url = self._base_url + url if not url.startswith("http") else url
            logger.info("DynamicPageResolver: resolved RV URL: %s", full_url)
            return full_url

        logger.warning("DynamicPageResolver: could not resolve RV listing URL")
        return None

    def _extract_link(self, text: str, pattern: str) -> str | None:
        """Extract the first URL matching a pattern from snapshot text."""
        match = re.search(pattern, text)
        if match:
            return match.group(0)
        return None

    def clear_cache(self) -> None:
        """Clear the resolved URL cache."""
        self._cache.clear()
