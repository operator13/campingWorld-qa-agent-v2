"""Tests for the weekly review module."""

from __future__ import annotations

import pytest

from qa_agent.memory import MemoryStore
from qa_agent.nodes.metrics import MetricsDB
from qa_agent.weekly_review import (
    _compute_grade_score,
    _score_to_grade,
    _trend_arrow,
    gather_review_stats,
    generate_prescriptions,
    generate_weekly_review,
    get_previous_stats,
    write_weekly_review,
)


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

class TestGrading:
    def test_perfect_score(self):
        stats = {
            "pass_rate": 1.0,
            "escape_rate": 0.0,
            "triage_accuracy": 1.0,
            "healer_cache_hit_rate": 1.0,
        }
        score = _compute_grade_score(stats)
        assert score == 100

    def test_zero_score(self):
        stats = {
            "pass_rate": 0.0,
            "escape_rate": 1.0,
            "triage_accuracy": 0.0,
            "healer_cache_hit_rate": 0.0,
        }
        score = _compute_grade_score(stats)
        assert score == 0

    def test_medium_score(self):
        stats = {
            "pass_rate": 0.7,
            "escape_rate": 0.1,
            "triage_accuracy": 0.8,
            "healer_cache_hit_rate": 0.3,
        }
        score = _compute_grade_score(stats)
        assert 50 <= score <= 80

    def test_grade_A(self):
        assert _score_to_grade(95) == "A"
        assert _score_to_grade(90) == "A"

    def test_grade_B(self):
        assert _score_to_grade(75) == "B"
        assert _score_to_grade(70) == "B"

    def test_grade_C(self):
        assert _score_to_grade(50) == "C+"
        assert _score_to_grade(40) == "C"

    def test_grade_F(self):
        assert _score_to_grade(5) == "F"
        assert _score_to_grade(0) == "F"


class TestTrendArrow:
    def test_up(self):
        assert _trend_arrow(0.8, 0.5) == "↑"

    def test_down(self):
        assert _trend_arrow(0.3, 0.7) == "↓"

    def test_flat(self):
        assert _trend_arrow(0.5, 0.51) == "—"

    def test_no_previous(self):
        assert _trend_arrow(0.5, None) == "—"


# ---------------------------------------------------------------------------
# Stats gathering
# ---------------------------------------------------------------------------

class TestGatherStats:
    def test_with_runs(self, tmp_path):
        db = MetricsDB(tmp_path / "test.db")
        for i in range(7):
            db.record_run(
                goal=f"t-{i}", route="/", passed=i < 5,
                failed_cases=[] if i < 5 else ["tc-1"],
                failure_class=None if i < 5 else "locator_drift",
                confidence=0.0 if i < 5 else 0.8,
                attempts=0, fingerprint=None,
                outcome="pass" if i < 5 else "failed",
            )

        memory = MemoryStore(memory_dir=tmp_path / "mem")
        stats = gather_review_stats(db=db, memory=memory)

        assert stats["total_runs"] == 7
        assert stats["passed_runs"] == 5
        assert stats["failed_runs"] == 2
        assert round(stats["pass_rate"], 2) == 0.71

    def test_empty_db(self, tmp_path):
        db = MetricsDB(tmp_path / "test.db")
        memory = MemoryStore(memory_dir=tmp_path / "mem")
        stats = gather_review_stats(db=db, memory=memory)

        assert stats["total_runs"] == 0
        assert stats["pass_rate"] == 0.0


# ---------------------------------------------------------------------------
# Prescriptions
# ---------------------------------------------------------------------------

class TestPrescriptions:
    def test_high_escape_rate(self, tmp_path):
        memory = MemoryStore(memory_dir=tmp_path)
        stats = {"escape_rate": 0.15, "escapes": 3, "triage_audited": 2,
                 "triage_accuracy": 0.8, "pass_rate": 0.8,
                 "flaky_tests": 0, "volatile_routes": 0,
                 "healer_cache_hit_rate": 0.3, "locator_entries": 5}
        prescriptions = generate_prescriptions(stats, memory=memory)
        assert any("escape rate" in p.lower() for p in prescriptions)

    def test_low_triage_accuracy(self, tmp_path):
        memory = MemoryStore(memory_dir=tmp_path)
        stats = {"escape_rate": 0.02, "escapes": 0, "triage_audited": 10,
                 "triage_accuracy": 0.55, "pass_rate": 0.8,
                 "flaky_tests": 0, "volatile_routes": 0,
                 "healer_cache_hit_rate": 0.3, "locator_entries": 5}
        prescriptions = generate_prescriptions(stats, memory=memory)
        assert any("triage accuracy" in p.lower() for p in prescriptions)

    def test_flaky_tests_flagged(self, tmp_path):
        memory = MemoryStore(memory_dir=tmp_path)
        for i in range(5):
            memory.record_test_result("tc-flaky", "/checkout", i < 2)

        stats = {"escape_rate": 0.0, "escapes": 0, "triage_audited": 0,
                 "triage_accuracy": 0.0, "pass_rate": 0.9,
                 "flaky_tests": 1, "volatile_routes": 0,
                 "healer_cache_hit_rate": 0.5, "locator_entries": 5}
        prescriptions = generate_prescriptions(stats, memory=memory)
        assert any("flaky" in p.lower() for p in prescriptions)

    def test_healthy_system(self, tmp_path):
        memory = MemoryStore(memory_dir=tmp_path)
        stats = {"escape_rate": 0.02, "escapes": 0, "triage_audited": 3,
                 "triage_accuracy": 0.85, "pass_rate": 0.95,
                 "flaky_tests": 0, "volatile_routes": 0,
                 "healer_cache_hit_rate": 0.4, "locator_entries": 5}
        prescriptions = generate_prescriptions(stats, memory=memory)
        assert any("healthy" in p.lower() for p in prescriptions)

    def test_volatile_routes_flagged(self, tmp_path):
        memory = MemoryStore(memory_dir=tmp_path)
        memory.update_route("/checkout", testids=["a"])
        for _ in range(10):
            memory.increment_route_changes("/checkout")

        stats = {"escape_rate": 0.0, "escapes": 0, "triage_audited": 0,
                 "triage_accuracy": 0.0, "pass_rate": 0.9,
                 "flaky_tests": 0, "volatile_routes": 1,
                 "healer_cache_hit_rate": 0.5, "locator_entries": 5}
        prescriptions = generate_prescriptions(stats, memory=memory)
        assert any("volatile" in p.lower() for p in prescriptions)


# ---------------------------------------------------------------------------
# Full review generation
# ---------------------------------------------------------------------------

class TestGenerateReview:
    def test_produces_complete_review(self, tmp_path):
        db = MetricsDB(tmp_path / "test.db")
        db.record_run(
            goal="test", route="/", passed=True,
            failed_cases=[], failure_class=None,
            confidence=0.0, attempts=0, fingerprint=None, outcome="pass",
        )
        memory = MemoryStore(memory_dir=tmp_path / "mem")

        review = generate_weekly_review(db=db, memory=memory)

        assert "date" in review
        assert "stats" in review
        assert "grade" in review
        assert "score" in review
        assert "prescriptions" in review
        assert "markdown" in review
        assert isinstance(review["score"], int)
        assert review["grade"] in ("A", "B+", "B", "B-", "C+", "C", "C-", "D", "F")

    def test_markdown_contains_stats_table(self, tmp_path):
        db = MetricsDB(tmp_path / "test.db")
        db.record_run(
            goal="test", route="/", passed=True,
            failed_cases=[], failure_class=None,
            confidence=0.0, attempts=0, fingerprint=None, outcome="pass",
        )
        memory = MemoryStore(memory_dir=tmp_path / "mem")

        review = generate_weekly_review(db=db, memory=memory)
        md = review["markdown"]

        assert "| Metric |" in md
        assert "| Total runs |" in md
        assert "| Pass rate |" in md
        assert "Grade:" in md
        assert "Prescriptions" in md

    def test_includes_trends_when_previous(self, tmp_path):
        db = MetricsDB(tmp_path / "test.db")
        db.record_run(
            goal="test", route="/", passed=True,
            failed_cases=[], failure_class=None,
            confidence=0.0, attempts=0, fingerprint=None, outcome="pass",
        )
        memory = MemoryStore(memory_dir=tmp_path / "mem")

        previous = {"pass_rate": 0.5, "escape_rate": 0.2, "triage_accuracy": 0.6, "healer_cache_hit_rate": 0.1}
        review = generate_weekly_review(db=db, memory=memory, previous_stats=previous)

        assert review["trends"]
        assert "pass_rate" in review["trends"]


# ---------------------------------------------------------------------------
# Write + read previous
# ---------------------------------------------------------------------------

class TestWriteAndReadPrevious:
    def test_write_review(self, tmp_path):
        review = {
            "date": "2026-08-17",
            "grade": "B",
            "markdown": "## Week of 2026-08-17\n\n### Stats\n| Metric | Value | Trend |\n|--------|-------|-------|\n| Total runs | 7 | — |\n| Pass rate | 71% | — |\n",
        }
        write_weekly_review(review, memory_dir=tmp_path)

        filepath = tmp_path / "WEEKLY_REVIEW.md"
        assert filepath.exists()
        content = filepath.read_text()
        assert "2026-08-17" in content
        assert "71%" in content

    def test_read_previous_stats(self, tmp_path):
        filepath = tmp_path / "WEEKLY_REVIEW.md"
        filepath.write_text(
            "# Weekly Reviews\n\n"
            "## Week of 2026-08-10\n\n"
            "### Stats\n"
            "| Metric | Value | Trend |\n"
            "|--------|-------|-------|\n"
            "| Total runs | 7 | — |\n"
            "| Pass rate | 85% | — |\n"
            "| Escape rate | 5% | — |\n"
            "| Triage accuracy | 80% | — |\n"
            "| Healer cache hit | 30% | — |\n"
        )

        previous = get_previous_stats(memory_dir=tmp_path)
        assert previous is not None
        assert previous["pass_rate"] == 0.85
        assert previous["escape_rate"] == 0.05
        assert previous["triage_accuracy"] == 0.80

    def test_read_previous_returns_none_on_empty(self, tmp_path):
        assert get_previous_stats(memory_dir=tmp_path) is None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCLIReview:
    def test_review_weekly_runs(self):
        """CLI review weekly doesn't crash."""
        from qa_agent.cli import _review_weekly
        _review_weekly()
