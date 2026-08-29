"""Tests for DynamicPageResolver — mocked MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from qa_agent.orchestrator.dynamic_page_resolver import DynamicPageResolver


# ---------------------------------------------------------------------------
# Product URL resolution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolves_product_url_from_snapshot():
    """Extracts product URL from category page snapshot."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return 'link: "Camping Tent" href="/product/tent-abc-123" | link: "Grill" href="/product/grill-456"'
        return None

    call_tool.side_effect = side_effect
    resolver = DynamicPageResolver(call_tool)
    url = await resolver.resolve("product_detail")
    assert url is not None
    assert "/product/tent-abc-123" in url


@pytest.mark.asyncio
async def test_resolves_product_url_with_base():
    """Resolved URL includes base URL."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return 'href="/product/item-1"'
        return None

    call_tool.side_effect = side_effect
    resolver = DynamicPageResolver(call_tool)
    url = await resolver.resolve("product_detail")
    assert url is not None
    assert url.startswith("https://www.campingworld.com")


# ---------------------------------------------------------------------------
# RV URL resolution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolves_rv_url():
    """Extracts RV listing URL from listings page."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return 'link: "2024 Jayco" href="/rvs-for-sale/jayco-whitehawk-123"'
        return None

    call_tool.side_effect = side_effect
    resolver = DynamicPageResolver(call_tool)
    url = await resolver.resolve("rv_detail")
    assert url is not None
    assert "/rvs-for-sale/jayco-whitehawk-123" in url


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_caches_resolved_url():
    """Second resolve call returns cached URL without MCP calls."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return 'href="/product/cached-item"'
        return None

    call_tool.side_effect = side_effect
    resolver = DynamicPageResolver(call_tool)

    url1 = await resolver.resolve("product_detail")
    call_count = call_tool.call_count

    url2 = await resolver.resolve("product_detail")
    assert url1 == url2
    assert call_tool.call_count == call_count  # No new calls


@pytest.mark.asyncio
async def test_clear_cache():
    """clear_cache forces re-resolution."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return 'href="/product/item"'
        return None

    call_tool.side_effect = side_effect
    resolver = DynamicPageResolver(call_tool)
    await resolver.resolve("product_detail")
    resolver.clear_cache()
    assert "product_detail" not in resolver._cache


# ---------------------------------------------------------------------------
# Unknown page key
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_returns_none_for_unknown_key():
    """Unknown page key returns None."""
    resolver = DynamicPageResolver(AsyncMock())
    url = await resolver.resolve("unknown_page")
    assert url is None


# ---------------------------------------------------------------------------
# Resolution failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_returns_none_when_no_links_found():
    """Returns None when no matching links in snapshot."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "heading: Welcome. No product links here."
        if tool_name == "browser_click":
            raise RuntimeError("No element")
        return None

    call_tool.side_effect = side_effect
    resolver = DynamicPageResolver(call_tool)
    url = await resolver.resolve("product_detail")
    assert url is None


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_product_resolver_navigates_to_rv_parts():
    """Product resolver navigates to /rv-parts."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return 'href="/product/test"'
        return None

    call_tool.side_effect = side_effect
    resolver = DynamicPageResolver(call_tool)
    await resolver.resolve("product_detail")
    call_tool.assert_any_call(
        "browser_navigate", {"url": "https://www.campingworld.com/rv-parts"}
    )


@pytest.mark.asyncio
async def test_rv_resolver_navigates_to_rvs_for_sale():
    """RV resolver navigates to /rvs-for-sale."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return 'href="/rvs-for-sale/test-rv"'
        return None

    call_tool.side_effect = side_effect
    resolver = DynamicPageResolver(call_tool)
    await resolver.resolve("rv_detail")
    call_tool.assert_any_call(
        "browser_navigate", {"url": "https://www.campingworld.com/rvs-for-sale"}
    )
