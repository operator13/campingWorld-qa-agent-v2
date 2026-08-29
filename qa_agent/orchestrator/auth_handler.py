"""Auth handler — logs into campingworld.com for auth-gated pages."""

from __future__ import annotations

import logging
from typing import Any

from qa_agent.config import EnvConfig

logger = logging.getLogger(__name__)


class AuthHandler:
    """Handles login for auth-gated pages via Playwright MCP tools."""

    def __init__(self, call_tool_fn: Any, base_url: str = "https://www.campingworld.com") -> None:
        self._call_tool = call_tool_fn
        self._base_url = base_url
        self._authenticated = False

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    async def ensure_authenticated(self) -> None:
        """Log in if not already authenticated. Reuses session if already logged in."""
        if self._authenticated:
            logger.debug("AuthHandler: already authenticated, skipping login")
            return

        cfg = EnvConfig.from_env()
        if not cfg.app_test_user or not cfg.app_test_pass:
            raise ValueError(
                "APP_TEST_USER and APP_TEST_PASS must be set in .env for auth-gated pages"
            )

        logger.info("AuthHandler: logging in as %s", cfg.app_test_user)

        # Navigate to sign-in page
        await self._call_tool("browser_navigate", {"url": f"{self._base_url}/sign-in"})

        # Fill email
        await self._call_tool("browser_click", {"element": "Email"})
        await self._call_tool("browser_type", {"text": cfg.app_test_user})

        # Fill password
        await self._call_tool("browser_click", {"element": "Password"})
        await self._call_tool("browser_type", {"text": cfg.app_test_pass})

        # Click sign in
        await self._call_tool("browser_click", {"element": "Sign In"})

        # Wait for navigation to complete
        try:
            await self._call_tool("browser_wait_for", {"text": "Account", "timeout": 10000})
            self._authenticated = True
            logger.info("AuthHandler: login successful")
        except Exception:
            logger.warning("AuthHandler: login may have failed — could not find 'Account' text")
            # Still mark as attempted to avoid infinite retries
            self._authenticated = True

    async def detect_auth_redirect(self) -> bool:
        """Check if the current page redirected to a login page."""
        snapshot = await self._call_tool("browser_snapshot", {})
        snapshot_text = str(snapshot).lower() if snapshot else ""
        return any(
            indicator in snapshot_text
            for indicator in ["sign in", "log in", "login", "sign-in"]
        )

    def reset(self) -> None:
        """Reset auth state (e.g., after clearing cookies)."""
        self._authenticated = False
