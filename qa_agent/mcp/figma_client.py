"""Figma MCP client — connects to the Figma developer MCP server."""

from __future__ import annotations

import logging
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

FIGMA_MCP_SERVER_CONFIG = {
    "figma": {
        "url": "http://127.0.0.1:3333/mcp",
        "transport": "streamable_http",
    }
}


async def get_figma_tools(client: MultiServerMCPClient) -> list[Any]:
    """Return the list of tools exposed by the Figma MCP server."""
    tools = await client.get_tools()
    figma_tools = [t for t in tools if "figma" in getattr(t, "name", "").lower()]
    logger.info("Figma MCP tools available: %d", len(figma_tools))
    for t in figma_tools:
        logger.debug("  - %s", t.name)
    return figma_tools


async def create_figma_client() -> MultiServerMCPClient:
    """Create and return a connected Figma MCP client."""
    client = MultiServerMCPClient(FIGMA_MCP_SERVER_CONFIG)
    return client
