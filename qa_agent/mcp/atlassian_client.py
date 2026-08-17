"""Atlassian MCP client — connects to the Atlassian MCP server for Jira access."""

from __future__ import annotations

import logging
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

ATLASSIAN_MCP_SERVER_CONFIG = {
    "atlassian": {
        "command": "npx",
        "args": ["-y", "@anthropic-ai/atlassian-mcp-server"],
        "transport": "stdio",
    }
}


async def get_atlassian_tools(client: MultiServerMCPClient) -> list[Any]:
    """Return the list of tools exposed by the Atlassian MCP server."""
    tools = await client.get_tools()
    logger.info("Atlassian MCP tools available: %d", len(tools))
    for t in tools:
        logger.debug("  - %s", t.name)
    return tools


async def create_atlassian_client() -> MultiServerMCPClient:
    """Create and return a connected Atlassian MCP client."""
    client = MultiServerMCPClient(ATLASSIAN_MCP_SERVER_CONFIG)
    return client
