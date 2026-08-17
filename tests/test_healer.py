"""Tests for the Healer node — especially the assertion guardrail."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from qa_agent.nodes.healer import (
    AssertionGuardError,
    _extract_assertion_lines,
    healer,
    validate_healer_diff,
)
from qa_agent.state import QAState


# ---------------------------------------------------------------------------
# Assertion guardrail — validate_healer_diff
# ---------------------------------------------------------------------------

class TestAssertionGuardrail:
    def test_accepts_locator_only_change(self):
        """Changing only locators passes the guardrail."""
        old = """\
import { type Page, type Locator } from '@playwright/test';
export class CheckoutPage {
  readonly submitBtn: Locator;
  constructor(page: Page) {
    this.submitBtn = page.getByRole('button', { name: 'Submit' });
  }
}"""
        new = """\
import { type Page, type Locator } from '@playwright/test';
export class CheckoutPage {
  readonly submitBtn: Locator;
  constructor(page: Page) {
    this.submitBtn = page.getByRole('button', { name: 'Place Order' });
  }
}"""
        # Should not raise
        validate_healer_diff(old, new)

    def test_rejects_added_assertion(self):
        """Adding an assertion is rejected."""
        old = "this.submitBtn = page.getByRole('button', { name: 'Submit' });"
        new = """\
this.submitBtn = page.getByRole('button', { name: 'Submit' });
await expect(this.submitBtn).toBeVisible();"""
        with pytest.raises(AssertionGuardError):
            validate_healer_diff(old, new)

    def test_rejects_removed_assertion(self):
        """Removing an assertion is rejected."""
        old = """\
this.submitBtn = page.getByRole('button', { name: 'Submit' });
await expect(this.submitBtn).toBeVisible();"""
        new = "this.submitBtn = page.getByRole('button', { name: 'Submit' });"
        with pytest.raises(AssertionGuardError):
            validate_healer_diff(old, new)

    def test_rejects_modified_assertion(self):
        """Changing an assertion value is rejected."""
        old = "await expect(page).toHaveURL('/checkout');"
        new = "await expect(page).toHaveURL('/cart');"
        with pytest.raises(AssertionGuardError):
            validate_healer_diff(old, new)

    def test_rejects_toHaveText_change(self):
        """Changing toHaveText assertion is rejected."""
        old = "await expect(heading).toHaveText('Welcome');"
        new = "await expect(heading).toHaveText('Hello');"
        with pytest.raises(AssertionGuardError):
            validate_healer_diff(old, new)

    def test_accepts_wait_change(self):
        """Changing a wait strategy passes."""
        old = "await page.waitForSelector('.loading');"
        new = "await page.waitForSelector('[data-testid=spinner]');"
        validate_healer_diff(old, new)

    def test_accepts_empty_sources(self):
        """Both empty sources pass."""
        validate_healer_diff("", "")

    def test_accepts_identical_sources(self):
        """Identical sources pass."""
        src = "await expect(x).toBeVisible();\nthis.btn = page.locator('button');"
        validate_healer_diff(src, src)


class TestExtractAssertionLines:
    def test_finds_expect(self):
        src = "await expect(page).toHaveURL('/ok');\nconst x = 1;"
        lines = _extract_assertion_lines(src)
        assert len(lines) == 1
        assert "expect" in lines[0]

    def test_finds_multiple_patterns(self):
        src = """\
await expect(btn).toBeVisible();
await expect(input).toHaveValue('test');
const locator = page.getByRole('button');
await expect(page).toHaveTitle('Home');"""
        lines = _extract_assertion_lines(src)
        assert len(lines) == 3

    def test_no_assertions(self):
        src = "const x = 1;\nthis.btn = page.locator('button');"
        lines = _extract_assertion_lines(src)
        assert len(lines) == 0


# ---------------------------------------------------------------------------
# Healer node with mocked LLM
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_healer_with_mock_llm():
    """Healer patches a page object when guardrail passes."""
    mock_response_json = '''{
        "page_objects": {
            "/checkout": "export class CheckoutPage { submitBtn = page.getByRole('button', { name: 'Place Order' }); }"
        },
        "changes": [
            {
                "file": "/checkout",
                "old_locator": "page.getByRole('button', { name: 'Submit' })",
                "new_locator": "page.getByRole('button', { name: 'Place Order' })",
                "reason": "Button text changed"
            }
        ]
    }'''

    mock_response = AsyncMock()
    mock_response.content = mock_response_json

    with patch("qa_agent.nodes.healer.ChatAnthropic") as MockChat:
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)
        MockChat.return_value = mock_model

        state = QAState(
            goal="Test checkout",
            page_objects={
                "/checkout": "export class CheckoutPage { submitBtn = page.getByRole('button', { name: 'Submit' }); }"
            },
            error="Locator not found: button 'Submit'",
            attempts=0,
        )
        result = await healer(state)

    assert "page_objects" in result
    assert "/checkout" in result["page_objects"]
    assert "Place Order" in result["page_objects"]["/checkout"]
    assert result["attempts"] == 1  # will be added by reducer


@pytest.mark.asyncio
async def test_healer_rejects_assertion_diff():
    """Healer keeps old source when LLM response touches assertions."""
    old_source = """\
export class CheckoutPage {
  submitBtn = page.getByRole('button', { name: 'Submit' });
}"""

    # Bad response: LLM added an assertion
    bad_response_json = '''{
        "page_objects": {
            "/checkout": "export class CheckoutPage {\\n  submitBtn = page.getByRole('button', { name: 'Place Order' });\\n  await expect(submitBtn).toBeVisible();\\n}"
        }
    }'''

    mock_response = AsyncMock()
    mock_response.content = bad_response_json

    with patch("qa_agent.nodes.healer.ChatAnthropic") as MockChat:
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)
        MockChat.return_value = mock_model

        state = QAState(
            goal="Test checkout",
            page_objects={"/checkout": old_source},
            error="Locator not found",
            attempts=0,
        )
        result = await healer(state)

    # Should keep the old source because guardrail rejected the diff
    assert result["page_objects"]["/checkout"] == old_source
