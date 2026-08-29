"""Tests for orchestrator Pydantic models."""

from __future__ import annotations

import pytest

from qa_agent.orchestrator.models import (
    CrawlResult,
    GeneratedOutput,
    PageConfig,
    PageSnapshot,
)


# ---------------------------------------------------------------------------
# PageConfig
# ---------------------------------------------------------------------------

def test_page_config_required_fields():
    """PageConfig requires name, url, and route."""
    config = PageConfig(name="Homepage", url="/", route="/")
    assert config.name == "Homepage"
    assert config.url == "/"
    assert config.route == "/"


def test_page_config_defaults():
    """PageConfig has sensible defaults."""
    config = PageConfig(name="Test", url="/test", route="/test")
    assert config.requires_auth is False
    assert config.priority == 1
    assert config.regions == []
    assert config.prerequisites == []
    assert config.dynamic_url is False
    assert config.sample_urls == []


def test_page_config_with_all_fields():
    """PageConfig accepts all optional fields."""
    config = PageConfig(
        name="PDP",
        url="/product/",
        route="/product",
        requires_auth=False,
        priority=2,
        regions=["title", "images", "pricing"],
        prerequisites=[{"action": "click", "target": "first product"}],
        dynamic_url=True,
        sample_urls=["/product/tent-123", "/product/grill-456"],
    )
    assert config.dynamic_url is True
    assert len(config.sample_urls) == 2
    assert len(config.regions) == 3


def test_page_config_with_auth():
    """Auth-gated page config."""
    config = PageConfig(name="Account", url="/account", route="/account", requires_auth=True)
    assert config.requires_auth is True


# ---------------------------------------------------------------------------
# PageSnapshot
# ---------------------------------------------------------------------------

def test_page_snapshot_creation():
    """PageSnapshot stores snapshot text and metadata."""
    config = PageConfig(name="Homepage", url="/", route="/")
    snapshot = PageSnapshot(
        page_config=config,
        url="https://www.campingworld.com/",
        snapshot_text="<accessibility tree content>",
        timestamp="2026-08-28T00:00:00Z",
    )
    assert snapshot.snapshot_text == "<accessibility tree content>"
    assert snapshot.viewport == "desktop"
    assert snapshot.screenshot_path is None


def test_page_snapshot_with_screenshot():
    """PageSnapshot can include a screenshot path."""
    config = PageConfig(name="Test", url="/test", route="/test")
    snapshot = PageSnapshot(
        page_config=config,
        url="https://example.com/test",
        snapshot_text="DOM content",
        screenshot_path="/tmp/screenshot.png",
        timestamp="2026-08-28T00:00:00Z",
        viewport="mobile",
    )
    assert snapshot.screenshot_path == "/tmp/screenshot.png"
    assert snapshot.viewport == "mobile"


# ---------------------------------------------------------------------------
# GeneratedOutput
# ---------------------------------------------------------------------------

def test_generated_output_format():
    """GeneratedOutput stores POM and test source together."""
    config = PageConfig(name="Homepage", url="/", route="/")
    output = GeneratedOutput(
        page_config=config,
        pom_filename="HomepagePage.ts",
        pom_source="export class HomepagePage { }",
        test_filename="homepage.spec.ts",
        test_source="test.describe('Homepage', () => { });",
    )
    assert output.pom_filename == "HomepagePage.ts"
    assert "HomepagePage" in output.pom_source
    assert "homepage.spec.ts" == output.test_filename


# ---------------------------------------------------------------------------
# CrawlResult
# ---------------------------------------------------------------------------

def test_crawl_result_defaults():
    """CrawlResult starts with zero counts and empty lists."""
    result = CrawlResult()
    assert result.pages_crawled == 0
    assert result.pages_failed == 0
    assert result.outputs == []
    assert result.errors == []


def test_crawl_result_aggregation():
    """CrawlResult correctly counts pages."""
    config = PageConfig(name="Test", url="/", route="/")
    output = GeneratedOutput(
        page_config=config,
        pom_filename="TestPage.ts",
        pom_source="code",
        test_filename="test.spec.ts",
        test_source="code",
    )
    result = CrawlResult(
        pages_crawled=3,
        pages_failed=1,
        outputs=[output],
        errors=["Page X failed: timeout"],
    )
    assert result.pages_crawled == 3
    assert result.pages_failed == 1
    assert len(result.outputs) == 1
    assert len(result.errors) == 1
