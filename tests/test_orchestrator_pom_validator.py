"""Tests for POM Validator — ensures generated POMs follow conventions."""

from __future__ import annotations

import pytest

from qa_agent.orchestrator.pom_validator import validate_pom

VALID_POM = """
import { type Page, type Locator } from '@playwright/test';

export class HomepagePage {
  readonly page: Page;
  readonly searchInput: Locator;
  readonly cartIcon: Locator;

  constructor(page: Page) {
    this.page = page;
    this.searchInput = page.getByRole('searchbox');
    this.cartIcon = page.getByRole('link', { name: /cart/i });
  }

  async navigate() {
    await this.page.goto('/');
  }

  async search(query: string) {
    await this.searchInput.fill(query);
    await this.searchInput.press('Enter');
  }
}
""".strip()


# ---------------------------------------------------------------------------
# Valid POM
# ---------------------------------------------------------------------------

def test_valid_pom_passes():
    """A well-formed POM passes all validation checks."""
    result = validate_pom(VALID_POM)
    assert result.valid is True
    assert result.errors == []


# ---------------------------------------------------------------------------
# Missing export class
# ---------------------------------------------------------------------------

def test_rejects_missing_export_class():
    source = VALID_POM.replace("export class", "class")
    result = validate_pom(source)
    assert result.valid is False
    assert any("export class" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Missing page: Page constructor
# ---------------------------------------------------------------------------

def test_rejects_missing_page_param():
    source = VALID_POM.replace("page: Page", "pg: any")
    result = validate_pom(source)
    assert result.valid is False
    assert any("page: Page" in e for e in result.errors)


# ---------------------------------------------------------------------------
# CSS selectors
# ---------------------------------------------------------------------------

def test_rejects_css_class_selector():
    source = VALID_POM.replace(
        "page.getByRole('searchbox')",
        "page.locator('.search-input')",
    )
    result = validate_pom(source)
    assert result.valid is False
    assert any("CSS selector" in e for e in result.errors)


def test_rejects_css_id_selector():
    source = VALID_POM.replace(
        "page.getByRole('searchbox')",
        "page.locator('#search')",
    )
    result = validate_pom(source)
    assert result.valid is False
    assert any("CSS selector" in e for e in result.errors)


def test_rejects_css_attribute_selector():
    source = VALID_POM.replace(
        "page.getByRole('searchbox')",
        "page.locator('[data-id=search]')",
    )
    result = validate_pom(source)
    assert result.valid is False
    assert any("CSS selector" in e for e in result.errors)


def test_rejects_query_selector():
    source = VALID_POM + "\n  querySelector('.test');"
    result = validate_pom(source)
    assert result.valid is False
    assert any("CSS selector" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Missing navigate()
# ---------------------------------------------------------------------------

def test_rejects_missing_navigate():
    source = VALID_POM.replace("async navigate()", "async goToPage()")
    result = validate_pom(source)
    assert result.valid is False
    assert any("navigate" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Missing import
# ---------------------------------------------------------------------------

def test_rejects_missing_playwright_import():
    source = VALID_POM.replace("@playwright/test", "@some/other-lib")
    result = validate_pom(source)
    assert result.valid is False
    assert any("@playwright/test" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Assertions in POM
# ---------------------------------------------------------------------------

def test_rejects_expect_in_pom():
    source = VALID_POM + "\n    expect(this.searchInput).toBeVisible();"
    result = validate_pom(source)
    assert result.valid is False
    assert any("Assertion" in e for e in result.errors)


def test_rejects_toHaveText_in_pom():
    source = VALID_POM + "\n    .toHaveText('something');"
    result = validate_pom(source)
    assert result.valid is False
    assert any("Assertion" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Resilient locators
# ---------------------------------------------------------------------------

def test_rejects_no_resilient_locators():
    """POM with no getByRole/getByTestId/etc. fails."""
    source = """
import { type Page, type Locator } from '@playwright/test';

export class BadPage {
  readonly page: Page;
  constructor(page: Page) {
    this.page = page;
  }
  async navigate() {
    await this.page.goto('/bad');
  }
}
""".strip()
    result = validate_pom(source)
    assert result.valid is False
    assert any("resilient locator" in e for e in result.errors)


def test_accepts_getByTestId():
    """POM using getByTestId is valid."""
    source = VALID_POM.replace("getByRole('searchbox')", "getByTestId('search-input')")
    result = validate_pom(source)
    assert result.valid is True


def test_accepts_getByText():
    """POM using getByText is valid."""
    source = VALID_POM.replace("getByRole('searchbox')", "getByText('Search')")
    result = validate_pom(source)
    assert result.valid is True


# ---------------------------------------------------------------------------
# Multiple errors
# ---------------------------------------------------------------------------

def test_reports_multiple_errors():
    """Validator reports all errors, not just the first one."""
    source = "class BadPage { }"  # Missing everything
    result = validate_pom(source)
    assert result.valid is False
    assert len(result.errors) >= 4  # export class, page: Page, locators, navigate, import
