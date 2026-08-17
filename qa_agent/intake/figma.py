"""Figma intake adapter — reads a frame/file and derives a presentational spec."""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

from qa_agent.intake.base import IntakeResult

logger = logging.getLogger(__name__)


class FigmaIntake:
    """Reads a Figma frame and derives goal + acceptance criteria from the design.

    Uses the Figma REST API (not MCP) for intake — MCP is used later by
    the Design Reader node for the full structured spec.
    """

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or os.getenv("FIGMA_TOKEN", "")

    async def load(self, ref: str) -> IntakeResult:
        """Load a Figma file/node reference.

        Ref formats:
          - Full URL: https://figma.com/file/ABC/name?node-id=1:24
          - Short: FILE_KEY/NODE_ID (e.g. 'abc123/1:24')
          - Node only: '1:24' (requires FIGMA_FILE_KEY env)
        """
        import httpx

        file_key, node_id = self._parse_ref(ref)
        logger.info("Fetching Figma file=%s node=%s", file_key, node_id)

        headers = {"X-Figma-Token": self.token}

        # Fetch file metadata for the goal
        url = f"https://api.figma.com/v1/files/{file_key}"
        if node_id:
            url += f"?ids={node_id}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        return self._parse_response(data, ref, node_id)

    def _parse_response(
        self, data: dict, original_ref: str, node_id: str | None
    ) -> IntakeResult:
        """Derive goal and acceptance criteria from Figma file data."""
        file_name = data.get("name", "Untitled")

        # Find the target node
        node_name = file_name
        if node_id and "nodes" in data:
            node_data = data["nodes"].get(node_id, {})
            doc = node_data.get("document", {})
            node_name = doc.get("name", file_name)

        goal = f"Test the '{node_name}' screen/component from Figma design"

        # Derive basic acceptance criteria from the design structure
        acceptance_criteria = [
            f"All elements from the '{node_name}' design are present and visible",
            "Layout matches the Figma design",
            "Interactive elements are functional",
        ]

        return IntakeResult(
            goal=goal,
            acceptance_criteria=acceptance_criteria,
            figma_ref=original_ref,
            app_url=os.getenv("APP_BASE_URL"),
        )

    @staticmethod
    def _parse_ref(ref: str) -> tuple[str, str | None]:
        """Parse a Figma reference into (file_key, node_id)."""
        # Full URL
        url_match = re.match(
            r"https://(?:www\.)?figma\.com/(?:file|design)/([^/]+)",
            ref,
        )
        if url_match:
            file_key = url_match.group(1)
            node_id = None
            node_match = re.search(r"node-id=([^&]+)", ref)
            if node_match:
                node_id = node_match.group(1).replace("%3A", ":")
            return file_key, node_id

        # Short format: FILE_KEY/NODE_ID
        if "/" in ref and not ref.startswith("http"):
            parts = ref.split("/", 1)
            return parts[0], parts[1]

        # Node only — needs FIGMA_FILE_KEY env
        file_key = os.getenv("FIGMA_FILE_KEY", "")
        if file_key:
            return file_key, ref

        return ref, None
