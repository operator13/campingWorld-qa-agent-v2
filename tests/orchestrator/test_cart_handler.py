"""Tests for CartHandler — mocked MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from qa_agent.orchestrator.cart_handler import CartHandler


@pytest.fixture
def mock_call_tool():
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "Your cart: 1 item. Product Name. $29.99"
        if tool_name == "browser_wait_for":
            return None
        return None

    call_tool.side_effect = side_effect
    return call_tool


# ---------------------------------------------------------------------------
# Add to cart flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_navigates_to_category(mock_call_tool):
    """Cart handler navigates to /rv-parts to find a product."""
    handler = CartHandler(mock_call_tool)
    await handler.ensure_cart_has_item()
    mock_call_tool.assert_any_call(
        "browser_navigate", {"url": "https://www.campingworld.com/rv-parts"}
    )


@pytest.mark.asyncio
async def test_clicks_add_to_cart(mock_call_tool):
    """Cart handler clicks Add to Cart."""
    handler = CartHandler(mock_call_tool)
    await handler.ensure_cart_has_item()
    mock_call_tool.assert_any_call("browser_click", {"element": "Add to Cart"})


@pytest.mark.asyncio
async def test_marks_item_added(mock_call_tool):
    """After adding, has_item is True."""
    handler = CartHandler(mock_call_tool)
    assert handler.has_item is False
    await handler.ensure_cart_has_item()
    assert handler.has_item is True


# ---------------------------------------------------------------------------
# Session reuse
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skips_if_already_added(mock_call_tool):
    """Does not re-add if cart already has item."""
    handler = CartHandler(mock_call_tool)
    await handler.ensure_cart_has_item()
    count_after_first = mock_call_tool.call_count

    await handler.ensure_cart_has_item()
    assert mock_call_tool.call_count == count_after_first


# ---------------------------------------------------------------------------
# Verify cart
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_cart_not_empty_returns_true(mock_call_tool):
    """Cart with items returns True."""
    handler = CartHandler(mock_call_tool)
    result = await handler.verify_cart_not_empty()
    assert result is True


@pytest.mark.asyncio
async def test_verify_cart_empty_returns_false():
    """Empty cart returns False."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "Your cart is empty. Continue shopping."
        return None

    call_tool.side_effect = side_effect
    handler = CartHandler(call_tool)
    result = await handler.verify_cart_not_empty()
    assert result is False


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def test_reset_clears_state():
    handler = CartHandler(AsyncMock())
    handler._item_added = True
    handler.reset()
    assert handler.has_item is False


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handles_add_to_cart_failure():
    """Gracefully handles when Add to Cart click fails."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_click" and args.get("element") == "Add to Cart":
            raise RuntimeError("Element not found")
        if tool_name == "browser_wait_for":
            return None
        return None

    call_tool.side_effect = side_effect
    handler = CartHandler(call_tool)
    await handler.ensure_cart_has_item()  # Should not raise
    assert handler.has_item is False
