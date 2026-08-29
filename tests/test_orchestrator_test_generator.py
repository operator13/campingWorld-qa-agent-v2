"""Tests for TestGenerator — mocked LLM."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qa_agent.orchestrator.models import PageConfig, PageSnapshot
from qa_agent.orchestrator.test_generator import (
    _build_prompt,
    _extract_source,
    _find_page_key,
    _route_to_class_name,
    _route_to_spec_filename,
    generate_tests,
)

VALID_TEST = """
import { test, expect } from '@playwright/test';
import { HomepagePage } from '../page_objects/HomepagePage';

test.describe('Homepage', () => {
  let homepage: HomepagePage;

  test.beforeEach(async ({ page }) => {
    homepage = new HomepagePage(page);
    await homepage.navigate();
  });

  test('hero banner is visible', async () => {
    await expect(homepage.heroBanner).toBeVisible();
  });

  test('search bar accepts input', async ({ page }) => {
    await homepage.search('tent');
    await expect(page).toHaveURL(/search/);
  });
});
""".strip()

SAMPLE_POM = """
import { type Page, type Locator } from '@playwright/test';

export class HomepagePage {
  readonly page: Page;
  readonly heroBanner: Locator;
  readonly searchInput: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heroBanner = page.getByRole('banner');
    this.searchInput = page.getByRole('searchbox');
  }

  async navigate() { await this.page.goto('/'); }
  async search(query: string) {
    await this.searchInput.fill(query);
    await this.searchInput.press('Enter');
  }
}
""".strip()


@pytest.fixture
def homepage_config():
    return PageConfig(name="Homepage", url="/", route="/", regions=["hero", "search"])


@pytest.fixture
def homepage_snapshot(homepage_config):
    return PageSnapshot(
        page_config=homepage_config,
        url="https://www.campingworld.com/",
        snapshot_text="role: heading, name: Welcome | role: searchbox",
        timestamp="2026-08-28T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# _route_to_spec_filename
# ---------------------------------------------------------------------------

def test_spec_filename_homepage():
    assert _route_to_spec_filename("/") == "homepage.spec.ts"


def test_spec_filename_simple():
    assert _route_to_spec_filename("/cart") == "cart.spec.ts"


def test_spec_filename_hyphenated():
    assert _route_to_spec_filename("/sign-in") == "sign-in.spec.ts"


def test_spec_filename_nested():
    assert _route_to_spec_filename("/rvs-for-sale/detail") == "rvs-for-sale-detail.spec.ts"


# ---------------------------------------------------------------------------
# _route_to_class_name
# ---------------------------------------------------------------------------

def test_class_name_homepage():
    assert _route_to_class_name("/") == "HomepagePage"


def test_class_name_cart():
    assert _route_to_class_name("/cart") == "CartPage"


# ---------------------------------------------------------------------------
# _find_page_key
# ---------------------------------------------------------------------------

def test_find_page_key_exact():
    assert _find_page_key("Homepage") == "homepage"


def test_find_page_key_product_detail():
    assert _find_page_key("Product Detail Page") == "product_detail"


def test_find_page_key_sign_in():
    assert _find_page_key("Sign In") == "sign_in"


def test_find_page_key_store_locator():
    assert _find_page_key("Store Locator") == "store_locator"


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------

def test_build_prompt_contains_pom_source(homepage_config, homepage_snapshot):
    prompt = _build_prompt(SAMPLE_POM, homepage_config, homepage_snapshot, ["test 1"])
    assert "HomepagePage" in prompt
    assert "getByRole" in prompt


def test_build_prompt_contains_scenarios(homepage_config, homepage_snapshot):
    scenarios = ["hero is visible", "search works"]
    prompt = _build_prompt(SAMPLE_POM, homepage_config, homepage_snapshot, scenarios)
    assert "hero is visible" in prompt
    assert "search works" in prompt


def test_build_prompt_contains_dom(homepage_config, homepage_snapshot):
    prompt = _build_prompt(SAMPLE_POM, homepage_config, homepage_snapshot, ["test"])
    assert "searchbox" in prompt


def test_build_prompt_contains_import_path(homepage_config, homepage_snapshot):
    prompt = _build_prompt(SAMPLE_POM, homepage_config, homepage_snapshot, ["test"])
    assert "../page_objects/HomepagePage" in prompt


def test_build_prompt_truncates_long_dom(homepage_config):
    snapshot = PageSnapshot(
        page_config=homepage_config,
        url="https://example.com",
        snapshot_text="x" * 30000,
        timestamp="2026-08-28T00:00:00Z",
    )
    prompt = _build_prompt(SAMPLE_POM, homepage_config, snapshot, ["test"])
    assert "truncated" in prompt


# ---------------------------------------------------------------------------
# _extract_source
# ---------------------------------------------------------------------------

def test_extract_source_plain():
    resp = MagicMock()
    resp.content = VALID_TEST
    result = _extract_source(resp)
    assert "test.describe" in result


def test_extract_source_strips_fences():
    resp = MagicMock()
    resp.content = f"```typescript\n{VALID_TEST}\n```"
    result = _extract_source(resp)
    assert "test.describe" in result
    assert "```" not in result


def test_extract_source_handles_blocks():
    block = MagicMock()
    block.text = VALID_TEST
    resp = MagicMock()
    resp.content = [block]
    result = _extract_source(resp)
    assert "test.describe" in result


# ---------------------------------------------------------------------------
# generate_tests (mocked LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_tests_returns_typescript(homepage_config, homepage_snapshot):
    mock_response = MagicMock()
    mock_response.content = VALID_TEST

    with patch("qa_agent.orchestrator.test_generator.ChatAnthropic") as MockLLM:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        MockLLM.return_value = mock_instance

        result = await generate_tests(SAMPLE_POM, homepage_config, homepage_snapshot)

    assert "test.describe" in result
    assert "expect(" in result


@pytest.mark.asyncio
async def test_generate_tests_uses_template_scenarios(homepage_config, homepage_snapshot):
    """When no scenarios provided, uses template scenarios."""
    mock_response = MagicMock()
    mock_response.content = VALID_TEST

    with patch("qa_agent.orchestrator.test_generator.ChatAnthropic") as MockLLM:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        MockLLM.return_value = mock_instance

        await generate_tests(SAMPLE_POM, homepage_config, homepage_snapshot)

        call_args = mock_instance.ainvoke.call_args[0][0]
        human_msg = call_args[1].content
        assert "hero banner" in human_msg  # From homepage template


@pytest.mark.asyncio
async def test_generate_tests_accepts_custom_scenarios(homepage_config, homepage_snapshot):
    mock_response = MagicMock()
    mock_response.content = VALID_TEST

    with patch("qa_agent.orchestrator.test_generator.ChatAnthropic") as MockLLM:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        MockLLM.return_value = mock_instance

        custom = ["custom scenario one", "custom scenario two"]
        await generate_tests(SAMPLE_POM, homepage_config, homepage_snapshot, scenarios=custom)

        call_args = mock_instance.ainvoke.call_args[0][0]
        human_msg = call_args[1].content
        assert "custom scenario one" in human_msg
