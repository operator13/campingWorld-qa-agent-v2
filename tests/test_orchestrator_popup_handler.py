"""Tests for PopupHandler — mocked MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from qa_agent.orchestrator.popup_handler import PopupHandler


@pytest.fixture
def mock_call_tool():
    """Default mock that returns empty snapshot (no popups)."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "role: heading, name: Welcome"
        return None

    call_tool.side_effect = side_effect
    return call_tool


# ---------------------------------------------------------------------------
# No popups
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_popups_returns_zero(mock_call_tool):
    """When no popup context is found, dismiss_all returns 0."""
    handler = PopupHandler(mock_call_tool)
    dismissed = await handler.dismiss_all()
    assert dismissed == 0


# ---------------------------------------------------------------------------
# Cookie consent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dismisses_cookie_banner():
    """Detects cookie consent banner and clicks Accept."""
    call_tool = AsyncMock()
    call_count = 0

    async def side_effect(tool_name: str, args: dict):
        nonlocal call_count
        if tool_name == "browser_snapshot":
            return "dialog: Cookie consent. We use cookies to improve your experience. button: Accept All"
        if tool_name == "browser_click":
            call_count += 1
            return None
        return None

    call_tool.side_effect = side_effect
    handler = PopupHandler(call_tool)
    dismissed = await handler.dismiss_all()
    assert dismissed >= 1


# ---------------------------------------------------------------------------
# Promo modal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dismisses_promo_modal():
    """Detects promo modal and clicks Close."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "dialog: Sign up for our newsletter! modal overlay. button: Close. button: No Thanks"
        if tool_name == "browser_click":
            return None
        return None

    call_tool.side_effect = side_effect
    handler = PopupHandler(call_tool)
    dismissed = await handler.dismiss_all()
    assert dismissed >= 1


# ---------------------------------------------------------------------------
# Click failure handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handles_click_failure_gracefully():
    """If clicking a dismiss button fails, handler continues without crashing."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "cookie consent dialog"
        if tool_name == "browser_click":
            raise RuntimeError("Element not found")
        if tool_name == "browser_press_key":
            return None
        return None

    call_tool.side_effect = side_effect
    handler = PopupHandler(call_tool)
    # Should not raise
    dismissed = await handler.dismiss_all()
    assert dismissed == 0


# ---------------------------------------------------------------------------
# Escape fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escape_fallback_when_no_dismiss():
    """Presses Escape as fallback when no popups were dismissed."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "role: heading, name: Welcome to the store"
        if tool_name == "browser_press_key":
            return None
        return None

    call_tool.side_effect = side_effect
    handler = PopupHandler(call_tool)
    dismissed = await handler.dismiss_all()
    assert dismissed == 0
    # Verify Escape was pressed as fallback
    call_tool.assert_any_call("browser_press_key", {"key": "Escape"})
