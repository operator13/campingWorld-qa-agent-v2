"""Jira defect surface — create/dedup bug tickets via Atlassian MCP.

Deduplication uses a failure fingerprint: hash of (route + assertion + error class).
Same failure → same ticket, never filed twice.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Optional

from langchain_mcp_adapters.client import MultiServerMCPClient

from qa_agent.mcp.atlassian_client import ATLASSIAN_MCP_SERVER_CONFIG
from qa_agent.schemas.models import RunResult

logger = logging.getLogger(__name__)


def compute_fingerprint(
    route: str,
    error_class: str,
    failed_cases: list[str],
) -> str:
    """Compute a stable dedup fingerprint for a failure.

    Hash of (route + error_class + sorted failed case IDs).
    Same underlying bug → same fingerprint → one Jira ticket.
    """
    key = f"{route}|{error_class}|{','.join(sorted(failed_cases))}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class JiraDefectSurface:
    """Creates and deduplicates Jira bug tickets via Atlassian MCP."""

    def __init__(self, project_key: Optional[str] = None) -> None:
        self.project_key = project_key or os.getenv("JIRA_PROJECT_KEY", "QA")
        self._tools: list[Any] | None = None

    async def _get_tools(self) -> list[Any]:
        """Connect to Atlassian MCP and cache the tools."""
        if self._tools is None:
            client = MultiServerMCPClient(ATLASSIAN_MCP_SERVER_CONFIG)
            self._tools = await client.get_tools()
        return self._tools

    async def _find_tool(self, name_fragment: str) -> Any:
        """Find an MCP tool by name fragment."""
        tools = await self._get_tools()
        for tool in tools:
            if name_fragment in tool.name:
                return tool
        raise RuntimeError(
            f"Atlassian MCP tool '{name_fragment}' not found. "
            f"Available: {[t.name for t in tools]}"
        )

    @property
    def is_configured(self) -> bool:
        """Check if Atlassian MCP can be reached (always true — auth is handled by MCP)."""
        return True

    async def find_existing(self, fingerprint: str) -> Optional[str]:
        """Search for an existing Jira issue with this fingerprint."""
        try:
            search_tool = await self._find_tool("searchJiraIssue")
            jql = f'project = {self.project_key} AND labels = "qa-agent-fp-{fingerprint}"'
            result = await search_tool.ainvoke({"jql": jql, "maxResults": 1})
            data = result if isinstance(result, dict) else json.loads(result)

            issues = data.get("issues", [])
            if issues:
                return issues[0].get("key")
        except Exception as e:
            logger.warning("Jira MCP search failed: %s", e)

        return None

    async def create_defect(
        self,
        goal: str,
        fingerprint: str,
        failure_class: str,
        confidence: float,
        error: str,
        run_results: Optional[RunResult] = None,
        attempts: int = 0,
    ) -> Optional[str]:
        """Create a Jira bug ticket via MCP."""
        try:
            create_tool = await self._find_tool("createJiraIssue")

            summary = f"[QA Agent] {goal}"
            if len(summary) > 255:
                summary = summary[:252] + "..."

            failed_cases = run_results.failed_cases if run_results else []
            logs_preview = run_results.logs[:2000] if run_results else ""

            description = (
                f"## Defect Report\n\n"
                f"**Failure class:** {failure_class} (confidence: {confidence:.2f})\n"
                f"**Heal attempts:** {attempts}\n"
                f"**Failed cases:** {', '.join(failed_cases)}\n\n"
                f"### Error\n```\n{error[:3000]}\n```\n\n"
                f"### Logs\n```\n{logs_preview}\n```"
            )

            result = await create_tool.ainvoke({
                "projectKey": self.project_key,
                "summary": summary,
                "description": description,
                "issueType": "Bug",
                "labels": [
                    "qa-agent",
                    f"qa-agent-fp-{fingerprint}",
                    f"qa-agent-class-{failure_class}",
                ],
            })

            data = result if isinstance(result, dict) else json.loads(result)
            issue_key = data.get("key", "unknown")
            logger.info("Created Jira defect via MCP: %s", issue_key)
            return issue_key
        except Exception as e:
            logger.error("Failed to create Jira defect via MCP: %s", e)
            return None

    async def file_or_dedup(
        self,
        goal: str,
        route: str,
        failure_class: str,
        confidence: float,
        error: str,
        run_results: Optional[RunResult] = None,
        attempts: int = 0,
    ) -> dict[str, Any]:
        """File a defect or return the existing one if it's a duplicate."""
        failed_cases = run_results.failed_cases if run_results else []
        fingerprint = compute_fingerprint(route, failure_class, failed_cases)

        existing = await self.find_existing(fingerprint)
        if existing:
            logger.info("Dedup: defect already filed as %s (fp=%s)", existing, fingerprint)
            return {"action": "deduped", "issue_key": existing, "fingerprint": fingerprint}

        issue_key = await self.create_defect(
            goal=goal,
            fingerprint=fingerprint,
            failure_class=failure_class,
            confidence=confidence,
            error=error,
            run_results=run_results,
            attempts=attempts,
        )

        if issue_key:
            return {"action": "created", "issue_key": issue_key, "fingerprint": fingerprint}
        return {"action": "error", "issue_key": None, "fingerprint": fingerprint}
