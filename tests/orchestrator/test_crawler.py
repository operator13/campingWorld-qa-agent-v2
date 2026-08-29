"""Tests for PageCrawler — mocked MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from qa_agent.orchestrator.crawler import PageCrawler
from qa_agent.orchestrator.models import PageConfig


@pytest.fixture
def mock_call_tool():
    """Mock MCP tool caller that returns reasonable defaults."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "role: heading, name: Welcome to Camping World"
        if tool_name == "browser_take_screenshot":
            return "/tmp/screenshot.png"
        if tool_name == "browser_navigate":
            return None
        if tool_name == "browser_wait_for":
            return None
        if tool_name == "browser_press_key":
            return None
        return None

    call_tool.side_effect = side_effect
    return call_tool


@pytest.fixture
def crawler(mock_call_tool):
    return PageCrawler(mock_call_tool)


@pytest.fixture
def homepage_config():
    return PageConfig(name="Homepage", url="/", route="/")


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crawler_navigates_to_url(crawler, mock_call_tool, homepage_config):
    """Crawler calls browser_navigate with the correct URL."""
    await crawler.crawl_page(homepage_config)
    mock_call_tool.assert_any_call("browser_navigate", {"url": "https://www.campingworld.com/"})


@pytest.mark.asyncio
async def test_crawler_navigates_dynamic_url(mock_call_tool):
    """Dynamic pages use sample_urls when available."""
    config = PageConfig(
        name="PDP",
        url="/product/",
        route="/product",
        dynamic_url=True,
        sample_urls=["/product/tent-123"],
    )
    crawler = PageCrawler(mock_call_tool)
    await crawler.crawl_page(config)
    mock_call_tool.assert_any_call(
        "browser_navigate", {"url": "https://www.campingworld.com/product/tent-123"}
    )


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crawler_takes_snapshot(crawler, homepage_config):
    """Crawler calls browser_snapshot and returns the text."""
    snapshot = await crawler.crawl_page(homepage_config)
    assert "Welcome to Camping World" in snapshot.snapshot_text


@pytest.mark.asyncio
async def test_crawler_returns_page_snapshot(crawler, homepage_config):
    """Crawl result is a PageSnapshot with all expected fields."""
    snapshot = await crawler.crawl_page(homepage_config)
    assert snapshot.page_config.name == "Homepage"
    assert snapshot.url == "https://www.campingworld.com/"
    assert snapshot.timestamp  # not empty
    assert snapshot.viewport == "desktop"


@pytest.mark.asyncio
async def test_crawler_captures_screenshot(crawler, homepage_config):
    """Crawler attempts to capture a screenshot."""
    snapshot = await crawler.crawl_page(homepage_config)
    assert snapshot.screenshot_path == "/tmp/screenshot.png"


@pytest.mark.asyncio
async def test_crawler_handles_screenshot_failure(homepage_config):
    """Crawler continues gracefully if screenshot fails."""
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "DOM content"
        if tool_name == "browser_take_screenshot":
            raise RuntimeError("Screenshot failed")
        if tool_name == "browser_press_key":
            return None
        return None

    call_tool.side_effect = side_effect
    crawler = PageCrawler(call_tool)
    snapshot = await crawler.crawl_page(homepage_config)
    assert snapshot.screenshot_path is None
    assert snapshot.snapshot_text == "DOM content"


# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crawler_executes_hover_prerequisite(mock_call_tool):
    """Crawler executes hover prerequisites before snapshot."""
    config = PageConfig(
        name="Nav",
        url="/",
        route="/nav",
        prerequisites=[{"action": "hover", "target": "menu trigger"}],
    )
    crawler = PageCrawler(mock_call_tool)
    await crawler.crawl_page(config)
    mock_call_tool.assert_any_call("browser_hover", {"element": "menu trigger"})


@pytest.mark.asyncio
async def test_crawler_executes_fill_prerequisite(mock_call_tool):
    """Crawler executes fill prerequisites (click + type)."""
    config = PageConfig(
        name="Search",
        url="/search",
        route="/search",
        prerequisites=[{"action": "fill", "target": "search input", "value": "tent"}],
    )
    crawler = PageCrawler(mock_call_tool)
    await crawler.crawl_page(config)
    mock_call_tool.assert_any_call("browser_click", {"element": "search input"})
    mock_call_tool.assert_any_call("browser_type", {"text": "tent"})
