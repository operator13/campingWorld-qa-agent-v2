"""Tests for POMGenerator — mocked LLM."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qa_agent.orchestrator.models import PageConfig, PageSnapshot
from qa_agent.orchestrator.pom_generator import (
    _build_prompt,
    _extract_source,
    _route_to_class_name,
    generate_pom,
)

VALID_POM = """
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


@pytest.fixture
def homepage_snapshot():
    config = PageConfig(
        name="Homepage",
        url="/",
        route="/",
        regions=["hero", "search", "navigation"],
    )
    return PageSnapshot(
        page_config=config,
        url="https://www.campingworld.com/",
        snapshot_text="role: heading, name: Welcome | role: searchbox, name: Search",
        timestamp="2026-08-28T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# _route_to_class_name
# ---------------------------------------------------------------------------

def test_route_to_class_name_homepage():
    assert _route_to_class_name("/") == "HomepagePage"


def test_route_to_class_name_simple():
    assert _route_to_class_name("/cart") == "CartPage"


def test_route_to_class_name_hyphenated():
    assert _route_to_class_name("/sign-in") == "SignInPage"


def test_route_to_class_name_nested():
    assert _route_to_class_name("/rvs-for-sale") == "RvsForSalePage"


def test_route_to_class_name_with_slash():
    assert _route_to_class_name("/rvs-for-sale/detail") == "RvsForSaleDetailPage"


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------

def test_build_prompt_contains_page_name(homepage_snapshot):
    prompt = _build_prompt(homepage_snapshot)
    assert "Homepage" in prompt


def test_build_prompt_contains_route(homepage_snapshot):
    prompt = _build_prompt(homepage_snapshot)
    assert "`/`" in prompt


def test_build_prompt_contains_class_name(homepage_snapshot):
    prompt = _build_prompt(homepage_snapshot)
    assert "HomepagePage" in prompt


def test_build_prompt_contains_dom_snapshot(homepage_snapshot):
    prompt = _build_prompt(homepage_snapshot)
    assert "searchbox" in prompt


def test_build_prompt_contains_regions(homepage_snapshot):
    prompt = _build_prompt(homepage_snapshot)
    assert "hero" in prompt
    assert "search" in prompt
    assert "navigation" in prompt


def test_build_prompt_truncates_long_snapshots():
    config = PageConfig(name="Big", url="/big", route="/big")
    snapshot = PageSnapshot(
        page_config=config,
        url="https://example.com/big",
        snapshot_text="x" * 50000,
        timestamp="2026-08-28T00:00:00Z",
    )
    prompt = _build_prompt(snapshot)
    assert "truncated" in prompt
    assert len(prompt) < 40000


# ---------------------------------------------------------------------------
# _extract_source
# ---------------------------------------------------------------------------

def test_extract_source_plain_text():
    """Plain TypeScript returned as-is."""
    mock_resp = MagicMock()
    mock_resp.content = VALID_POM
    result = _extract_source(mock_resp)
    assert "export class HomepagePage" in result


def test_extract_source_strips_typescript_fences():
    """Strips ```typescript fences."""
    mock_resp = MagicMock()
    mock_resp.content = f"Here is the code:\n```typescript\n{VALID_POM}\n```"
    result = _extract_source(mock_resp)
    assert "export class HomepagePage" in result
    assert "```" not in result


def test_extract_source_strips_ts_fences():
    """Strips ```ts fences."""
    mock_resp = MagicMock()
    mock_resp.content = f"```ts\n{VALID_POM}\n```"
    result = _extract_source(mock_resp)
    assert "export class HomepagePage" in result
    assert "```" not in result


def test_extract_source_handles_content_blocks():
    """Handles list of content blocks (TextBlock)."""
    block = MagicMock()
    block.text = VALID_POM
    mock_resp = MagicMock()
    mock_resp.content = [block]
    result = _extract_source(mock_resp)
    assert "export class HomepagePage" in result


# ---------------------------------------------------------------------------
# generate_pom (mocked LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_pom_returns_typescript(homepage_snapshot):
    """generate_pom calls LLM and returns TypeScript source."""
    mock_response = MagicMock()
    mock_response.content = VALID_POM

    with patch("qa_agent.orchestrator.pom_generator.ChatAnthropic") as MockLLM:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        MockLLM.return_value = mock_instance

        result = await generate_pom(homepage_snapshot)

    assert "export class HomepagePage" in result
    assert "getByRole" in result


@pytest.mark.asyncio
async def test_generate_pom_uses_system_prompt(homepage_snapshot):
    """generate_pom sends the DOM_TO_POM system prompt."""
    mock_response = MagicMock()
    mock_response.content = VALID_POM

    with patch("qa_agent.orchestrator.pom_generator.ChatAnthropic") as MockLLM:
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = mock_response
        MockLLM.return_value = mock_instance

        await generate_pom(homepage_snapshot)

        # Verify ainvoke was called with messages
        call_args = mock_instance.ainvoke.call_args[0][0]
        assert len(call_args) == 2  # SystemMessage + HumanMessage
        assert "Page Object Generator" in call_args[0].content
