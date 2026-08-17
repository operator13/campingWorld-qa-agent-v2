"""Playwright MCP client — connects to the Playwright MCP server."""

from __future__ import annotations

import logging
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

PLAYWRIGHT_MCP_SERVER_CONFIG = {
    "playwright": {
        "command": "npx",
        "args": ["@playwright/mcp@latest"],
        "transport": "stdio",
    }
}


async def get_playwright_tools(client: MultiServerMCPClient) -> list[Any]:
    """Return the list of tools exposed by the Playwright MCP server."""
    tools = await client.get_tools()
    pw_tools = [t for t in tools if "playwright" in getattr(t, "name", "").lower()
                or "browser" in getattr(t, "name", "").lower()]
    # If no name-filtered tools, return all (Playwright MCP may use different names)
    if not pw_tools:
        pw_tools = tools
    logger.info("Playwright MCP tools available: %d", len(pw_tools))
    for t in pw_tools:
        logger.debug("  - %s", t.name)
    return pw_tools


async def create_playwright_client() -> MultiServerMCPClient:
    """Create and return a connected Playwright MCP client."""
    client = MultiServerMCPClient(PLAYWRIGHT_MCP_SERVER_CONFIG)
    return client
