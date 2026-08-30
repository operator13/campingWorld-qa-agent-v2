"""Tests for the Eval Agent — scorecard, regression, eval runner."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from qa_agent.eval.eval_runner import (
    build_synthetic_state,
    load_triage_scenarios,
)
from qa_agent.eval.regression import detect_regression
from qa_agent.eval.scorecard import (
    build_scorecard,
    save_scorecard,
    load_latest_scorecard,
    _compute_category_breakdown,
)


# ---------------------------------------------------------------------------
# Golden data loading tests
# ---------------------------------------------------------------------------

class TestLoadScenarios:

    def test_loads_all_30_scenarios(self):
        scenarios, skipped = load_triage_scenarios()
        assert len(scenarios) == 30
        assert skipped == 0

    def test_skips_expired_scenarios(self, tmp_path):
        golden = [
            {
                "scenario": "expired_one",
                "category": "locator_drift",
                "error": "TimeoutError",
                "expected_class": "locator_drift",
                "expected_confidence_min": 0.75,
                "valid_until": "2020-01-01",
            },
            {
                "scenario": "valid_one",
                "category": "app_defect",
                "error": "AssertionError",
                "expected_class": "app_defect",
                "expected_confidence_min": 0.80,
                "valid_until": "2099-01-01",
            },
        ]
        path = tmp_path / "test_golden.json"
        path.write_text(json.dumps(golden))

        scenarios, skipped = load_triage_scenarios(path)
        assert len(scenarios) == 1
        assert skipped == 1
        assert scenarios[0]["scenario"] == "valid_one"

    def test_validates_required_fields(self, tmp_path):
        golden = [{"category": "bad", "error": "missing scenario and expected_class"}]
        path = tmp_path / "bad_golden.json"
        path.write_text(json.dumps(golden))

        scenarios, skipped = load_triage_scenarios(path)
        assert len(scenarios) == 0
        assert skipped == 1

    def test_categories_are_correct(self):
        scenarios, _ = load_triage_scenarios()
        categories = {s["category"] for s in scenarios}
        assert categories == {"locator_drift", "app_defect", "unknown"}

    def test_category_counts(self):
        scenarios, _ = load_triage_scenarios()
        counts = {}
        for s in scenarios:
            counts[s["category"]] = counts.get(s["category"], 0) + 1
        assert counts["locator_drift"] == 10
        assert counts["app_defect"] == 12
        assert counts["unknown"] == 8


# ---------------------------------------------------------------------------
# Synthetic state tests
# ---------------------------------------------------------------------------

class TestBuildSyntheticState:

    def test_builds_state_with_error(self):
        scenario = {
            "scenario": "test_error",
            "error": "TimeoutError: something failed",
            "expected_class": "locator_drift",
        }
        state = build_synthetic_state(scenario)
        assert state.error == "TimeoutError: something failed"
        assert state.goal == "eval-test_error"

    def test_builds_dom_snippet_renamed(self):
        scenario = {
            "scenario": "test_dom",
            "error": "TimeoutError",
            "dom_has_element": True,
            "dom_element_renamed": "Place Order",
            "expected_class": "locator_drift",
        }
        state = build_synthetic_state(scenario)
        assert state.dom_snapshot is not None
        assert "Place Order" in state.dom_snapshot

    def test_builds_dom_snippet_no_element(self):
        scenario = {
            "scenario": "test_no_dom",
            "error": "TimeoutError",
            "dom_has_element": False,
            "expected_class": "unknown",
        }
        state = build_synthetic_state(scenario)
        assert state.dom_snapshot is not None
        assert "not found" in state.dom_snapshot

    def test_no_dom_when_null(self):
        scenario = {
            "scenario": "test_null_dom",
            "error": "AssertionError",
            "dom_has_element": None,
            "expected_class": "app_defect",
        }
        state = build_synthetic_state(scenario)
        assert state.dom_snapshot is None

    def test_run_results_populated(self):
        scenario = {
            "scenario": "test_rr",
            "error": "Error",
            "expected_class": "unknown",
        }
        state = build_synthetic_state(scenario)
        assert state.run_results is not None
        assert state.run_results.passed is False


# ---------------------------------------------------------------------------
# Scorecard tests
# ---------------------------------------------------------------------------

class TestBuildScorecard:

    def test_scorecard_has_required_fields(self):
        eval_result = {
            "triage_accuracy": {"score": 0.85, "correct": 17, "total": 20, "misses": []},
            "scenarios": [{"scenario": f"s{i}", "category": "locator_drift"} for i in range(20)],
            "skipped_expired": 0,
        }
        sc = build_scorecard(
            eval_result, run_id="test-001", agent="triage",
            baseline_mode=False, thresholds={"triage_accuracy": 0.75},
        )
        assert "eval_run_id" in sc
        assert "agent" in sc
        assert "timestamp" in sc
        assert "triage_accuracy" in sc
        assert "by_category" in sc
        assert "passed" in sc
        assert "regression_vs_previous" in sc

    def test_baseline_mode_no_pass_fail(self):
        eval_result = {
            "triage_accuracy": {"score": 0.50, "correct": 5, "total": 10, "misses": []},
            "scenarios": [],
            "skipped_expired": 0,
        }
        sc = build_scorecard(
            eval_result, run_id="test-002", agent="triage",
            baseline_mode=True, thresholds={"triage_accuracy": 0.75},
        )
        assert sc["passed"] is None

    def test_pass_when_above_threshold(self):
        eval_result = {
            "triage_accuracy": {"score": 0.90, "correct": 9, "total": 10, "misses": []},
            "scenarios": [],
            "skipped_expired": 0,
        }
        sc = build_scorecard(
            eval_result, run_id="test-003", agent="triage",
            baseline_mode=False, thresholds={"triage_accuracy": 0.75},
        )
        assert sc["passed"] is True

    def test_fail_when_below_threshold(self):
        eval_result = {
            "triage_accuracy": {"score": 0.60, "correct": 6, "total": 10, "misses": []},
            "scenarios": [],
            "skipped_expired": 0,
        }
        sc = build_scorecard(
            eval_result, run_id="test-004", agent="triage",
            baseline_mode=False, thresholds={"triage_accuracy": 0.75},
        )
        assert sc["passed"] is False

    def test_category_breakdown(self):
        scenarios = [
            {"scenario": "s1", "category": "locator_drift"},
            {"scenario": "s2", "category": "locator_drift"},
            {"scenario": "s3", "category": "app_defect"},
        ]
        misses = [{"scenario": "s2"}]

        breakdown = _compute_category_breakdown(scenarios, misses)
        assert breakdown["locator_drift"]["correct"] == 1
        assert breakdown["locator_drift"]["total"] == 2
        assert breakdown["app_defect"]["correct"] == 1


class TestSaveLoadScorecard:

    def test_save_and_load(self, tmp_path):
        sc = {
            "eval_run_id": "test-save",
            "agent": "triage",
            "timestamp": "2026-08-30T00:00:00Z",
            "triage_accuracy": {"score": 0.85, "correct": 17, "total": 20, "misses": []},
        }
        path = save_scorecard(sc, tmp_path)
        assert path.exists()
        assert "triage-" in path.name

        loaded = load_latest_scorecard("triage", tmp_path)
        assert loaded is not None
        assert loaded["eval_run_id"] == "test-save"

    def test_load_returns_none_when_empty(self, tmp_path):
        result = load_latest_scorecard("triage", tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# Regression detection tests
# ---------------------------------------------------------------------------

class TestRegressionDetection:

    def test_first_run_status(self):
        current = {"triage_accuracy": {"score": 0.85, "misses": []}}
        result = detect_regression(current, None)
        assert result["status"] == "first_run"

    def test_stable_within_threshold(self):
        current = {"triage_accuracy": {"score": 0.83, "misses": []}}
        previous = {"triage_accuracy": {"score": 0.85, "misses": []}}
        result = detect_regression(current, previous)
        assert result["status"] == "stable"
        assert result["severity"] is None

    def test_minor_regression(self):
        current = {"triage_accuracy": {"score": 0.78, "misses": []}}
        previous = {"triage_accuracy": {"score": 0.85, "misses": []}}
        result = detect_regression(current, previous)
        assert result["status"] == "regression"
        assert result["severity"] == "minor"

    def test_major_regression(self):
        current = {"triage_accuracy": {"score": 0.70, "misses": []}}
        previous = {"triage_accuracy": {"score": 0.85, "misses": []}}
        result = detect_regression(current, previous)
        assert result["status"] == "regression"
        assert result["severity"] == "major"

    def test_improvement_detected(self):
        current = {"triage_accuracy": {"score": 0.93, "misses": []}}
        previous = {"triage_accuracy": {"score": 0.85, "misses": []}}
        result = detect_regression(current, previous)
        assert result["status"] == "improvement"

    def test_new_failures_identified(self):
        current = {"triage_accuracy": {"score": 0.80, "misses": [
            {"scenario": "new_miss"},
            {"scenario": "old_miss"},
        ]}}
        previous = {"triage_accuracy": {"score": 0.85, "misses": [
            {"scenario": "old_miss"},
        ]}}
        result = detect_regression(current, previous)
        assert "new_miss" in result["new_failures"]
        assert "old_miss" not in result["new_failures"]

    def test_recovered_scenarios(self):
        current = {"triage_accuracy": {"score": 0.90, "misses": []}}
        previous = {"triage_accuracy": {"score": 0.85, "misses": [
            {"scenario": "was_broken"},
        ]}}
        result = detect_regression(current, previous)
        assert "was_broken" in result["recovered"]


# ---------------------------------------------------------------------------
# Eval runner integration tests (mocked triage)
# ---------------------------------------------------------------------------

class TestEvalRunnerIntegration:

    @pytest.mark.asyncio
    async def test_run_triage_eval_all_correct(self, tmp_path):
        """Mock triage to return correct answers for all scenarios."""
        scenarios = [
            {"scenario": "s1", "category": "locator_drift", "error": "Timeout",
             "expected_class": "locator_drift", "expected_confidence_min": 0.75},
            {"scenario": "s2", "category": "app_defect", "error": "Assertion",
             "expected_class": "app_defect", "expected_confidence_min": 0.80},
        ]

        async def mock_triage(state):
            if "s1" in state.goal:
                return {"failure_class": "locator_drift", "confidence": 0.85}
            return {"failure_class": "app_defect", "confidence": 0.90}

        with patch("qa_agent.eval.eval_runner.triage", side_effect=mock_triage):
            from qa_agent.eval.eval_runner import run_triage_eval
            scorecard = await run_triage_eval(
                scenarios=scenarios,
                baseline_mode=False,
                threshold=0.75,
                reports_dir=tmp_path,
            )

        assert scorecard["triage_accuracy"]["score"] == 1.0
        assert scorecard["passed"] is True

    @pytest.mark.asyncio
    async def test_run_triage_eval_partial_correct(self, tmp_path):
        """Mock triage to miss one scenario."""
        scenarios = [
            {"scenario": "s1", "category": "locator_drift", "error": "Timeout",
             "expected_class": "locator_drift", "expected_confidence_min": 0.75},
            {"scenario": "s2", "category": "app_defect", "error": "Assertion",
             "expected_class": "app_defect", "expected_confidence_min": 0.80},
            {"scenario": "s3", "category": "unknown", "error": "Generic",
             "expected_class": "unknown", "expected_confidence_min": 0.0},
        ]

        async def mock_triage(state):
            if "s1" in state.goal:
                return {"failure_class": "locator_drift", "confidence": 0.85}
            if "s2" in state.goal:
                return {"failure_class": "unknown", "confidence": 0.50}  # WRONG
            return {"failure_class": "unknown", "confidence": 0.10}

        from qa_agent.eval import eval_runner
        with patch.object(eval_runner, "triage", side_effect=mock_triage):
            scorecard = await eval_runner.run_triage_eval(
                scenarios=scenarios,
                baseline_mode=False,
                threshold=0.50,
                reports_dir=tmp_path,
            )

        assert scorecard["triage_accuracy"]["correct"] == 2
        assert scorecard["triage_accuracy"]["total"] == 3
        assert len(scorecard["triage_accuracy"]["misses"]) == 1

    @pytest.mark.asyncio
    async def test_run_triage_eval_baseline_mode(self, tmp_path):
        """Baseline mode should set passed=None."""
        scenarios = [
            {"scenario": "s1", "category": "locator_drift", "error": "Timeout",
             "expected_class": "locator_drift", "expected_confidence_min": 0.75},
        ]

        async def mock_triage(state):
            return {"failure_class": "locator_drift", "confidence": 0.85}

        from qa_agent.eval import eval_runner
        with patch.object(eval_runner, "triage", side_effect=mock_triage):
            scorecard = await eval_runner.run_triage_eval(
                scenarios=scenarios,
                baseline_mode=True,
                reports_dir=tmp_path,
            )

        assert scorecard["passed"] is None
        assert scorecard["baseline_mode"] is True
