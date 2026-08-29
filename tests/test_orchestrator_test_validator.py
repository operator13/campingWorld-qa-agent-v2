"""Tests for Test Validator — ensures generated test specs follow conventions."""

from __future__ import annotations

import pytest

from qa_agent.orchestrator.test_validator import validate_test

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

  test('search works', async ({ page }) => {
    await homepage.search('tent');
    await expect(page).toHaveURL(/search/);
  });
});
""".strip()


# ---------------------------------------------------------------------------
# Valid test
# ---------------------------------------------------------------------------

def test_valid_test_passes():
    result = validate_test(VALID_TEST)
    assert result.valid is True
    assert result.errors == []


def test_valid_test_with_pom_class():
    result = validate_test(VALID_TEST, pom_class_name="HomepagePage")
    assert result.valid is True


# ---------------------------------------------------------------------------
# Missing imports
# ---------------------------------------------------------------------------

def test_rejects_missing_playwright_import():
    source = VALID_TEST.replace("@playwright/test", "@some/lib")
    result = validate_test(source)
    assert result.valid is False
    assert any("@playwright/test" in e for e in result.errors)


def test_rejects_missing_pom_import():
    source = VALID_TEST.replace("../page_objects/", "../somewhere/")
    result = validate_test(source)
    assert result.valid is False
    assert any("Page Object import" in e for e in result.errors)


def test_rejects_missing_specific_pom_class():
    result = validate_test(VALID_TEST, pom_class_name="CartPage")
    assert result.valid is False
    assert any("CartPage" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Missing structure
# ---------------------------------------------------------------------------

def test_rejects_missing_describe():
    source = VALID_TEST.replace("test.describe(", "/* describe removed */void(")
    result = validate_test(source)
    assert result.valid is False
    assert any("test.describe" in e for e in result.errors)


def test_rejects_missing_before_each():
    source = VALID_TEST.replace("test.beforeEach(", "/* removed */void(")
    result = validate_test(source)
    assert result.valid is False
    assert any("beforeEach" in e for e in result.errors)


def test_rejects_no_test_blocks():
    """A file with no test('...') blocks fails."""
    source = """
import { test, expect } from '@playwright/test';
import { HomepagePage } from '../page_objects/HomepagePage';

test.describe('Homepage', () => {
  test.beforeEach(async ({ page }) => {});
  // no actual tests
  expect(true).toBe(true);
});
""".strip()
    result = validate_test(source)
    assert result.valid is False
    assert any("test() block" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Inline selectors
# ---------------------------------------------------------------------------

def test_rejects_inline_css_class_selector():
    source = VALID_TEST + "\n  page.locator('.some-class');"
    result = validate_test(source)
    assert result.valid is False
    assert any("Inline selector" in e for e in result.errors)


def test_rejects_inline_id_selector():
    source = VALID_TEST + "\n  page.locator('#some-id');"
    result = validate_test(source)
    assert result.valid is False
    assert any("Inline selector" in e for e in result.errors)


def test_rejects_query_selector():
    source = VALID_TEST + "\n  document.querySelector('.x');"
    result = validate_test(source)
    assert result.valid is False
    assert any("Inline selector" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Hard waits
# ---------------------------------------------------------------------------

def test_rejects_wait_for_timeout():
    source = VALID_TEST + "\n  await page.waitForTimeout(1000);"
    result = validate_test(source)
    assert result.valid is False
    assert any("Hard wait" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Missing assertions
# ---------------------------------------------------------------------------

def test_rejects_no_assertions():
    source = VALID_TEST.replace("expect(", "/* expect removed */ void(")
    result = validate_test(source)
    assert result.valid is False
    assert any("assertion" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# Multiple errors
# ---------------------------------------------------------------------------

def test_reports_multiple_errors():
    source = "const x = 1;"  # Missing everything
    result = validate_test(source)
    assert result.valid is False
    assert len(result.errors) >= 5
