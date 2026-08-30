"""Tests for Site Health Score system."""

import json
import pytest
from pathlib import Path

from qa_agent.health import (
    parse_playwright_json,
    compute_domain_scores,
    compute_site_health,
    build_health_report,
    format_health_markdown,
)


# Sample Playwright JSON output structure
SAMPLE_PLAYWRIGHT_JSON = {
    "suites": [
        {
            "title": "Homepage",
            "specs": [
                {"title": "hero banner visible", "tests": [{"status": "expected", "results": [{"duration": 1000}]}]},
                {"title": "logo visible", "tests": [{"status": "expected", "results": [{"duration": 500}]}]},
                {"title": "search works", "tests": [{"status": "expected", "results": [{"duration": 2000}]}]},
            ],
            "suites": [],
        },
        {
            "title": "Cart",
            "specs": [
                {"title": "empty cart heading", "tests": [{"status": "expected", "results": [{"duration": 800}]}]},
                {"title": "add to cart", "tests": [{"status": "unexpected", "results": [{"duration": 5000}]}]},
            ],
            "suites": [],
        },
        {
            "title": "Search",
            "specs": [
                {"title": "results visible", "tests": [{"status": "expected", "results": [{"duration": 1500}]}]},
                {"title": "filter works", "tests": [{"status": "skipped", "results": []}]},
            ],
            "suites": [],
        },
    ],
}


@pytest.fixture
def sample_json(tmp_path):
    path = tmp_path / "results.json"
    path.write_text(json.dumps(SAMPLE_PLAYWRIGHT_JSON))
    return path


class TestParsePlaywrightJson:

    def test_parses_domains(self, sample_json):
        results = parse_playwright_json(sample_json)
        names = [r["name"] for r in results]
        assert "Homepage" in names
        assert "Cart" in names
        assert "Search" in names

    def test_counts_passed(self, sample_json):
        results = parse_playwright_json(sample_json)
        homepage = next(r for r in results if r["name"] == "Homepage")
        assert homepage["passed"] == 3
        assert homepage["failed"] == 0
        assert homepage["total"] == 3

    def test_counts_failed(self, sample_json):
        results = parse_playwright_json(sample_json)
        cart = next(r for r in results if r["name"] == "Cart")
        assert cart["passed"] == 1
        assert cart["failed"] == 1
        assert cart["total"] == 2

    def test_counts_skipped(self, sample_json):
        results = parse_playwright_json(sample_json)
        search = next(r for r in results if r["name"] == "Search")
        assert search["skipped"] == 1

    def test_empty_json(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text('{"suites": []}')
        results = parse_playwright_json(path)
        assert results == []


class TestComputeDomainScores:

    def test_healthy_domain(self):
        results = [{"name": "Homepage", "passed": 13, "failed": 0, "skipped": 0, "total": 13, "duration_ms": 5000}]
        scores = compute_domain_scores(results)
        assert scores[0]["score"] == 1.0
        assert scores[0]["status"] == "HEALTHY"

    def test_degraded_domain(self):
        results = [{"name": "Search", "passed": 9, "failed": 1, "skipped": 0, "total": 10, "duration_ms": 5000}]
        scores = compute_domain_scores(results)
        assert scores[0]["score"] == 0.9
        assert scores[0]["status"] == "DEGRADED"

    def test_critical_domain(self):
        results = [{"name": "Cart", "passed": 1, "failed": 4, "skipped": 0, "total": 5, "duration_ms": 5000}]
        scores = compute_domain_scores(results)
        assert scores[0]["score"] == 0.2
        assert scores[0]["status"] == "CRITICAL"

    def test_critical_path_flagged(self):
        results = [{"name": "Cart", "passed": 3, "failed": 0, "skipped": 0, "total": 3, "duration_ms": 1000}]
        scores = compute_domain_scores(results)
        assert scores[0]["is_critical"] is True
        assert scores[0]["weight"] == 2.0

    def test_non_critical_domain(self):
        results = [{"name": "Good Sam", "passed": 6, "failed": 0, "skipped": 0, "total": 6, "duration_ms": 1000}]
        scores = compute_domain_scores(results)
        assert scores[0]["is_critical"] is False
        assert scores[0]["weight"] == 1.0

    def test_footer_low_weight(self):
        results = [{"name": "Footer & Legal Pages", "passed": 13, "failed": 0, "skipped": 0, "total": 13, "duration_ms": 1000}]
        scores = compute_domain_scores(results)
        assert scores[0]["weight"] == 0.5


class TestComputeSiteHealth:

    def test_all_passing(self):
        domain_scores = [
            {"name": "Homepage", "passed": 10, "failed": 0, "total": 10, "score": 1.0, "weight": 1.0},
            {"name": "Cart", "passed": 5, "failed": 0, "total": 5, "score": 1.0, "weight": 2.0},
        ]
        health = compute_site_health(domain_scores)
        assert health["overall_score"] == 1.0
        assert health["overall_status"] == "HEALTHY"
        assert health["total_passed"] == 15
        assert health["total_failed"] == 0

    def test_weighted_score(self):
        domain_scores = [
            {"name": "Footer", "passed": 10, "failed": 0, "skipped": 0, "total": 10, "score": 1.0, "weight": 0.5},
            {"name": "Cart", "passed": 0, "failed": 5, "skipped": 0, "total": 5, "score": 0.0, "weight": 2.0},
        ]
        health = compute_site_health(domain_scores)
        # Footer: 1.0 * 0.5 * 10 = 5.0, Cart: 0.0 * 2.0 * 5 = 0.0
        # Total weight: 0.5*10 + 2.0*5 = 15.0, Score: 5.0/15.0 = 0.333
        assert health["overall_score"] == pytest.approx(0.3333, abs=0.001)
        assert health["overall_status"] == "CRITICAL"

    def test_trend_stable(self):
        domain_scores = [
            {"name": "Homepage", "passed": 10, "failed": 0, "total": 10, "score": 1.0, "weight": 1.0},
        ]
        health = compute_site_health(domain_scores, previous_score=1.0)
        assert health["trend"]["status"] == "stable"

    def test_trend_declining(self):
        domain_scores = [
            {"name": "Cart", "passed": 3, "failed": 2, "total": 5, "score": 0.6, "weight": 2.0},
        ]
        health = compute_site_health(domain_scores, previous_score=0.95)
        assert health["trend"]["status"] == "declining"

    def test_trend_improving(self):
        domain_scores = [
            {"name": "Cart", "passed": 5, "failed": 0, "total": 5, "score": 1.0, "weight": 2.0},
        ]
        health = compute_site_health(domain_scores, previous_score=0.80)
        assert health["trend"]["status"] == "improving"

    def test_empty_domains(self):
        health = compute_site_health([])
        assert health["overall_score"] == 0.0
        assert health["overall_status"] == "CRITICAL"


class TestBuildHealthReport:

    def test_report_has_required_fields(self):
        domain_scores = [
            {"name": "Cart", "passed": 3, "failed": 0, "total": 3, "score": 1.0,
             "status": "HEALTHY", "weight": 2.0, "is_critical": True},
        ]
        site_health = compute_site_health(domain_scores)
        report = build_health_report(domain_scores, site_health, run_id="test-run")

        assert "timestamp" in report
        assert "overall_score" in report
        assert "overall_status" in report
        assert "domains" in report
        assert "critical_domains" in report
        assert report["run_id"] == "test-run"
        assert "Cart" in report["critical_domains"]


class TestFormatHealthMarkdown:

    def test_markdown_has_sections(self):
        report = {
            "overall_score": 0.95,
            "overall_status": "HEALTHY",
            "total_passed": 120,
            "total_failed": 5,
            "total_tests": 125,
            "total_skipped": 0,
            "run_id": "test",
            "timestamp": "2026-08-30",
            "domains": [
                {"name": "Cart", "passed": 3, "failed": 0, "total": 3,
                 "score": 1.0, "status": "HEALTHY", "weight": 2.0, "is_critical": True},
            ],
            "trend": {"delta": 0.0, "status": "stable", "previous_score": 0.95},
        }
        md = format_health_markdown(report)
        assert "# CampingWorld Site Health Report" in md
        assert "95.0% HEALTHY" in md
        assert "## Domain Breakdown" in md
        assert "Cart" in md
        assert "STABLE" in md
