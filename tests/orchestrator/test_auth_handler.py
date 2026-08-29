"""Tests for AuthHandler — mocked MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from qa_agent.orchestrator.auth_handler import AuthHandler


@pytest.fixture
def mock_call_tool():
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "role: heading, name: My Account"
        return None

    call_tool.side_effect = side_effect
    return call_tool


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_navigates_to_sign_in(mock_call_tool):
    """Auth handler navigates to /sign-in."""
    handler = AuthHandler(mock_call_tool)
    with patch("qa_agent.orchestrator.auth_handler.EnvConfig") as MockEnv:
        mock_cfg = MockEnv.from_env.return_value
        mock_cfg.app_test_user = "test@example.com"
        mock_cfg.app_test_pass = "password123"
        await handler.ensure_authenticated()

    mock_call_tool.assert_any_call(
        "browser_navigate", {"url": "https://www.campingworld.com/sign-in"}
    )


@pytest.mark.asyncio
async def test_login_fills_credentials(mock_call_tool):
    """Auth handler fills email and password."""
    handler = AuthHandler(mock_call_tool)
    with patch("qa_agent.orchestrator.auth_handler.EnvConfig") as MockEnv:
        mock_cfg = MockEnv.from_env.return_value
        mock_cfg.app_test_user = "test@example.com"
        mock_cfg.app_test_pass = "secret"
        await handler.ensure_authenticated()

    mock_call_tool.assert_any_call("browser_type", {"text": "test@example.com"})
    mock_call_tool.assert_any_call("browser_type", {"text": "secret"})


@pytest.mark.asyncio
async def test_login_clicks_sign_in(mock_call_tool):
    """Auth handler clicks Sign In button."""
    handler = AuthHandler(mock_call_tool)
    with patch("qa_agent.orchestrator.auth_handler.EnvConfig") as MockEnv:
        mock_cfg = MockEnv.from_env.return_value
        mock_cfg.app_test_user = "user"
        mock_cfg.app_test_pass = "pass"
        await handler.ensure_authenticated()

    mock_call_tool.assert_any_call("browser_click", {"element": "Sign In"})


# ---------------------------------------------------------------------------
# Session reuse
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reuses_session(mock_call_tool):
    """Does not re-login if already authenticated."""
    handler = AuthHandler(mock_call_tool)
    with patch("qa_agent.orchestrator.auth_handler.EnvConfig") as MockEnv:
        mock_cfg = MockEnv.from_env.return_value
        mock_cfg.app_test_user = "user"
        mock_cfg.app_test_pass = "pass"
        await handler.ensure_authenticated()
        call_count_after_first = mock_call_tool.call_count

        await handler.ensure_authenticated()
        assert mock_call_tool.call_count == call_count_after_first, "Should not make new calls"


@pytest.mark.asyncio
async def test_is_authenticated_property(mock_call_tool):
    handler = AuthHandler(mock_call_tool)
    assert handler.is_authenticated is False
    with patch("qa_agent.orchestrator.auth_handler.EnvConfig") as MockEnv:
        mock_cfg = MockEnv.from_env.return_value
        mock_cfg.app_test_user = "user"
        mock_cfg.app_test_pass = "pass"
        await handler.ensure_authenticated()
    assert handler.is_authenticated is True


# ---------------------------------------------------------------------------
# Missing credentials
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_raises_without_credentials(mock_call_tool):
    """Raises ValueError when env vars are empty."""
    handler = AuthHandler(mock_call_tool)
    with patch("qa_agent.orchestrator.auth_handler.EnvConfig") as MockEnv:
        mock_cfg = MockEnv.from_env.return_value
        mock_cfg.app_test_user = ""
        mock_cfg.app_test_pass = ""
        with pytest.raises(ValueError, match="APP_TEST_USER"):
            await handler.ensure_authenticated()


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def test_reset_clears_auth(mock_call_tool):
    handler = AuthHandler(mock_call_tool)
    handler._authenticated = True
    handler.reset()
    assert handler.is_authenticated is False


# ---------------------------------------------------------------------------
# Auth redirect detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detect_auth_redirect_true():
    """Detects when page redirected to login."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "Please sign in to continue"
        return None

    call_tool.side_effect = side_effect
    handler = AuthHandler(call_tool)
    assert await handler.detect_auth_redirect() is True


@pytest.mark.asyncio
async def test_detect_auth_redirect_false():
    """Returns False when on a normal page."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "Welcome to your dashboard"
        return None

    call_tool.side_effect = side_effect
    handler = AuthHandler(call_tool)
    assert await handler.detect_auth_redirect() is False
