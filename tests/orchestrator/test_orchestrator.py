"""Tests for the main Orchestrator — mocked MCP + LLM."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qa_agent.orchestrator.models import PageConfig
from qa_agent.orchestrator.orchestrator import Orchestrator

MOCK_POM = """
import { type Page, type Locator } from '@playwright/test';

export class HomepagePage {
  readonly page: Page;
  readonly searchInput: Locator;

  constructor(page: Page) {
    this.page = page;
    this.searchInput = page.getByRole('searchbox');
  }

  async navigate() {
    await this.page.goto('/');
  }
}
""".strip()

MOCK_TEST = """
import { test, expect } from '@playwright/test';
import { HomepagePage } from '../page_objects/HomepagePage';

test.describe('Homepage', () => {
  let homepage: HomepagePage;
  test.beforeEach(async ({ page }) => {
    homepage = new HomepagePage(page);
    await homepage.navigate();
  });

  test('search is visible', async () => {
    await expect(homepage.searchInput).toBeVisible();
  });
});
""".strip()


@pytest.fixture
def mock_call_tool():
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        if tool_name == "browser_snapshot":
            return "role: searchbox, name: Search products"
        if tool_name == "browser_take_screenshot":
            return "/tmp/screenshot.png"
        if tool_name == "browser_press_key":
            return None
        return None

    call_tool.side_effect = side_effect
    return call_tool


# ---------------------------------------------------------------------------
# Single page crawl
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_single_page(mock_call_tool, tmp_path, monkeypatch):
    """Orchestrator processes a single page end to end."""
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("qa_agent.orchestrator.progress._PROJECT_ROOT", tmp_path)

    with (
        patch("qa_agent.orchestrator.orchestrator.generate_pom", return_value=MOCK_POM),
        patch("qa_agent.orchestrator.orchestrator.generate_tests", return_value=MOCK_TEST),
    ):
        orchestrator = Orchestrator(mock_call_tool)
        orchestrator.progress = __import__(
            "qa_agent.orchestrator.progress", fromlist=["ProgressTracker"]
        ).ProgressTracker(path=tmp_path / "progress.json")

        result = await orchestrator.crawl_site(pages=["homepage"])

    assert result.pages_crawled == 1
    assert result.pages_failed == 0
    assert len(result.outputs) == 1
    assert result.outputs[0].pom_filename == "HomepagePage.ts"

    # Files written
    assert (tmp_path / "page_objects" / "HomepagePage.ts").exists()
    assert (tmp_path / "tests_generated" / "homepage.spec.ts").exists()


# ---------------------------------------------------------------------------
# Multiple pages
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_multiple_pages(mock_call_tool, tmp_path, monkeypatch):
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("qa_agent.orchestrator.progress._PROJECT_ROOT", tmp_path)

    with (
        patch("qa_agent.orchestrator.orchestrator.generate_pom", return_value=MOCK_POM),
        patch("qa_agent.orchestrator.orchestrator.generate_tests", return_value=MOCK_TEST),
    ):
        orchestrator = Orchestrator(mock_call_tool)
        orchestrator.progress = __import__(
            "qa_agent.orchestrator.progress", fromlist=["ProgressTracker"]
        ).ProgressTracker(path=tmp_path / "progress.json")

        result = await orchestrator.crawl_site(pages=["homepage", "sign_in", "store_locator"])

    assert result.pages_crawled == 3
    assert result.pages_failed == 0


# ---------------------------------------------------------------------------
# Resume skips done
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_resume_skips_done(mock_call_tool, tmp_path, monkeypatch):
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)

    from qa_agent.orchestrator.progress import ProgressTracker

    progress = ProgressTracker(path=tmp_path / "progress.json")
    progress.mark_done("Homepage")

    with (
        patch("qa_agent.orchestrator.orchestrator.generate_pom", return_value=MOCK_POM),
        patch("qa_agent.orchestrator.orchestrator.generate_tests", return_value=MOCK_TEST),
    ):
        orchestrator = Orchestrator(mock_call_tool)
        orchestrator.progress = progress

        result = await orchestrator.crawl_site(pages=["homepage", "sign_in"], resume=True)

    # Homepage skipped, only sign_in processed
    assert result.pages_crawled == 1


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_dry_run(mock_call_tool, tmp_path, monkeypatch):
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("qa_agent.orchestrator.progress._PROJECT_ROOT", tmp_path)

    orchestrator = Orchestrator(mock_call_tool)
    orchestrator.progress = __import__(
        "qa_agent.orchestrator.progress", fromlist=["ProgressTracker"]
    ).ProgressTracker(path=tmp_path / "progress.json")

    result = await orchestrator.crawl_site(pages=["homepage"], dry_run=True)

    assert result.pages_crawled == 1
    # No files generated in dry run
    assert len(result.outputs) == 0
    assert not (tmp_path / "page_objects").exists() or not list((tmp_path / "page_objects").iterdir())


# ---------------------------------------------------------------------------
# Auth pages excluded by default
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_excludes_auth_by_default(mock_call_tool, tmp_path, monkeypatch):
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("qa_agent.orchestrator.progress._PROJECT_ROOT", tmp_path)

    with (
        patch("qa_agent.orchestrator.orchestrator.generate_pom", return_value=MOCK_POM),
        patch("qa_agent.orchestrator.orchestrator.generate_tests", return_value=MOCK_TEST),
    ):
        orchestrator = Orchestrator(mock_call_tool)
        orchestrator.progress = __import__(
            "qa_agent.orchestrator.progress", fromlist=["ProgressTracker"]
        ).ProgressTracker(path=tmp_path / "progress.json")

        result = await orchestrator.crawl_site(include_auth=False)

    # Account page (requires_auth=True) should not be in outputs
    output_names = [o.page_config.name for o in result.outputs]
    assert "Account Dashboard" not in output_names


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_handles_page_failure(tmp_path, monkeypatch):
    """Orchestrator continues after a page fails."""
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("qa_agent.orchestrator.progress._PROJECT_ROOT", tmp_path)

    call_count = 0
    call_tool = AsyncMock()

    async def side_effect(tool_name: str, args: dict):
        nonlocal call_count
        if tool_name == "browser_navigate":
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Connection refused")
        if tool_name == "browser_snapshot":
            return "role: heading, name: Page content"
        if tool_name == "browser_press_key":
            return None
        return None

    call_tool.side_effect = side_effect

    with (
        patch("qa_agent.orchestrator.orchestrator.generate_pom", return_value=MOCK_POM),
        patch("qa_agent.orchestrator.orchestrator.generate_tests", return_value=MOCK_TEST),
    ):
        orchestrator = Orchestrator(call_tool)
        orchestrator.progress = __import__(
            "qa_agent.orchestrator.progress", fromlist=["ProgressTracker"]
        ).ProgressTracker(path=tmp_path / "progress.json")

        result = await orchestrator.crawl_site(pages=["homepage", "sign_in"])

    assert result.pages_failed >= 1
    assert len(result.errors) >= 1


# ---------------------------------------------------------------------------
# Unknown page key
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_unknown_page_key(mock_call_tool, tmp_path, monkeypatch):
    monkeypatch.setattr("qa_agent.orchestrator.file_writer._PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("qa_agent.orchestrator.progress._PROJECT_ROOT", tmp_path)

    orchestrator = Orchestrator(mock_call_tool)
    orchestrator.progress = __import__(
        "qa_agent.orchestrator.progress", fromlist=["ProgressTracker"]
    ).ProgressTracker(path=tmp_path / "progress.json")

    result = await orchestrator.crawl_site(pages=["nonexistent_page"])
    assert result.pages_crawled == 0
