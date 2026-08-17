"""Jira intake adapter — reads a ticket via Atlassian MCP (no API key needed)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from qa_agent.intake.base import IntakeResult
from qa_agent.mcp.atlassian_client import ATLASSIAN_MCP_SERVER_CONFIG

logger = logging.getLogger(__name__)


class JiraIntake:
    """Reads a Jira issue via Atlassian MCP and extracts goal + acceptance criteria."""

    async def load(self, ref: str) -> IntakeResult:
        """Load a Jira issue by key (e.g. 'QA-123') and extract AC."""
        logger.info("Fetching Jira issue via MCP: %s", ref)

        client = MultiServerMCPClient(ATLASSIAN_MCP_SERVER_CONFIG)
        tools = await client.get_tools()

        # Find the getJiraIssue tool
        get_issue_tool = None
        for tool in tools:
            if "getJiraIssue" in tool.name or "get_jira_issue" in tool.name:
                get_issue_tool = tool
                break

        if not get_issue_tool:
            # Fallback: try a generic fetch tool
            for tool in tools:
                if "fetch" in tool.name.lower() or "issue" in tool.name.lower():
                    get_issue_tool = tool
                    break

        if not get_issue_tool:
            raise RuntimeError(
                f"Atlassian MCP has no getJiraIssue tool. "
                f"Available tools: {[t.name for t in tools]}"
            )

        # Invoke the tool to get the issue
        result = await get_issue_tool.ainvoke({"issueKey": ref})
        data = result if isinstance(result, dict) else json.loads(result)

        return self._parse_issue(data)

    def _parse_issue(self, data: dict[str, Any]) -> IntakeResult:
        """Extract goal, AC, and optional Figma link from a Jira issue payload."""
        fields = data.get("fields", data)

        summary = fields.get("summary", data.get("summary", ""))
        description = self._extract_text(fields.get("description", data.get("description")))
        ac_field = self._extract_text(fields.get("customfield_10035"))

        goal = summary

        acceptance_criteria: list[str] = []
        if ac_field:
            acceptance_criteria = self._split_criteria(ac_field)
        elif description:
            acceptance_criteria = self._split_criteria(description)

        figma_ref = self._find_figma_url(description or "")
        app_url = os.getenv("APP_BASE_URL")

        return IntakeResult(
            goal=goal,
            acceptance_criteria=acceptance_criteria,
            figma_ref=figma_ref,
            app_url=app_url,
        )

    @staticmethod
    def _extract_text(field: Any) -> str | None:
        """Extract plain text from a Jira ADF (Atlassian Document Format) or string field."""
        if field is None:
            return None
        if isinstance(field, str):
            return field
        if isinstance(field, dict) and "content" in field:
            parts: list[str] = []
            for block in field["content"]:
                if "content" in block:
                    for inline in block["content"]:
                        if inline.get("type") == "text":
                            parts.append(inline.get("text", ""))
                parts.append("\n")
            return "\n".join(parts).strip()
        return str(field)

    @staticmethod
    def _split_criteria(text: str) -> list[str]:
        """Split text into individual acceptance criteria lines."""
        lines: list[str] = []
        for line in text.split("\n"):
            line = line.strip()
            line = re.sub(r"^[-*•]\s*", "", line)
            line = re.sub(r"^\d+[.)]\s*", "", line)
            if line and len(line) > 5:
                lines.append(line)
        return lines

    @staticmethod
    def _find_figma_url(text: str) -> str | None:
        """Find a Figma URL in text."""
        match = re.search(r"https://(?:www\.)?figma\.com/[\w/\-?=&]+", text)
        return match.group(0) if match else None
