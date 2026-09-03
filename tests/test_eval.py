"""Tests for the evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path

from qa_agent.eval.run_eval import (
    GOLDEN_DIR,
    THRESHOLDS,
    run_full_eval,
    score_ac_coverage,
    score_locator_quality,
    score_triage_accuracy,
)


class TestACCoverage:
    def test_full_coverage(self):
        """All ACs covered → 1.0."""
        acs = ["User can submit order", "Email is required"]
        tests = [
            {"title": "User submits order", "steps": ["User fills email", "User clicks submit order"], "expected": ["Order confirmed"]},
            {"title": "Email is required validation", "steps": ["Leave email empty"], "expected": ["Error: email is required"]},
        ]
        result = score_ac_coverage(acs, tests)
        assert result["score"] == 1.0
        assert result["uncovered"] == []

    def test_partial_coverage(self):
        """Some ACs uncovered → fractional score."""
        acs = ["User can submit order", "Email is required", "Password must be 8 chars"]
        tests = [
            {"title": "User submits order successfully", "steps": ["User clicks submit order"], "expected": ["Order confirmed"]},
        ]
        result = score_ac_coverage(acs, tests)
        assert 0 < result["score"] < 1.0
        assert len(result["uncovered"]) >= 1

    def test_no_acs(self):
        """No ACs → score is 1.0 (vacuously true)."""
        result = score_ac_coverage([], [])
        assert result["score"] == 1.0

    def test_no_tests(self):
        """ACs but no tests → score is 0.0."""
        result = score_ac_coverage(["User can login"], [])
        assert result["score"] == 0.0

    def test_golden_fixture_coverage(self):
        """The golden fixture has adequate AC coverage."""
        intake = json.loads((GOLDEN_DIR / "sample_intake.json").read_text())
        plan = json.loads((GOLDEN_DIR / "expected_plan.json").read_text())
        result = score_ac_coverage(intake["acceptance_criteria"], plan)
        assert result["score"] >= THRESHOLDS["ac_coverage"], (
            f"Golden AC coverage {result['score']:.2f} below threshold {THRESHOLDS['ac_coverage']}"
        )


class TestLocatorQuality:
    def test_all_good_locators(self):
        """Only getByRole/getByTestId → 1.0."""
        po = {
            "/checkout": (
                "this.btn = page.getByRole('button', { name: 'Submit' });\n"
                "this.email = page.getByTestId('checkout-email');\n"
            )
        }
        result = score_locator_quality(po)
        assert result["score"] == 1.0
        assert result["brittle"] == 0

    def test_mixed_locators(self):
        """Mix of good and brittle → fractional score."""
        po = {
            "/checkout": (
                "this.btn = page.getByRole('button', { name: 'Submit' });\n"
                "this.bad = page.locator('.btn-primary');\n"
                "this.email = page.getByTestId('email');\n"
            )
        }
        result = score_locator_quality(po)
        assert result["good"] == 2
        assert result["brittle"] == 1
        assert 0.6 < result["score"] < 0.7  # 2/3 ≈ 0.667

    def test_all_brittle(self):
        """Only CSS selectors → 0.0."""
        po = {"/page": "this.x = page.locator('.foo');\nthis.y = page.locator('#bar');\n"}
        result = score_locator_quality(po)
        assert result["score"] == 0.0

    def test_empty_page_objects(self):
        """No page objects → 1.0 (nothing to score)."""
        result = score_locator_quality({})
        assert result["score"] == 1.0


class TestTriageAccuracy:
    def test_all_correct(self):
        """All classifications correct → 1.0."""
        expected = [
            {"scenario": "s1", "expected_class": "locator_drift", "expected_confidence_min": 0.75},
            {"scenario": "s2", "expected_class": "app_defect", "expected_confidence_min": 0.80},
        ]
        results = [
            {"failure_class": "locator_drift", "confidence": 0.9},
            {"failure_class": "app_defect", "confidence": 0.85},
        ]
        score = score_triage_accuracy(results, expected)
        assert score["score"] == 1.0

    def test_wrong_class(self):
        """Wrong classification → miss."""
        expected = [
            {"scenario": "s1", "expected_class": "app_defect", "expected_confidence_min": 0.8},
        ]
        results = [
            {"failure_class": "locator_drift", "confidence": 0.9},
        ]
        score = score_triage_accuracy(results, expected)
        assert score["score"] == 0.0
        assert len(score["misses"]) == 1

    def test_low_confidence(self):
        """Right class but confidence below threshold → miss."""
        expected = [
            {"scenario": "s1", "expected_class": "locator_drift", "expected_confidence_min": 0.75},
        ]
        results = [
            {"failure_class": "locator_drift", "confidence": 0.5},
        ]
        score = score_triage_accuracy(results, expected)
        assert score["score"] == 0.0

    def test_no_expected(self):
        """No expected scenarios → 1.0."""
        score = score_triage_accuracy([], [])
        assert score["score"] == 1.0

    def test_missing_results(self):
        """Fewer results than expected → misses for missing."""
        expected = [
            {"scenario": "s1", "expected_class": "locator_drift", "expected_confidence_min": 0.75},
            {"scenario": "s2", "expected_class": "app_defect", "expected_confidence_min": 0.80},
        ]
        results = [
            {"failure_class": "locator_drift", "confidence": 0.9},
        ]
        score = score_triage_accuracy(results, expected)
        assert score["score"] == 0.5
        assert score["correct"] == 1


class TestFullEval:
    def test_all_pass(self):
        """Full eval with good inputs passes."""
        result = run_full_eval(
            acceptance_criteria=["User can submit order"],
            test_cases=[
                {"title": "User submits order", "steps": ["User clicks submit order"], "expected": ["Order confirmed"]},
            ],
            page_objects={"/checkout": "page.getByRole('button', { name: 'Submit' });"},
            triage_results=[{"failure_class": "locator_drift", "confidence": 0.9}],
            triage_expected=[
                {"scenario": "s1", "expected_class": "locator_drift", "expected_confidence_min": 0.75},
            ],
        )
        assert result["passed"] is True

    def test_fail_on_low_ac_coverage(self):
        """Full eval fails when AC coverage is below threshold."""
        result = run_full_eval(
            acceptance_criteria=["AC1", "AC2", "AC3", "AC4", "AC5"],
            test_cases=[],
            page_objects={},
            triage_results=[],
            triage_expected=[],
        )
        assert result["passed"] is False
