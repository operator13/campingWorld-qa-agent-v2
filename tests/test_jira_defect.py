"""Tests for the Jira defect surface — fingerprinting and dedup."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from qa_agent.schemas.models import RunResult
from qa_agent.surfaces.jira_defect import JiraDefectSurface, compute_fingerprint


class TestFingerprint:
    def test_same_inputs_same_fingerprint(self):
        """Identical inputs produce identical fingerprints."""
        fp1 = compute_fingerprint("/checkout", "app_defect", ["tc-1", "tc-2"])
        fp2 = compute_fingerprint("/checkout", "app_defect", ["tc-1", "tc-2"])
        assert fp1 == fp2

    def test_order_independent(self):
        """Failed case order doesn't affect fingerprint (sorted internally)."""
        fp1 = compute_fingerprint("/checkout", "app_defect", ["tc-2", "tc-1"])
        fp2 = compute_fingerprint("/checkout", "app_defect", ["tc-1", "tc-2"])
        assert fp1 == fp2

    def test_different_route_different_fingerprint(self):
        fp1 = compute_fingerprint("/checkout", "app_defect", ["tc-1"])
        fp2 = compute_fingerprint("/login", "app_defect", ["tc-1"])
        assert fp1 != fp2

    def test_different_class_different_fingerprint(self):
        fp1 = compute_fingerprint("/checkout", "app_defect", ["tc-1"])
        fp2 = compute_fingerprint("/checkout", "locator_drift", ["tc-1"])
        assert fp1 != fp2

    def test_different_cases_different_fingerprint(self):
        fp1 = compute_fingerprint("/checkout", "app_defect", ["tc-1"])
        fp2 = compute_fingerprint("/checkout", "app_defect", ["tc-2"])
        assert fp1 != fp2

    def test_fingerprint_is_short(self):
        """Fingerprint is a 16-char hex string."""
        fp = compute_fingerprint("/checkout", "app_defect", ["tc-1"])
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)


class TestJiraDefectSurface:
    def test_is_configured(self):
        """MCP-based surface is always 'configured' (auth handled by MCP)."""
        jira = JiraDefectSurface(project_key="QA")
        assert jira.is_configured is True

    def test_project_key_default(self):
        jira = JiraDefectSurface()
        assert jira.project_key == "QA"

    def test_project_key_custom(self):
        jira = JiraDefectSurface(project_key="TEST")
        assert jira.project_key == "TEST"


class TestFileOrDedup:
    @pytest.mark.asyncio
    async def test_dedup_finds_existing(self):
        """When an existing ticket is found, returns deduped."""
        jira = JiraDefectSurface(project_key="QA")

        with patch.object(jira, "find_existing", return_value="QA-123"):
            result = await jira.file_or_dedup(
                goal="test",
                route="/checkout",
                failure_class="app_defect",
                confidence=0.9,
                error="error",
                run_results=RunResult(passed=False, failed_cases=["tc-1"], logs=""),
            )

        assert result["action"] == "deduped"
        assert result["issue_key"] == "QA-123"

    @pytest.mark.asyncio
    async def test_creates_when_no_existing(self):
        """When no existing ticket, creates a new one."""
        jira = JiraDefectSurface(project_key="QA")

        with patch.object(jira, "find_existing", return_value=None), \
             patch.object(jira, "create_defect", return_value="QA-456"):
            result = await jira.file_or_dedup(
                goal="test",
                route="/checkout",
                failure_class="app_defect",
                confidence=0.9,
                error="error",
            )

        assert result["action"] == "created"
        assert result["issue_key"] == "QA-456"
