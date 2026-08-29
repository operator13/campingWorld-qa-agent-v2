"""Pydantic models for the DOM orchestrator."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageConfig(BaseModel):
    """Declarative configuration for a single page type to crawl."""

    name: str
    url: str
    route: str
    requires_auth: bool = False
    priority: int = Field(default=1, description="1=highest priority")
    regions: list[str] = Field(default_factory=list, description="Logical page regions to identify")
    prerequisites: list[dict[str, str]] = Field(
        default_factory=list,
        description="Actions to perform before snapshot (e.g. hover, click, fill)",
    )
    dynamic_url: bool = Field(default=False, description="URL contains dynamic segments")
    sample_urls: list[str] = Field(
        default_factory=list,
        description="Concrete URLs for dynamic pages (resolved at crawl time)",
    )


class PageSnapshot(BaseModel):
    """DOM snapshot captured from a crawled page."""

    page_config: PageConfig
    url: str
    snapshot_text: str = Field(description="Accessibility tree from browser_snapshot")
    screenshot_path: str | None = None
    timestamp: str
    viewport: str = "desktop"


class GeneratedOutput(BaseModel):
    """Generated POM and test files for a single page."""

    page_config: PageConfig
    pom_filename: str
    pom_source: str
    test_filename: str
    test_source: str


class CrawlResult(BaseModel):
    """Summary of a full or partial site crawl."""

    pages_crawled: int = 0
    pages_failed: int = 0
    outputs: list[GeneratedOutput] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
