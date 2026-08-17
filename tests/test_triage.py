"""Tests for the Triage node."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from qa_agent.nodes.triage import _parse_response, triage
from qa_agent.schemas.models import RunResult
from qa_agent.state import QAState


class TestTriageParseResponse:
    """Test the response parser independently."""

    def test_parses_locator_drift(self):
        mock = AsyncMock()
        mock.content = '{"failure_class": "locator_drift", "confidence": 0.9, "reasoning": "selector not found"}'
        result = _parse_response(mock)
        assert result["failure_class"] == "locator_drift"
        assert result["confidence"] == 0.9

    def test_parses_app_defect(self):
        mock = AsyncMock()
        mock.content = '{"failure_class": "app_defect", "confidence": 0.85, "reasoning": "assertion mismatch"}'
        result = _parse_response(mock)
        assert result["failure_class"] == "app_defect"
        assert result["confidence"] == 0.85

    def test_clamps_confidence(self):
        mock = AsyncMock()
        mock.content = '{"failure_class": "unknown", "confidence": 1.5}'
        result = _parse_response(mock)
        assert result["confidence"] == 1.0

        mock.content = '{"failure_class": "unknown", "confidence": -0.5}'
        result = _parse_response(mock)
        assert result["confidence"] == 0.0

    def test_invalid_class_defaults_to_unknown(self):
        mock = AsyncMock()
        mock.content = '{"failure_class": "network_error", "confidence": 0.8}'
        result = _parse_response(mock)
        assert result["failure_class"] == "unknown"

    def test_unparseable_defaults_safely(self):
        mock = AsyncMock()
        mock.content = "I cannot determine the issue"
        result = _parse_response(mock)
        assert result["failure_class"] == "unknown"
        assert result["confidence"] == 0.0

    def test_parses_json_in_code_block(self):
        mock = AsyncMock()
        mock.content = '```json\n{"failure_class": "locator_drift", "confidence": 0.8}\n```'
        result = _parse_response(mock)
        assert result["failure_class"] == "locator_drift"


@pytest.mark.asyncio
async def test_triage_with_mock_llm():
    """Triage produces failure_class + confidence from mocked LLM."""
    mock_response = AsyncMock()
    mock_response.content = '{"failure_class": "locator_drift", "confidence": 0.92, "reasoning": "Selector not found but element exists with new name"}'

    with patch("qa_agent.nodes.triage.ChatAnthropic") as MockChat:
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(return_value=mock_response)
        MockChat.return_value = mock_model

        state = QAState(
            goal="Test checkout",
            error="TimeoutError: locator.click: Timeout 30000ms exceeded.\nWaiting for getByRole('button', { name: 'Submit' })",
            run_results=RunResult(
                passed=False,
                failed_cases=["tc-checkout-01"],
                logs="Error: locator not found",
            ),
            attempts=0,
        )
        result = await triage(state)

    assert result["failure_class"] == "locator_drift"
    assert result["confidence"] == 0.92
