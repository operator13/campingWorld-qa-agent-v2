"""Tests for AI nodes — each with mocked LLM returns schema-valid output."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from qa_agent.schemas.models import ExpectedUI, TestCase, UIElement, UIFlow
from qa_agent.state import QAState


# ---------------------------------------------------------------------------
# Design Reader
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_design_reader_skips_without_figma():
    """Design Reader returns empty when no figma_ref."""
    from qa_agent.nodes.design_reader import design_reader

    state = QAState(goal="Test login", acceptance_criteria=["User can log in"])
    result = await design_reader(state)
    assert result == {}


@pytest.mark.asyncio
async def test_design_reader_with_mock_llm():
    """Design Reader produces ExpectedUI from mocked LLM response."""
    from qa_agent.nodes.design_reader import design_reader

    mock_response_json = '''{
        "route": "/checkout",
        "elements": [
            {"role": "button", "name": "Submit", "state": "enabled", "testid": "checkout-submit"},
            {"role": "textbox", "name": "Email", "state": "required", "testid": "checkout-email"}
        ],
        "flows": [
            {"name": "checkout", "steps": ["fill email", "click submit", "see confirmation"]}
        ]
    }'''

    mock_response = AsyncMock()
    mock_response.content = f"```json\n{mock_response_json}\n```"

    with patch("qa_agent.nodes.design_reader.ChatAnthropic") as MockChat:
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)
        MockChat.return_value = mock_model

        state = QAState(
            goal="Test checkout",
            figma_ref="abc123/1:24",
            acceptance_criteria=["User can submit order"],
        )
        result = await design_reader(state)

    assert "expected_ui" in result
    ui = result["expected_ui"]
    assert isinstance(ui, ExpectedUI)
    assert ui.route == "/checkout"
    assert len(ui.elements) == 2
    assert ui.elements[0].name == "Submit"
    assert len(ui.flows) == 1


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_planner_with_mock_llm():
    """Planner produces test cases from mocked LLM response."""
    from qa_agent.nodes.planner import planner

    mock_response_json = '''[
        {
            "id": "tc-checkout-01",
            "title": "User can submit a valid order",
            "feature": "checkout",
            "route": "/checkout",
            "tags": ["@smoke", "@checkout"],
            "steps": ["Navigate to /checkout", "Fill email", "Click Submit"],
            "expected": ["Confirmation page displayed"],
            "source": "both"
        },
        {
            "id": "tc-checkout-02",
            "title": "Email field is required",
            "feature": "checkout",
            "route": "/checkout",
            "tags": ["@checkout"],
            "steps": ["Navigate to /checkout", "Leave email empty", "Click Submit"],
            "expected": ["Validation error shown"],
            "source": "jira"
        }
    ]'''

    mock_response = AsyncMock()
    mock_response.content = mock_response_json

    with patch("qa_agent.nodes.planner.ChatAnthropic") as MockChat:
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)
        MockChat.return_value = mock_model

        state = QAState(
            goal="Test checkout",
            acceptance_criteria=["User can submit order", "Email is required"],
            expected_ui=ExpectedUI(
                route="/checkout",
                elements=[UIElement(role="button", name="Submit", state="enabled")],
                flows=[],
            ),
        )
        result = await planner(state)

    assert "plan" in result
    assert len(result["plan"]) == 2
    tc = result["plan"][0]
    assert isinstance(tc, TestCase)
    assert tc.feature == "checkout"
    assert tc.route == "/checkout"
    assert "@smoke" in tc.tags


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generator_with_mock_llm():
    """Generator produces page objects + test code from mocked LLM response."""
    from qa_agent.nodes.generator import generator

    mock_response_json = '''{
        "page_objects": {
            "/checkout": "import { type Page, type Locator } from '@playwright/test';\\nexport class CheckoutPage { }"
        },
        "test_code": {
            "tests/checkout.spec.ts": "import { test, expect } from '@playwright/test';\\ntest('submit', async () => {});"
        }
    }'''

    mock_response = AsyncMock()
    mock_response.content = mock_response_json

    with patch("qa_agent.nodes.generator.ChatAnthropic") as MockChat:
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)
        MockChat.return_value = mock_model

        state = QAState(
            goal="Test checkout",
            plan=[
                TestCase(
                    id="tc-checkout-01",
                    title="Submit order",
                    feature="checkout",
                    route="/checkout",
                    steps=["Navigate", "Fill email", "Submit"],
                    expected=["Confirmation shown"],
                )
            ],
        )
        result = await generator(state)

    assert "page_objects" in result
    assert "test_code" in result
    assert "/checkout" in result["page_objects"]
    assert "tests/checkout.spec.ts" in result["test_code"]


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_executor_writes_files(tmp_path):
    """Executor writes page objects and test files to disk."""
    from qa_agent.nodes import executor as executor_mod

    # Patch the project root to use tmp_path
    original_root = executor_mod._PROJECT_ROOT
    executor_mod._PROJECT_ROOT = tmp_path

    try:
        state = QAState(
            goal="Test checkout",
            page_objects={"/checkout": "export class CheckoutPage {}"},
            test_code={"tests/checkout.spec.ts": "test('works', () => {});"},
            app_url="http://localhost:3000",
        )

        # Mock the subprocess to avoid needing actual playwright
        with patch("qa_agent.nodes.executor._run_playwright_tests") as mock_run:
            from qa_agent.schemas.models import RunResult
            mock_run.return_value = (
                RunResult(passed=True, failed_cases=[], logs="All passed"),
                None,
            )
            result = await executor_mod.executor(state)

        # Check files were written
        assert (tmp_path / "page_objects" / "CheckoutPage.ts").exists()
        assert (tmp_path / "tests_generated" / "checkout.spec.ts").exists()
        assert result["run_results"].passed is True
    finally:
        executor_mod._PROJECT_ROOT = original_root
