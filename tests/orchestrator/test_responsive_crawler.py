"""Tests for ResponsiveCrawler — mocked MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from qa_agent.orchestrator.models import PageConfig
from qa_agent.orchestrator.responsive_crawler import VIEWPORTS, ResponsiveCrawler


@pytest.fixture
def mock_call_tool():
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "role: heading, name: Page Content"
        if tool_name == "browser_take_screenshot":
            return "/tmp/screenshot.png"
        if tool_name == "browser_resize":
            return None
        if tool_name == "browser_press_key":
            return None
        return None

    call_tool.side_effect = side_effect
    return call_tool


@pytest.fixture
def homepage_config():
    return PageConfig(name="Homepage", url="/", route="/")


# ---------------------------------------------------------------------------
# Multi-viewport crawl
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crawls_both_viewports(mock_call_tool, homepage_config):
    """Crawls at both desktop and mobile viewports."""
    crawler = ResponsiveCrawler(mock_call_tool)
    snapshots = await crawler.crawl_responsive(homepage_config)
    assert len(snapshots) == 2
    viewports = [s.viewport for s in snapshots]
    assert "desktop" in viewports
    assert "mobile" in viewports


@pytest.mark.asyncio
async def test_desktop_viewport_dimensions(mock_call_tool, homepage_config):
    """Desktop crawl resizes to 1280x720."""
    crawler = ResponsiveCrawler(mock_call_tool)
    await crawler.crawl_responsive(homepage_config, viewports=["desktop"])
    mock_call_tool.assert_any_call("browser_resize", {"width": 1280, "height": 720})


@pytest.mark.asyncio
async def test_mobile_viewport_dimensions(mock_call_tool, homepage_config):
    """Mobile crawl resizes to 375x812."""
    crawler = ResponsiveCrawler(mock_call_tool)
    await crawler.crawl_responsive(homepage_config, viewports=["mobile"])
    mock_call_tool.assert_any_call("browser_resize", {"width": 375, "height": 812})


# ---------------------------------------------------------------------------
# Single viewport
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_viewport(mock_call_tool, homepage_config):
    """Can crawl at just one viewport."""
    crawler = ResponsiveCrawler(mock_call_tool)
    snapshots = await crawler.crawl_responsive(homepage_config, viewports=["mobile"])
    assert len(snapshots) == 1
    assert snapshots[0].viewport == "mobile"


# ---------------------------------------------------------------------------
# Snapshot content
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshots_have_content(mock_call_tool, homepage_config):
    """Each snapshot has the DOM text."""
    crawler = ResponsiveCrawler(mock_call_tool)
    snapshots = await crawler.crawl_responsive(homepage_config)
    for snap in snapshots:
        assert snap.snapshot_text
        assert "Page Content" in snap.snapshot_text


# ---------------------------------------------------------------------------
# Unknown viewport
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skips_unknown_viewport(mock_call_tool, homepage_config):
    """Unknown viewport names are skipped."""
    crawler = ResponsiveCrawler(mock_call_tool)
    snapshots = await crawler.crawl_responsive(homepage_config, viewports=["tablet"])
    assert len(snapshots) == 0


# ---------------------------------------------------------------------------
# Reset viewport
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reset_viewport(mock_call_tool):
    """reset_viewport resizes back to desktop."""
    crawler = ResponsiveCrawler(mock_call_tool)
    await crawler.reset_viewport()
    mock_call_tool.assert_any_call("browser_resize", {"width": 1280, "height": 720})


# ---------------------------------------------------------------------------
# Viewport constants
# ---------------------------------------------------------------------------

def test_viewports_defined():
    assert "desktop" in VIEWPORTS
    assert "mobile" in VIEWPORTS
    assert VIEWPORTS["desktop"]["width"] == 1280
    assert VIEWPORTS["mobile"]["width"] == 375
