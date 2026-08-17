"""Tests for the defect_report node."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from qa_agent.nodes.defect_report import _build_report, defect_report
from qa_agent.schemas.models import RunResult, TestCase
from qa_agent.state import QAState


class TestBuildReport:
    def test_includes_all_fields(self):
        state = QAState(
            goal="Test checkout",
            failure_class="app_defect",
            confidence=0.92,
            attempts=2,
            error="AssertionError: wrong value",
            run_results=RunResult(
                passed=False,
                failed_cases=["tc-1", "tc-2"],
                logs="Error log here",
                screenshots=["/tmp/fail.png"],
            ),
            plan=[
                TestCase(
                    id="tc-1", title="Submit", feature="checkout",
                    route="/checkout", steps=[], expected=[],
                )
            ],
        )
        report = _build_report(state)
        assert report["goal"] == "Test checkout"
        assert report["failure_class"] == "app_defect"
        assert report["confidence"] == 0.92
        assert report["attempts"] == 2
        assert report["fingerprint"]  # not empty
        assert len(report["failed_cases"]) == 2

    def test_fingerprint_is_stable(self):
        """Same state → same fingerprint."""
        state = QAState(
            goal="test",
            failure_class="app_defect",
            run_results=RunResult(passed=False, failed_cases=["tc-1"], logs=""),
            plan=[TestCase(id="tc-1", title="t", feature="f", route="/r", steps=[], expected=[])],
        )
        r1 = _build_report(state)
        r2 = _build_report(state)
        assert r1["fingerprint"] == r2["fingerprint"]


class TestDefectReportNode:
    @pytest.mark.asyncio
    async def test_files_via_mcp(self):
        """Defect report attempts to file via Atlassian MCP."""
        state = QAState(
            goal="Test login",
            failure_class="app_defect",
            confidence=0.88,
            error="Login failed",
            attempts=1,
        )

        mock_result = {"action": "created", "issue_key": "QA-999", "fingerprint": "abc"}

        with patch("qa_agent.nodes.defect_report.JiraDefectSurface") as MockJira:
            instance = MockJira.return_value
            instance.file_or_dedup = AsyncMock(return_value=mock_result)

            result = await defect_report(state)

        assert "QA-999" in result["error"]

    @pytest.mark.asyncio
    async def test_graceful_on_mcp_failure(self):
        """When MCP fails, still returns a defect error string."""
        state = QAState(
            goal="Test login",
            failure_class="app_defect",
            confidence=0.88,
            error="Login failed",
            attempts=1,
        )

        with patch("qa_agent.nodes.defect_report.JiraDefectSurface") as MockJira:
            instance = MockJira.return_value
            instance.file_or_dedup = AsyncMock(side_effect=Exception("MCP down"))

            result = await defect_report(state)

        assert "DEFECT" in result["error"]
