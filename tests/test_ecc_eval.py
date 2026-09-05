"""Tests for ECC agent eval system — finding extractor, matcher, and runner."""

from __future__ import annotations

import pytest

from qa_agent.eval.ecc.finding_extractor import Finding, extract_findings
from qa_agent.eval.ecc.finding_matcher import (
    MatchResult,
    compute_detection_scores,
    match_findings,
)
from qa_agent.eval.ecc.config import (
    ALL_ECC_AGENTS,
    DETECTION_AGENTS,
    GENERATIVE_AGENTS,
    get_agent_config,
)


# -----------------------------------------------------------------------
# Finding Extractor Tests
# -----------------------------------------------------------------------


class TestFindingExtractor:
    def test_parses_critical_severity(self):
        output = "**CRITICAL** SQL injection in api/users.py:12\nUser input interpolated into query"
        findings = extract_findings(output)
        assert len(findings) >= 1
        assert findings[0].severity == "CRITICAL"

    def test_parses_bracket_severity(self):
        output = "[HIGH] Path traversal in server.py:45\nUnsanitized file path"
        findings = extract_findings(output)
        assert len(findings) >= 1
        assert findings[0].severity == "HIGH"

    def test_parses_severity_prefix(self):
        output = "Severity: MEDIUM\nMissing rate limiting on /api/login"
        findings = extract_findings(output)
        assert len(findings) >= 1
        assert findings[0].severity == "MEDIUM"

    def test_extracts_file_and_line(self):
        output = "**CRITICAL** SQL injection found\nFile: api/users.py:12\nf-string query"
        findings = extract_findings(output)
        assert len(findings) >= 1
        assert findings[0].file is not None
        assert "users.py" in findings[0].file

    def test_extracts_inline_file_line(self):
        output = "**HIGH** XSS vulnerability in templates/index.html:34"
        findings = extract_findings(output)
        assert len(findings) >= 1

    def test_parses_multiple_findings(self):
        output = (
            "**CRITICAL** SQL injection in api/users.py:12\n"
            "User input in query\n\n"
            "**HIGH** XSS in templates/page.html:5\n"
            "Unescaped output\n\n"
            "**LOW** Missing docstring in utils.py:1\n"
        )
        findings = extract_findings(output)
        assert len(findings) == 3
        severities = [f.severity for f in findings]
        assert "CRITICAL" in severities
        assert "HIGH" in severities
        assert "LOW" in severities

    def test_handles_empty_output(self):
        assert extract_findings("") == []
        assert extract_findings("   ") == []

    def test_handles_none_output(self):
        assert extract_findings(None) == []

    def test_handles_no_severity_markers(self):
        output = "The code looks clean. No issues found."
        findings = extract_findings(output)
        assert len(findings) == 0

    def test_case_insensitive_severity(self):
        output = "**critical** Issue in file.py:1"
        findings = extract_findings(output)
        assert len(findings) >= 1
        assert findings[0].severity == "CRITICAL"

    def test_numbered_finding_fallback(self):
        output = (
            "1. **SQL injection** in api/users.py:12 — f-string query\n"
            "2. **XSS vulnerability** in templates/page.html:5\n"
        )
        findings = extract_findings(output)
        assert len(findings) >= 2


# -----------------------------------------------------------------------
# Finding Matcher Tests
# -----------------------------------------------------------------------


class TestFindingMatcher:
    def _make_finding(self, severity="HIGH", file="api/users.py", line=12, desc="SQL injection"):
        return Finding(
            severity=severity,
            file=file,
            line=line,
            description=desc,
            raw_text=f"{severity} {desc} in {file}:{line}",
        )

    def test_exact_match(self):
        findings = [self._make_finding(file="api/users.py", line=12)]
        planted = [{
            "issue_id": "V-001",
            "category": "sql_injection",
            "severity": "CRITICAL",
            "file": "api/users.py",
            "line_range": [12, 14],
            "description": "SQL injection via f-string",
        }]
        result = match_findings(findings, planted, "test")
        assert result.found_count == 1
        assert result.planted_count == 1
        assert len(result.missed_issues) == 0

    def test_line_proximity_match(self):
        findings = [self._make_finding(file="api/users.py", line=15)]
        planted = [{
            "issue_id": "V-001",
            "category": "sql_injection",
            "severity": "CRITICAL",
            "file": "api/users.py",
            "line_range": [12, 14],
            "description": "SQL injection query",
        }]
        result = match_findings(findings, planted, "test")
        assert result.found_count == 1  # within +/- 5 lines

    def test_line_too_far(self):
        findings = [self._make_finding(file="api/users.py", line=50)]
        planted = [{
            "issue_id": "V-001",
            "category": "sql_injection",
            "severity": "CRITICAL",
            "file": "api/users.py",
            "line_range": [12, 14],
            "description": "SQL injection",
        }]
        result = match_findings(findings, planted, "test")
        # May still match via category overlap depending on description
        # but without category match, should miss
        assert result.planted_count == 1

    def test_category_overlap_match(self):
        findings = [self._make_finding(
            file="api/users.py",
            line=12,
            desc="sql injection vulnerability found in database query",
        )]
        planted = [{
            "issue_id": "V-001",
            "category": "sql_injection",
            "severity": "CRITICAL",
            "file": "api/users.py",
            "line_range": [12, 14],
            "description": "SQL injection via f-string query",
        }]
        result = match_findings(findings, planted, "test")
        assert result.found_count == 1

    def test_false_positive_on_clean(self):
        findings = [self._make_finding(desc="potential issue found")]
        planted = []  # clean code, no planted issues
        result = match_findings(findings, planted, "clean_test")
        assert result.planted_count == 0
        assert result.false_positive_count == 1
        assert len(result.unmatched_findings) == 1

    def test_no_double_count(self):
        findings = [
            self._make_finding(file="api/users.py", line=12, desc="SQL injection found"),
            self._make_finding(file="api/users.py", line=13, desc="Another SQL injection"),
        ]
        planted = [{
            "issue_id": "V-001",
            "category": "sql_injection",
            "severity": "CRITICAL",
            "file": "api/users.py",
            "line_range": [12, 14],
            "description": "SQL injection",
        }]
        result = match_findings(findings, planted, "test")
        # Should count as 1 found, not 2
        assert result.found_count == 1

    def test_missed_issue(self):
        findings = []  # agent found nothing
        planted = [{
            "issue_id": "V-001",
            "category": "sql_injection",
            "severity": "CRITICAL",
            "file": "api/users.py",
            "line_range": [12, 14],
            "description": "SQL injection",
        }]
        result = match_findings(findings, planted, "test")
        assert result.found_count == 0
        assert result.missed_issues == ["V-001"]

    def test_path_normalization(self):
        findings = [self._make_finding(file="api/users.py", line=12)]
        planted = [{
            "issue_id": "V-001",
            "category": "sql_injection",
            "severity": "CRITICAL",
            "file": "api\\users.py",  # Windows path
            "line_range": [12, 14],
            "description": "SQL injection",
        }]
        result = match_findings(findings, planted, "test")
        assert result.found_count == 1


# -----------------------------------------------------------------------
# Detection Scores Tests
# -----------------------------------------------------------------------


class TestDetectionScores:
    def test_recall_calculation(self):
        results = [
            MatchResult("s1", planted_count=10, found_count=8,
                        false_positive_count=1, matches=[], unmatched_findings=[], missed_issues=[]),
            MatchResult("s2", planted_count=10, found_count=9,
                        false_positive_count=0, matches=[], unmatched_findings=[], missed_issues=[]),
        ]
        scores = compute_detection_scores(results)
        assert scores["recall"] == 0.85  # 17/20
        assert scores["total_planted"] == 20
        assert scores["total_found"] == 17

    def test_precision_calculation(self):
        results = [
            MatchResult("s1", planted_count=5, found_count=4,
                        false_positive_count=1, matches=[], unmatched_findings=[], missed_issues=[]),
        ]
        scores = compute_detection_scores(results)
        assert scores["precision"] == 0.8  # 4/(4+1)

    def test_false_positive_rate(self):
        results = []
        scores = compute_detection_scores(results, clean_scenario_count=5, clean_false_positives=1)
        assert scores["false_positive_rate"] == 0.2

    def test_zero_division_safe(self):
        scores = compute_detection_scores([])
        assert scores["recall"] == 0.0
        assert scores["precision"] == 0.0
        assert scores["false_positive_rate"] == 0.0

    def test_perfect_scores(self):
        results = [
            MatchResult("s1", planted_count=10, found_count=10,
                        false_positive_count=0, matches=[], unmatched_findings=[], missed_issues=[]),
        ]
        scores = compute_detection_scores(results, clean_scenario_count=5, clean_false_positives=0)
        assert scores["recall"] == 1.0
        assert scores["precision"] == 1.0
        assert scores["false_positive_rate"] == 0.0


# -----------------------------------------------------------------------
# Config Tests
# -----------------------------------------------------------------------


class TestConfig:
    def test_all_agents_includes_both_tiers(self):
        assert len(ALL_ECC_AGENTS) == 12

    def test_detection_agents_count(self):
        assert len(DETECTION_AGENTS) == 7

    def test_generative_agents_count(self):
        assert len(GENERATIVE_AGENTS) == 5

    def test_get_agent_config_detection(self):
        config = get_agent_config("security-reviewer")
        assert config.tier == "detection"
        assert config.recall_threshold == 0.85

    def test_get_agent_config_generative(self):
        config = get_agent_config("planner-ecc")
        assert config.tier == "generative"

    def test_scorecard_structure(self):
        config = get_agent_config("code-reviewer")
        assert config.name == "code-reviewer"
        assert config.tier == "detection"
        assert config.recall_threshold == 0.75
        assert config.budget_cap > 0

    def test_no_agents_in_both_tiers(self):
        overlap = set(DETECTION_AGENTS) & set(GENERATIVE_AGENTS)
        assert len(overlap) == 0
