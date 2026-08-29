"""Detect and dismiss common popups: cookie consent, promo modals, newsletter signups."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Keywords that indicate dismissable popups in the accessibility tree
DISMISS_PATTERNS = [
    # Cookie consent
    {"find": "Accept", "context": ["cookie", "consent", "privacy"]},
    {"find": "Accept All", "context": ["cookie", "consent"]},
    {"find": "I Accept", "context": ["cookie"]},
    {"find": "Got It", "context": ["cookie", "privacy"]},
    # Promo / newsletter modals
    {"find": "Close", "context": ["modal", "dialog", "popup", "overlay"]},
    {"find": "No Thanks", "context": ["sign up", "subscribe", "newsletter", "email"]},
    {"find": "✕", "context": ["modal", "dialog"]},
    {"find": "×", "context": ["modal", "dialog"]},
    # Generic close buttons
    {"find": "close", "context": ["dialog"]},
]


class PopupHandler:
    """Detects and dismisses common popups on e-commerce sites."""

    def __init__(self, call_tool_fn: Any) -> None:
        """
        Args:
            call_tool_fn: async callable that invokes an MCP tool.
                          Signature: async (tool_name: str, args: dict) -> Any
        """
        self._call_tool = call_tool_fn

    async def dismiss_all(self) -> int:
        """Attempt to dismiss any visible popups. Returns count of popups dismissed."""
        dismissed = 0

        # Take a snapshot to see what's on the page
        snapshot = await self._call_tool("browser_snapshot", {})
        snapshot_text = str(snapshot).lower() if snapshot else ""

        for pattern in DISMISS_PATTERNS:
            # Check if the popup context is present in the snapshot
            context_found = any(kw in snapshot_text for kw in pattern["context"])
            if not context_found:
                continue

            # Try to click the dismiss button
            try:
                await self._call_tool("browser_click", {"element": pattern["find"]})
                dismissed += 1
                logger.info("Dismissed popup via '%s'", pattern["find"])
                # Brief wait for animation
                await self._call_tool("browser_wait_for", {"time": 500})
            except Exception:
                logger.debug("Could not click '%s' — may not be visible", pattern["find"])

        # Try pressing Escape as a fallback for any remaining modals
        if dismissed == 0:
            try:
                await self._call_tool("browser_press_key", {"key": "Escape"})
                logger.debug("Pressed Escape as fallback popup dismissal")
            except Exception:
                pass

        return dismissed
