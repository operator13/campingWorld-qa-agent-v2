"""Tests for the Human Review surface."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from qa_agent.schemas.models import RunResult
from qa_agent.state import QAState
from qa_agent.surfaces.human_review import _build_review_payload, human_review


class TestBuildReviewPayload:
    def test_includes_triage_data(self):
        state = QAState(
            goal="Test checkout",
            failure_class="locator_drift",
            confidence=0.55,
            attempts=1,
            error="Locator not found",
        )
        payload = _build_review_payload(state)
        assert payload["goal"] == "Test checkout"
        assert payload["triage_guess"] == "locator_drift"
        assert payload["confidence"] == 0.55
        assert payload["attempts"] == 1
        assert "error" in payload
        assert "instructions" in payload

    def test_includes_run_results(self):
        state = QAState(
            goal="test",
            run_results=RunResult(
                passed=False,
                failed_cases=["tc-1", "tc-2"],
                logs="timeout error",
                screenshots=["/tmp/fail.png"],
            ),
        )
        payload = _build_review_payload(state)
        assert payload["failed_cases"] == ["tc-1", "tc-2"]
        assert "screenshots" in payload

    def test_truncates_long_content(self):
        state = QAState(
            goal="test",
            error="x" * 5000,
            dom_snapshot="y" * 5000,
        )
        payload = _build_review_payload(state)
        assert len(payload["error"]) == 2000
        assert len(payload["dom_snapshot_preview"]) == 1000


class TestHumanReviewNode:
    def test_heal_decision_routes_to_healer(self):
        """Human choosing 'heal' routes to healer node."""
        state = QAState(
            goal="test",
            failure_class="unknown",
            confidence=0.5,
        )

        with patch("qa_agent.surfaces.human_review.interrupt", return_value={"decision": "heal"}):
            result = human_review(state)

        assert result.goto == "healer"
        assert result.update["failure_class"] == "locator_drift"

    def test_defect_decision_routes_to_defect_report(self):
        """Human choosing 'defect' routes to defect_report node."""
        state = QAState(
            goal="test",
            failure_class="unknown",
            confidence=0.5,
        )

        with patch("qa_agent.surfaces.human_review.interrupt", return_value={"decision": "defect"}):
            result = human_review(state)

        assert result.goto == "defect_report"
        assert result.update["failure_class"] == "app_defect"

    def test_unknown_decision_defaults_to_defect(self):
        """An unrecognized decision defaults to defect_report (safe path)."""
        state = QAState(goal="test", confidence=0.5)

        with patch("qa_agent.surfaces.human_review.interrupt", return_value={"decision": "something_else"}):
            result = human_review(state)

        assert result.goto == "defect_report"

    def test_string_response_defaults_to_defect(self):
        """A non-dict interrupt response defaults to defect_report."""
        state = QAState(goal="test", confidence=0.5)

        with patch("qa_agent.surfaces.human_review.interrupt", return_value="heal"):
            result = human_review(state)

        assert result.goto == "defect_report"
