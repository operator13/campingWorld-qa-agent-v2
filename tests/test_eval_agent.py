"""Tests for the Eval Agent — scorecard, regression, recommendations, eval runner."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from qa_agent.eval.eval_runner import (
    build_synthetic_state,
    load_healer_scenarios,
    load_planner_scenarios,
    load_triage_scenarios,
)
from qa_agent.eval.run_eval import (
    score_assertion_integrity,
    score_diff_minimality,
    score_import_correctness,
    score_plan_quality,
)
from qa_agent.schemas.models import TestCase
from qa_agent.eval.recommendations import (
    generate_recommendations,
    format_report_markdown,
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
        assert path.parent.name == "triage"

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


# ---------------------------------------------------------------------------
# Recommendations tests
# ---------------------------------------------------------------------------

class TestRecommendations:

    def test_confidence_underrun_detected(self):
        scorecard = {
            "triage_accuracy": {
                "score": 0.0,
                "correct": 0,
                "total": 5,
                "misses": [
                    {"scenario": f"s{i}", "expected_class": "locator_drift",
                     "got_class": "locator_drift", "expected_conf_min": 0.75, "got_conf": 0.65}
                    for i in range(5)
                ],
            },
            "by_category": {"locator_drift": {"score": 0.0, "correct": 0, "total": 5}},
            "thresholds": {"triage_accuracy": 0.75},
        }
        recs = generate_recommendations(scorecard)
        confidence_recs = [r for r in recs if "confidence" in r["finding"].lower() or "rubric" in r["finding"].lower()]
        assert len(confidence_recs) >= 1
        assert confidence_recs[0]["priority"] == "high"

    def test_misclassification_detected(self):
        scorecard = {
            "triage_accuracy": {
                "score": 0.5,
                "correct": 1,
                "total": 2,
                "misses": [
                    {"scenario": "bad_one", "expected_class": "unknown",
                     "got_class": "app_defect", "expected_conf_min": 0.0, "got_conf": 0.05}
                ],
            },
            "by_category": {"unknown": {"score": 0.5, "correct": 1, "total": 2}},
            "thresholds": {"triage_accuracy": 0.75},
        }
        recs = generate_recommendations(scorecard)
        misclass_recs = [r for r in recs if "expected" in r["finding"] and "returned" in r["finding"]]
        assert len(misclass_recs) >= 1

    def test_below_threshold_recommendation(self):
        scorecard = {
            "triage_accuracy": {"score": 0.50, "correct": 5, "total": 10, "misses": [{}] * 5},
            "by_category": {},
            "thresholds": {"triage_accuracy": 0.75},
        }
        recs = generate_recommendations(scorecard)
        threshold_recs = [r for r in recs if "below threshold" in r["finding"]]
        assert len(threshold_recs) == 1

    def test_major_regression_recommendation(self):
        scorecard = {
            "triage_accuracy": {"score": 0.60, "correct": 6, "total": 10, "misses": []},
            "by_category": {},
            "thresholds": {"triage_accuracy": 0.75},
            "regression_vs_previous": {"severity": "major", "delta": -0.15,
                                        "previous_score": 0.75, "current_score": 0.60},
        }
        recs = generate_recommendations(scorecard)
        reg_recs = [r for r in recs if r["category"] == "regression" and r["priority"] == "high"]
        assert len(reg_recs) >= 1

    def test_all_passing_recommendation(self):
        scorecard = {
            "triage_accuracy": {"score": 0.90, "correct": 9, "total": 10, "misses": []},
            "by_category": {},
            "thresholds": {"triage_accuracy": 0.75},
        }
        recs = generate_recommendations(scorecard)
        assert any("pass" in r["finding"].lower() for r in recs)

    def test_recommendations_sorted_by_priority(self):
        scorecard = {
            "triage_accuracy": {"score": 0.50, "correct": 5, "total": 10, "misses": [
                {"scenario": "s1", "expected_class": "unknown", "got_class": "app_defect",
                 "expected_conf_min": 0.0, "got_conf": 0.05},
            ]},
            "by_category": {},
            "thresholds": {"triage_accuracy": 0.75},
            "regression_vs_previous": {"recovered": ["old_one"], "new_failures": [],
                                        "severity": None, "status": "stable"},
        }
        recs = generate_recommendations(scorecard)
        priorities = [r["priority"] for r in recs]
        assert priorities == sorted(priorities, key=lambda p: {"high": 0, "medium": 1, "low": 2}[p])


class TestFormatReportMarkdown:

    def test_report_contains_sections(self):
        scorecard = {
            "agent": "triage",
            "eval_run_id": "test-report",
            "timestamp": "2026-08-30T00:00:00Z",
            "baseline_mode": False,
            "passed": False,
            "triage_accuracy": {"score": 0.80, "correct": 8, "total": 10, "misses": [
                {"scenario": "s1", "expected_class": "locator_drift",
                 "got_class": "locator_drift", "expected_conf_min": 0.75, "got_conf": 0.65},
            ]},
            "by_category": {"locator_drift": {"score": 0.80, "correct": 8, "total": 10}},
            "thresholds": {"triage_accuracy": 0.75},
            "regression_vs_previous": {"status": "stable", "delta": 0.0},
            "recommendations": [
                {"priority": "high", "category": "locator_drift",
                 "finding": "Test finding", "action": "Test action"},
            ],
        }
        md = format_report_markdown(scorecard)
        assert "# Eval Report" in md
        assert "## Accuracy" in md
        assert "## By Category" in md
        assert "## Recommendations" in md
        assert "[HIGH]" in md
        assert "Test finding" in md
        assert "## Misses Detail" in md

    def test_report_no_recommendations_when_empty(self):
        scorecard = {
            "agent": "triage",
            "eval_run_id": "test",
            "timestamp": "2026-08-30",
            "baseline_mode": False,
            "passed": True,
            "triage_accuracy": {"score": 1.0, "correct": 10, "total": 10, "misses": []},
            "by_category": {},
            "thresholds": {"triage_accuracy": 0.75},
            "recommendations": [],
        }
        md = format_report_markdown(scorecard)
        assert "## Recommendations" not in md


# ---------------------------------------------------------------------------
# Planner golden data tests
# ---------------------------------------------------------------------------

class TestPlannerScenarios:

    def test_loads_8_scenarios(self):
        scenarios, skipped = load_planner_scenarios()
        assert len(scenarios) == 8
        assert skipped == 0

    def test_categories_present(self):
        scenarios, _ = load_planner_scenarios()
        scenario_names = {s["scenario"] for s in scenarios}
        assert "checkout_flow" in scenario_names
        assert "search_and_filter" in scenario_names
        assert "auth_login" in scenario_names
        assert "product_browsing" in scenario_names
        assert "cart_management" in scenario_names
        assert "payment_error_handling" in scenario_names
        assert "coupon_checkout_multistep" in scenario_names
        assert "email_validation_and_access_control" in scenario_names

    def test_all_scenarios_have_required_fields(self):
        scenarios, _ = load_planner_scenarios()
        required = {"scenario", "goal", "acceptance_criteria", "expected_ac_coverage_min"}
        for s in scenarios:
            missing = required - s.keys()
            assert not missing, f"Scenario {s.get('scenario')} missing fields: {missing}"

    def test_acceptance_criteria_are_nonempty(self):
        scenarios, _ = load_planner_scenarios()
        for s in scenarios:
            assert len(s["acceptance_criteria"]) >= 2, (
                f"Scenario {s['scenario']} needs at least 2 ACs"
            )

    def test_coverage_thresholds_are_reasonable(self):
        scenarios, _ = load_planner_scenarios()
        for s in scenarios:
            threshold = s["expected_ac_coverage_min"]
            assert 0.5 <= threshold <= 1.0, (
                f"Scenario {s['scenario']} has suspicious threshold: {threshold}"
            )

    def test_skips_expired_scenarios(self, tmp_path):
        golden = [
            {
                "scenario": "expired_planner",
                "goal": "test goal",
                "acceptance_criteria": ["AC 1"],
                "expected_ac_coverage_min": 0.80,
                "valid_until": "2020-01-01",
            },
            {
                "scenario": "valid_planner",
                "goal": "test goal",
                "acceptance_criteria": ["AC 1"],
                "expected_ac_coverage_min": 0.80,
                "valid_until": "2099-01-01",
            },
        ]
        path = tmp_path / "planner_golden.json"
        path.write_text(json.dumps(golden))

        scenarios, skipped = load_planner_scenarios(path)
        assert len(scenarios) == 1
        assert skipped == 1
        assert scenarios[0]["scenario"] == "valid_planner"

    def test_skips_invalid_scenarios(self, tmp_path):
        golden = [{"goal": "missing scenario and coverage fields"}]
        path = tmp_path / "bad_planner.json"
        path.write_text(json.dumps(golden))

        scenarios, skipped = load_planner_scenarios(path)
        assert len(scenarios) == 0
        assert skipped == 1


# ---------------------------------------------------------------------------
# Planner eval integration tests (mocked planner)
# ---------------------------------------------------------------------------

def _make_mock_planner_result(n_cases: int = 3) -> dict:
    """Build a planner result dict with n_cases TestCase objects."""
    cases = [
        TestCase(
            id=f"tc-{i}",
            title=f"Test case {i}",
            feature="checkout",
            route="/checkout",
            steps=[f"Navigate to /checkout", f"Perform action {i}"],
            expected=[f"Expected outcome {i}"],
            tags=["@smoke"],
        )
        for i in range(1, n_cases + 1)
    ]
    return {"plan": cases}


class TestPlannerEvalIntegration:

    @pytest.mark.asyncio
    async def test_run_planner_eval_all_pass(self, tmp_path):
        """Mock planner returns test cases covering all ACs — all scenarios pass."""
        scenarios = [
            {
                "scenario": "checkout_flow",
                "goal": "Test the checkout flow",
                "acceptance_criteria": [
                    "User can add items to the cart",
                    "User sees order confirmation",
                ],
                "expected_test_count_min": 1,
                "expected_ac_coverage_min": 0.50,
            },
        ]

        async def mock_planner(state):
            return {
                "plan": [
                    TestCase(
                        id="tc-1",
                        title="User can add items to the cart and see order confirmation",
                        feature="checkout",
                        route="/checkout",
                        steps=["Navigate to /checkout", "Add item to cart", "Submit order"],
                        expected=["Order confirmation is displayed after adding items to cart"],
                        tags=["@smoke"],
                    )
                ]
            }

        with patch("qa_agent.eval.eval_runner.planner", side_effect=mock_planner):
            from qa_agent.eval.eval_runner import run_planner_eval
            scorecard = await run_planner_eval(
                scenarios=scenarios,
                baseline_mode=False,
                threshold=0.50,
                reports_dir=tmp_path,
            )

        assert scorecard["agent"] == "planner"
        assert "planner_accuracy" in scorecard
        assert scorecard["planner_accuracy"]["total"] == 1

    @pytest.mark.asyncio
    async def test_run_planner_eval_miss_recorded(self, tmp_path):
        """Mock planner returns empty plan — scenario is flagged as a miss."""
        scenarios = [
            {
                "scenario": "auth_login",
                "goal": "Test user authentication",
                "acceptance_criteria": [
                    "User can log in with valid email and password",
                    "Invalid credentials show an error message",
                ],
                "expected_test_count_min": 2,
                "expected_ac_coverage_min": 0.80,
            },
        ]

        async def mock_planner(state):
            return {"plan": []}

        with patch("qa_agent.eval.eval_runner.planner", side_effect=mock_planner):
            from qa_agent.eval.eval_runner import run_planner_eval
            scorecard = await run_planner_eval(
                scenarios=scenarios,
                baseline_mode=False,
                threshold=0.80,
                reports_dir=tmp_path,
            )

        pa = scorecard["planner_accuracy"]
        assert pa["total"] == 1
        assert len(pa["misses"]) == 1
        assert pa["misses"][0]["scenario"] == "auth_login"

    @pytest.mark.asyncio
    async def test_run_planner_eval_baseline_mode(self, tmp_path):
        """Baseline mode sets passed=None regardless of score."""
        scenarios = [
            {
                "scenario": "cart_management",
                "goal": "Test cart management",
                "acceptance_criteria": ["User can add a product to the cart"],
                "expected_test_count_min": 1,
                "expected_ac_coverage_min": 0.80,
            },
        ]

        async def mock_planner(state):
            return {
                "plan": [
                    TestCase(
                        id="tc-1",
                        title="User can add a product to the cart",
                        feature="cart",
                        route="/cart",
                        steps=["Navigate to product page", "Click Add to Cart"],
                        expected=["Product appears in cart"],
                        tags=["@smoke"],
                    )
                ]
            }

        with patch("qa_agent.eval.eval_runner.planner", side_effect=mock_planner):
            from qa_agent.eval.eval_runner import run_planner_eval
            scorecard = await run_planner_eval(
                scenarios=scenarios,
                baseline_mode=True,
                reports_dir=tmp_path,
            )

        assert scorecard["passed"] is None
        assert scorecard["baseline_mode"] is True
        assert scorecard["agent"] == "planner"


# ---------------------------------------------------------------------------
# Healer golden data tests
# ---------------------------------------------------------------------------

class TestHealerScenarios:

    def test_loads_10_scenarios(self):
        scenarios, skipped = load_healer_scenarios()
        assert len(scenarios) == 10
        assert skipped == 0

    def test_all_scenarios_have_required_fields(self):
        scenarios, _ = load_healer_scenarios()
        required = {"scenario", "error", "route", "old_source", "dom_snippet"}
        for s in scenarios:
            missing = required - s.keys()
            assert not missing, f"Scenario {s.get('scenario')} missing fields: {missing}"

    def test_all_scenarios_have_expected_fix(self):
        scenarios, _ = load_healer_scenarios()
        for s in scenarios:
            assert "expected_fix_contains" in s, (
                f"Scenario {s['scenario']} missing expected_fix_contains"
            )
            assert s["expected_fix_contains"], (
                f"Scenario {s['scenario']} has empty expected_fix_contains"
            )

    def test_skips_expired_scenarios(self, tmp_path):
        golden = [
            {
                "scenario": "expired_healer",
                "error": "TimeoutError",
                "route": "/checkout",
                "old_source": "page.getByRole('button', { name: 'Old' })",
                "dom_snippet": "<button>New</button>",
                "expected_fix_contains": "New",
                "valid_until": "2020-01-01",
            },
            {
                "scenario": "valid_healer",
                "error": "TimeoutError",
                "route": "/cart",
                "old_source": "page.getByRole('button', { name: 'Old' })",
                "dom_snippet": "<button>Updated</button>",
                "expected_fix_contains": "Updated",
                "valid_until": "2099-01-01",
            },
        ]
        path = tmp_path / "healer_golden.json"
        path.write_text(json.dumps(golden))

        scenarios, skipped = load_healer_scenarios(path)
        assert len(scenarios) == 1
        assert skipped == 1
        assert scenarios[0]["scenario"] == "valid_healer"

    def test_skips_invalid_scenarios(self, tmp_path):
        golden = [{"scenario": "bad_healer", "error": "timeout"}]  # missing required fields
        path = tmp_path / "bad_healer.json"
        path.write_text(json.dumps(golden))

        scenarios, skipped = load_healer_scenarios(path)
        assert len(scenarios) == 0
        assert skipped == 1


# ---------------------------------------------------------------------------
# Assertion integrity scorer tests
# ---------------------------------------------------------------------------

class TestAssertionIntegrity:

    def test_scores_1_when_no_assertion_changes(self):
        old = {
            "/checkout": (
                "this.submitBtn = page.getByRole('button', { name: 'Submit' });\n"
                "await expect(page).toHaveURL('/checkout');\n"
            )
        }
        new = {
            "/checkout": (
                "this.submitBtn = page.getByRole('button', { name: 'Place Order' });\n"
                "await expect(page).toHaveURL('/checkout');\n"
            )
        }
        result = score_assertion_integrity(old, new)
        assert result["score"] == 1.0
        assert result["violations"] == 0
        assert result["clean"] == 1

    def test_scores_0_when_assertion_modified(self):
        old = {
            "/checkout": (
                "this.submitBtn = page.getByRole('button', { name: 'Submit' });\n"
                "await expect(page).toHaveURL('/checkout');\n"
            )
        }
        new = {
            "/checkout": (
                "this.submitBtn = page.getByRole('button', { name: 'Place Order' });\n"
                "await expect(page).toHaveURL('/confirmation');\n"  # assertion changed
            )
        }
        result = score_assertion_integrity(old, new)
        assert result["score"] == 0.0
        assert result["violations"] == 1
        assert "/checkout" in result["violation_routes"]

    def test_empty_sources_returns_perfect_score(self):
        result = score_assertion_integrity({}, {})
        assert result["score"] == 1.0
        assert result["total"] == 0

    def test_multiple_routes_partial_violations(self):
        old = {
            "/checkout": "await expect(page).toHaveURL('/checkout');\n",
            "/cart": "await expect(cart).toBeVisible();\n",
        }
        new = {
            "/checkout": "await expect(page).toHaveURL('/checkout');\n",  # unchanged — clean
            "/cart": "await expect(cart).toBeHidden();\n",  # assertion changed — violation
        }
        result = score_assertion_integrity(old, new)
        assert result["violations"] == 1
        assert result["clean"] == 1
        assert result["score"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Diff minimality scorer tests
# ---------------------------------------------------------------------------

class TestDiffMinimality:

    def test_scores_1_when_only_locator_changed(self):
        old = {"/checkout": "this.btn = page.getByRole('button', { name: 'Submit' });\n"}
        new = {"/checkout": "this.btn = page.getByRole('button', { name: 'Place Order' });\n"}
        result = score_diff_minimality(old, new)
        assert result["score"] == 1.0
        assert result["non_locator_changes"] == 0

    def test_scores_less_than_1_when_non_locator_changed(self):
        old = {
            "/checkout": (
                "this.btn = page.getByRole('button', { name: 'Submit' });\n"
                "readonly title = 'Checkout';\n"
            )
        }
        new = {
            "/checkout": (
                "this.btn = page.getByRole('button', { name: 'Place Order' });\n"
                "readonly title = 'Order';\n"  # non-locator line changed
            )
        }
        result = score_diff_minimality(old, new)
        assert result["score"] < 1.0
        assert result["non_locator_changes"] > 0

    def test_no_changes_returns_perfect_score(self):
        source = "this.btn = page.getByRole('button', { name: 'Submit' });\n"
        old = {"/checkout": source}
        new = {"/checkout": source}
        result = score_diff_minimality(old, new)
        assert result["score"] == 1.0
        assert result["total_changes"] == 0

    def test_testid_change_counts_as_locator(self):
        old = {"/login": "this.input = page.getByTestId('old-email');\n"}
        new = {"/login": "this.input = page.getByTestId('new-email');\n"}
        result = score_diff_minimality(old, new)
        assert result["score"] == 1.0

    def test_waitfor_change_counts_as_locator(self):
        old = {"/cart": "await this.heading.waitFor({ timeout: 5000 });\n"}
        new = {"/cart": "await this.heading.waitFor({ timeout: 10000 });\n"}
        result = score_diff_minimality(old, new)
        assert result["score"] == 1.0


# ---------------------------------------------------------------------------
# Healer eval integration tests (mocked healer)
# ---------------------------------------------------------------------------

_MOCK_OLD_SOURCE = (
    "import { type Page, type Locator } from '@playwright/test';\n\n"
    "export class CheckoutPage {\n"
    "  readonly submitBtn: Locator;\n"
    "  constructor(page: Page) {\n"
    "    this.submitBtn = page.getByRole('button', { name: 'Submit' });\n"
    "  }\n"
    "  async navigate() { await this.page.goto('/checkout'); }\n"
    "  async submit() { await this.submitBtn.click(); }\n"
    "}"
)

_MOCK_NEW_SOURCE = (
    "import { type Page, type Locator } from '@playwright/test';\n\n"
    "export class CheckoutPage {\n"
    "  readonly submitBtn: Locator;\n"
    "  constructor(page: Page) {\n"
    "    this.submitBtn = page.getByRole('button', { name: 'Place Order' });\n"
    "  }\n"
    "  async navigate() { await this.page.goto('/checkout'); }\n"
    "  async submit() { await this.submitBtn.click(); }\n"
    "}"
)


class TestHealerEvalIntegration:

    @pytest.mark.asyncio
    async def test_run_healer_eval_records_fix_present(self, tmp_path):
        """Mock healer returns a fixed source containing expected_fix_contains text."""
        scenarios = [
            {
                "scenario": "button_submit_renamed",
                "error": "TimeoutError: locator.click: Timeout 30000ms exceeded.\n  - waiting for getByRole('button', { name: 'Submit' })",
                "route": "/checkout",
                "old_source": _MOCK_OLD_SOURCE,
                "dom_snippet": "<button>Place Order</button>",
                "expected_fix_contains": "Place Order",
                "valid_until": "2099-06-01",
            }
        ]

        async def mock_healer(state):
            return {
                "page_objects": {"/checkout": _MOCK_NEW_SOURCE},
                "attempts": 1,
            }

        with patch("qa_agent.eval.eval_runner.healer", side_effect=mock_healer):
            from qa_agent.eval.eval_runner import run_healer_eval
            scorecard = await run_healer_eval(
                scenarios=scenarios,
                baseline_mode=False,
                threshold=0.75,
                reports_dir=tmp_path,
            )

        assert scorecard["agent"] == "healer"
        assert "assertion_integrity" in scorecard
        assert "diff_minimality" in scorecard
        assert "fix_rate" in scorecard
        assert scorecard["fix_rate"]["correct"] == 1
        assert scorecard["assertion_integrity"]["violations"] == 0

    @pytest.mark.asyncio
    async def test_run_healer_eval_baseline_mode(self, tmp_path):
        """Baseline mode sets passed=None regardless of score."""
        scenarios = [
            {
                "scenario": "testid_changed",
                "error": "TimeoutError: locator.fill: Timeout 30000ms exceeded.\n  - waiting for getByTestId('checkout-email')",
                "route": "/checkout",
                "old_source": "this.emailInput = page.getByTestId('checkout-email');\n",
                "dom_snippet": "<input data-testid=\"email-field\" type=\"email\" />",
                "expected_fix_contains": "email-field",
                "valid_until": "2099-06-01",
            }
        ]

        async def mock_healer(state):
            return {
                "page_objects": {"/checkout": "this.emailInput = page.getByTestId('email-field');\n"},
                "attempts": 1,
            }

        with patch("qa_agent.eval.eval_runner.healer", side_effect=mock_healer):
            from qa_agent.eval.eval_runner import run_healer_eval
            scorecard = await run_healer_eval(
                scenarios=scenarios,
                baseline_mode=True,
                reports_dir=tmp_path,
            )

        assert scorecard["passed"] is None
        assert scorecard["baseline_mode"] is True
        assert scorecard["agent"] == "healer"


# ---------------------------------------------------------------------------
# Executor parsing unit tests
# ---------------------------------------------------------------------------

from qa_agent.nodes.executor import _parse_failed_cases


class TestExecutorParsing:

    def test_parse_failed_cases_with_playwright_json(self):
        """Parse actual Playwright JSON reporter output format."""
        pw_json = {
            "suites": [
                {
                    "specs": [
                        {
                            "title": "fills checkout form",
                            "tests": [{"status": "unexpected"}],
                        },
                        {
                            "title": "submits order",
                            "tests": [{"status": "expected"}],
                        },
                    ]
                }
            ]
        }
        import json
        output = json.dumps(pw_json)
        failed = _parse_failed_cases(output)
        assert "fills checkout form" in failed
        assert "submits order" not in failed

    def test_parse_failed_cases_with_empty_output(self):
        """Empty string returns empty list without error."""
        failed = _parse_failed_cases("")
        assert failed == []

    def test_parse_failed_cases_with_malformed_json(self):
        """Malformed JSON falls back to line-based FAIL detection."""
        output = "FAIL  tests/checkout.spec.ts\n  FAIL  some other line with FAIL\n  passed test"
        failed = _parse_failed_cases(output)
        assert len(failed) >= 1
        assert any("FAIL" in f for f in failed)

    def test_parse_failed_cases_all_passing(self):
        """All passing specs produce empty failed list."""
        import json
        pw_json = {
            "suites": [
                {
                    "specs": [
                        {"title": "test passes", "tests": [{"status": "expected"}]},
                    ]
                }
            ]
        }
        failed = _parse_failed_cases(json.dumps(pw_json))
        assert failed == []

    def test_parse_failed_cases_multiple_suites(self):
        """Failed cases are collected across multiple suites."""
        import json
        pw_json = {
            "suites": [
                {
                    "specs": [
                        {"title": "checkout fails", "tests": [{"status": "unexpected"}]},
                    ]
                },
                {
                    "specs": [
                        {"title": "login fails", "tests": [{"status": "unexpected"}]},
                        {"title": "search passes", "tests": [{"status": "expected"}]},
                    ]
                },
            ]
        }
        failed = _parse_failed_cases(json.dumps(pw_json))
        assert "checkout fails" in failed
        assert "login fails" in failed
        assert "search passes" not in failed
        assert len(failed) == 2


# ---------------------------------------------------------------------------
# Generator scorer unit tests
# ---------------------------------------------------------------------------

from qa_agent.eval.run_eval import score_fix_correctness, score_old_locator_removed, score_pom_validity, score_test_validity


class TestPomValidity:

    VALID_POM = (
        "import { type Page, type Locator } from '@playwright/test';\n"
        "export class CheckoutPage {\n"
        "  private emailInput: Locator;\n"
        "  constructor(page: Page) {\n"
        "    this.emailInput = page.getByTestId('checkout-email');\n"
        "  }\n"
        "  async navigate() { await this.page.goto('/checkout'); }\n"
        "}\n"
    )

    INVALID_POM = (
        "// just a comment\n"
        "const x = 1;\n"
    )

    def test_valid_pom_scores_1_0(self):
        result = score_pom_validity({"/checkout": self.VALID_POM})
        assert result["score"] == 1.0
        assert result["valid"] == 1
        assert result["total"] == 1
        assert result["invalid"] == []

    def test_invalid_pom_scores_0_0(self):
        result = score_pom_validity({"/checkout": self.INVALID_POM})
        assert result["score"] == 0.0
        assert result["valid"] == 0
        assert result["total"] == 1
        assert len(result["invalid"]) == 1

    def test_empty_page_objects_scores_1_0(self):
        result = score_pom_validity({})
        assert result["score"] == 1.0
        assert result["total"] == 0

    def test_mixed_poms_partial_score(self):
        result = score_pom_validity({
            "/checkout": self.VALID_POM,
            "/login": self.INVALID_POM,
        })
        assert result["score"] == 0.5
        assert result["valid"] == 1
        assert result["total"] == 2

    def test_invalid_pom_reports_failed_checks(self):
        result = score_pom_validity({"/checkout": self.INVALID_POM})
        invalid = result["invalid"][0]
        assert "failed_checks" in invalid
        assert len(invalid["failed_checks"]) > 0


class TestTestValidity:

    VALID_SPEC = (
        "import { test, expect } from '@playwright/test';\n"
        "test.describe('Checkout', () => {\n"
        "  test.beforeEach(async ({ page }) => { await page.goto('/checkout'); });\n"
        "  test('fills form', async ({ page }) => {\n"
        "    await expect(page.getByRole('textbox')).toBeVisible();\n"
        "  });\n"
        "});\n"
    )

    INVALID_SPEC = (
        "// empty spec file\n"
        "const setup = () => {};\n"
    )

    def test_valid_spec_scores_1_0(self):
        result = score_test_validity({"checkout.spec.ts": self.VALID_SPEC})
        assert result["score"] == 1.0
        assert result["valid"] == 1
        assert result["total"] == 1
        assert result["invalid"] == []

    def test_invalid_spec_scores_0_0(self):
        result = score_test_validity({"checkout.spec.ts": self.INVALID_SPEC})
        assert result["score"] == 0.0
        assert result["valid"] == 0
        assert result["total"] == 1
        assert len(result["invalid"]) == 1

    def test_empty_test_code_scores_1_0(self):
        result = score_test_validity({})
        assert result["score"] == 1.0
        assert result["total"] == 0

    def test_mixed_specs_partial_score(self):
        result = score_test_validity({
            "checkout.spec.ts": self.VALID_SPEC,
            "empty.spec.ts": self.INVALID_SPEC,
        })
        assert result["score"] == 0.5
        assert result["valid"] == 1
        assert result["total"] == 2

    def test_invalid_spec_reports_failed_checks(self):
        result = score_test_validity({"bad.spec.ts": self.INVALID_SPEC})
        invalid = result["invalid"][0]
        assert "failed_checks" in invalid
        assert len(invalid["failed_checks"]) > 0


# ---------------------------------------------------------------------------
# Generator golden scenarios loading tests
# ---------------------------------------------------------------------------

class TestGeneratorScenarios:

    def test_loads_scenarios(self):
        from qa_agent.eval.eval_runner import load_generator_scenarios
        scenarios, skipped = load_generator_scenarios()
        assert len(scenarios) == 3
        assert skipped == 0

    def test_each_scenario_has_required_fields(self):
        from qa_agent.eval.eval_runner import load_generator_scenarios
        scenarios, _ = load_generator_scenarios()
        for s in scenarios:
            assert "scenario" in s
            assert "goal" in s
            assert "plan" in s
            assert len(s["plan"]) >= 1

    def test_skips_expired_scenarios(self, tmp_path):
        import json
        from qa_agent.eval.eval_runner import load_generator_scenarios
        data = [
            {
                "scenario": "expired",
                "goal": "old goal",
                "plan": [{"id": "tc-1", "title": "t", "feature": "f",
                           "route": "/r", "steps": [], "expected": []}],
                "valid_until": "2020-01-01",
            },
            {
                "scenario": "active",
                "goal": "active goal",
                "plan": [{"id": "tc-2", "title": "t", "feature": "f",
                           "route": "/r", "steps": [], "expected": []}],
                "valid_until": "2099-01-01",
            },
        ]
        path = tmp_path / "gen_scenarios.json"
        path.write_text(json.dumps(data))
        scenarios, skipped = load_generator_scenarios(path)
        assert len(scenarios) == 1
        assert skipped == 1
        assert scenarios[0]["scenario"] == "active"

    def test_skips_invalid_scenarios(self, tmp_path):
        import json
        from qa_agent.eval.eval_runner import load_generator_scenarios
        data = [{"bad_field": "no scenario or goal or plan"}]
        path = tmp_path / "bad_scenarios.json"
        path.write_text(json.dumps(data))
        scenarios, skipped = load_generator_scenarios(path)
        assert len(scenarios) == 0
        assert skipped == 1


# ---------------------------------------------------------------------------
# Generator eval integration tests (mocked generator)
# ---------------------------------------------------------------------------

_MOCK_POM = (
    "import { type Page, type Locator } from '@playwright/test';\n"
    "export class CheckoutPage {\n"
    "  private emailInput: Locator;\n"
    "  constructor(page: Page) {\n"
    "    this.emailInput = page.getByTestId('checkout-email');\n"
    "  }\n"
    "  async navigate() { await this.page.goto('/checkout'); }\n"
    "}\n"
)

_MOCK_SPEC = (
    "import { test, expect } from '@playwright/test';\n"
    "test.describe('Checkout', () => {\n"
    "  test.beforeEach(async ({ page }) => {});\n"
    "  test('fills form', async () => { await expect(true).toBeTruthy(); });\n"
    "});\n"
)

_MOCK_GENERATOR_RETURN = {
    "page_objects": {"/checkout": _MOCK_POM},
    "test_code": {"checkout.spec.ts": _MOCK_SPEC},
}


class TestGeneratorEvalIntegration:

    @pytest.mark.asyncio
    async def test_run_generator_eval_passes_with_valid_output(self, tmp_path):
        """Mocked generator returning valid POM + spec should produce a passing scorecard."""
        scenarios = [
            {
                "scenario": "checkout_page",
                "goal": "Generate tests for checkout",
                "plan": [
                    {
                        "id": "tc-1",
                        "title": "User can fill checkout form",
                        "feature": "checkout",
                        "route": "/checkout",
                        "steps": ["Navigate to /checkout", "Fill email"],
                        "expected": ["Form accepts input"],
                        "tags": ["@checkout"],
                        "source": "jira",
                    }
                ],
                "valid_until": "2027-06-01",
            }
        ]

        async def mock_generator(state):
            return _MOCK_GENERATOR_RETURN

        with patch("qa_agent.eval.eval_runner.generator", side_effect=mock_generator):
            from qa_agent.eval.eval_runner import run_generator_eval
            scorecard = await run_generator_eval(
                scenarios=scenarios,
                baseline_mode=False,
                locator_threshold=0.70,
                pom_threshold=0.80,
                test_threshold=0.80,
                reports_dir=tmp_path,
            )

        assert scorecard["agent"] == "generator"
        assert scorecard["locator_quality"]["score"] >= 0.70
        assert scorecard["pom_validity"]["score"] == 1.0
        assert scorecard["test_validity"]["score"] == 1.0
        assert scorecard["passed"] is True

    @pytest.mark.asyncio
    async def test_run_generator_eval_baseline_mode_no_pass_fail(self, tmp_path):
        """Baseline mode should set passed=None regardless of scores."""
        scenarios = [
            {
                "scenario": "checkout_page",
                "goal": "Generate tests for checkout",
                "plan": [
                    {
                        "id": "tc-1",
                        "title": "User can fill checkout form",
                        "feature": "checkout",
                        "route": "/checkout",
                        "steps": ["Navigate to /checkout"],
                        "expected": ["Form is visible"],
                        "tags": [],
                        "source": "jira",
                    }
                ],
            }
        ]

        async def mock_generator(state):
            return _MOCK_GENERATOR_RETURN

        from qa_agent.eval import eval_runner
        with patch.object(eval_runner, "generator", side_effect=mock_generator):
            scorecard = await eval_runner.run_generator_eval(
                scenarios=scenarios,
                baseline_mode=True,
                reports_dir=tmp_path,
            )


# ---------------------------------------------------------------------------
# Plan Quality scorer unit tests
# ---------------------------------------------------------------------------

class TestPlanQuality:

    def _make_test_case(
        self,
        tc_id: str,
        title: str,
        steps: list[str] | None = None,
        expected: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        return {
            "id": tc_id,
            "title": title,
            "steps": steps if steps is not None else ["Navigate to page", "Perform action"],
            "expected": expected if expected is not None else ["Expected outcome is visible"],
            "tags": tags if tags is not None else [],
        }

    def test_perfect_plan_scores_high(self):
        """A plan with >=2 steps, unique titles, and edge cases should score >=0.8."""
        test_cases = [
            self._make_test_case(
                "tc-1",
                "User can add item to cart and view cart summary",
                steps=["Navigate to product page", "Click Add to Cart", "Open cart drawer"],
                expected=["Cart shows added item with correct quantity"],
            ),
            self._make_test_case(
                "tc-2",
                "User can apply valid coupon and see discount applied",
                steps=["Navigate to cart page", "Enter valid coupon code", "Click Apply"],
                expected=["Discount is reflected in the order total"],
            ),
            self._make_test_case(
                "tc-3",
                "Invalid coupon code shows error message to user",
                steps=["Navigate to cart page", "Enter invalid coupon code", "Click Apply"],
                expected=["Error message is displayed for invalid coupon"],
                tags=["@negative"],
            ),
            self._make_test_case(
                "tc-4",
                "Empty cart shows helpful message when no items present",
                steps=["Navigate to empty cart page", "Verify cart state"],
                expected=["Empty cart message is shown to the user"],
            ),
            self._make_test_case(
                "tc-5",
                "Payment fails with insufficient funds and shows error",
                steps=["Proceed to payment page", "Enter card with insufficient funds", "Submit"],
                expected=["Payment error message is displayed"],
            ),
        ]
        acs = ["User can add items to the cart", "Invalid coupon shows error"]
        result = score_plan_quality(test_cases, acs)
        assert result["score"] >= 0.8, f"Expected score >= 0.8, got {result['score']}"

    def test_single_step_penalized(self):
        """Plan with 1-step test cases should have step_completeness < 1.0."""
        test_cases = [
            self._make_test_case(
                "tc-1",
                "User can log in",
                steps=["Click login"],  # only 1 step
                expected=["User is logged in"],
            ),
            self._make_test_case(
                "tc-2",
                "User sees dashboard",
                steps=["View dashboard"],  # only 1 step
                expected=["Dashboard is visible"],
            ),
        ]
        acs = ["User can log in"]
        result = score_plan_quality(test_cases, acs)
        assert result["step_completeness"]["score"] < 1.0, (
            f"Expected step_completeness < 1.0, got {result['step_completeness']['score']}"
        )
        assert len(result["step_completeness"]["incomplete"]) == 2

    def test_duplicate_titles_penalized(self):
        """Plan with near-duplicate titles should have deduplication < 1.0."""
        test_cases = [
            self._make_test_case(
                "tc-1",
                "User can add item to cart",
                steps=["Navigate to product", "Click add to cart"],
                expected=["Item added to cart"],
            ),
            self._make_test_case(
                "tc-2",
                "User can add item to cart",  # exact duplicate title
                steps=["Navigate to product page", "Click add to cart button"],
                expected=["Cart item count increases"],
            ),
            self._make_test_case(
                "tc-3",
                "User can remove item from cart",
                steps=["Navigate to cart", "Click remove item"],
                expected=["Item is removed from cart"],
            ),
        ]
        acs = ["User can add item to cart", "User can remove item from cart"]
        result = score_plan_quality(test_cases, acs)
        assert result["deduplication"]["score"] < 1.0, (
            f"Expected deduplication < 1.0, got {result['deduplication']['score']}"
        )
        assert len(result["deduplication"]["duplicates"]) >= 1

    def test_no_edge_cases_penalized(self):
        """Plan with zero negative/error test cases should have edge_case_coverage = 0.0."""
        test_cases = [
            self._make_test_case(
                "tc-1",
                "User can view product details",
                steps=["Navigate to product page", "Read product description"],
                expected=["Product name and description are shown"],
            ),
            self._make_test_case(
                "tc-2",
                "User can add product to wishlist",
                steps=["Navigate to product page", "Click Add to Wishlist"],
                expected=["Product appears in wishlist"],
            ),
            self._make_test_case(
                "tc-3",
                "User can share product link",
                steps=["Navigate to product page", "Click Share button"],
                expected=["Share dialog opens with product URL"],
            ),
        ]
        acs = ["Product details are visible", "User can manage wishlist"]
        result = score_plan_quality(test_cases, acs)
        assert result["edge_case_coverage"]["score"] == 0.0, (
            f"Expected edge_case_coverage = 0.0, got {result['edge_case_coverage']['score']}"
        )
        assert result["edge_case_coverage"]["edge_case_count"] == 0

    def test_empty_test_cases_returns_zero_score(self):
        """Empty plan should return overall score of 0.0."""
        result = score_plan_quality([], ["Some AC"])
        assert result["score"] == 0.0

    def test_edge_case_detected_via_tag(self):
        """Test cases tagged @error, @negative, or @edge should count as edge cases."""
        test_cases = [
            self._make_test_case(
                "tc-1",
                "User sees validation message on bad input",
                steps=["Navigate to form", "Submit empty form"],
                expected=["Validation message is shown"],
                tags=["@error"],
            ),
            self._make_test_case(
                "tc-2",
                "User successfully submits form",
                steps=["Navigate to form", "Fill all fields", "Submit"],
                expected=["Success message is shown"],
            ),
        ]
        acs = ["Form validates input"]
        result = score_plan_quality(test_cases, acs)
        assert result["edge_case_coverage"]["edge_case_count"] >= 1


# ---------------------------------------------------------------------------
# Fix Correctness scorer tests
# ---------------------------------------------------------------------------

class TestFixCorrectness:

    def test_fix_present_scores_1_0(self):
        """Healed source contains expected fix → score 1.0."""
        scenarios = [
            {
                "scenario": "button_renamed",
                "route": "/checkout",
                "expected_fix_contains": "Place Order",
            }
        ]
        healed_sources = {"/checkout": "page.getByRole('button', { name: 'Place Order' });"}
        result = score_fix_correctness(scenarios, healed_sources)
        assert result["score"] == 1.0
        assert result["correct"] == 1
        assert result["total"] == 1
        assert result["misses"] == []

    def test_fix_missing_scores_0_0(self):
        """Healed source doesn't contain expected fix → score 0.0."""
        scenarios = [
            {
                "scenario": "button_renamed",
                "route": "/checkout",
                "expected_fix_contains": "Place Order",
            }
        ]
        healed_sources = {"/checkout": "page.getByRole('button', { name: 'Submit' });"}
        result = score_fix_correctness(scenarios, healed_sources)
        assert result["score"] == 0.0
        assert result["correct"] == 0
        assert result["total"] == 1
        assert len(result["misses"]) == 1
        assert result["misses"][0]["scenario"] == "button_renamed"
        assert result["misses"][0]["expected"] == "Place Order"
        assert result["misses"][0]["found"] is False

    def test_empty_scenarios_score_1_0(self):
        """No scenarios → score 1.0 (nothing to fail)."""
        result = score_fix_correctness([], {})
        assert result["score"] == 1.0
        assert result["correct"] == 0
        assert result["total"] == 0
        assert result["misses"] == []


# ---------------------------------------------------------------------------
# Old Locator Removed scorer tests
# ---------------------------------------------------------------------------

class TestOldLocatorRemoved:

    def test_old_locator_removed_scores_1_0(self):
        """Old locator not in healed source → score 1.0."""
        scenarios = [
            {
                "scenario": "button_submit_renamed",
                "route": "/checkout",
                "error": (
                    "TimeoutError: locator.click: Timeout 30000ms exceeded.\n"
                    "  - waiting for getByRole('button', { name: 'Submit' })"
                ),
            }
        ]
        # Healed source uses the new locator, not the old one
        healed_sources = {
            "/checkout": "this.btn = page.getByRole('button', { name: 'Place Order' });"
        }
        result = score_old_locator_removed(scenarios, healed_sources)
        assert result["score"] == 1.0
        assert result["removed"] == 1
        assert result["still_present"] == 0
        assert result["failures"] == []

    def test_old_locator_still_present_scores_0_0(self):
        """Old locator still in healed source → score 0.0."""
        scenarios = [
            {
                "scenario": "testid_unchanged",
                "route": "/checkout",
                "error": (
                    "TimeoutError: locator.fill: Timeout 30000ms exceeded.\n"
                    "  - waiting for getByTestId('checkout-email')"
                ),
            }
        ]
        # Healed source still has the old broken locator
        healed_sources = {
            "/checkout": "this.emailInput = page.getByTestId('checkout-email');"
        }
        result = score_old_locator_removed(scenarios, healed_sources)
        assert result["score"] == 0.0
        assert result["removed"] == 0
        assert result["still_present"] == 1
        assert len(result["failures"]) == 1
        assert result["failures"][0]["scenario"] == "testid_unchanged"


# ---------------------------------------------------------------------------
# Import Correctness scorer unit tests
# ---------------------------------------------------------------------------

class TestImportCorrectness:

    _VALID_POM = (
        "import { type Page, type Locator } from '@playwright/test';\n"
        "export class CheckoutPage {\n"
        "  private emailInput: Locator;\n"
        "  constructor(page: Page) {\n"
        "    this.emailInput = page.getByTestId('checkout-email');\n"
        "  }\n"
        "  async navigate() { await this.page.goto('/checkout'); }\n"
        "}\n"
    )

    def test_correct_imports_score_1_0(self):
        """A test file with a valid import matching a POM class should score 1.0."""
        page_objects = {"/checkout": self._VALID_POM}
        test_code = {
            "checkout.spec.ts": (
                "import { CheckoutPage } from '../page_objects/CheckoutPage';\n"
                "import { test, expect } from '@playwright/test';\n"
            )
        }
        result = score_import_correctness(page_objects, test_code)
        assert result["score"] == 1.0
        assert result["correct"] == 1
        assert result["total"] == 1
        assert result["errors"] == []

    def test_hyphen_path_flagged(self):
        """An import using '../page-objects/' (hyphen) should be flagged as an error."""
        page_objects = {"/checkout": self._VALID_POM}
        test_code = {
            "checkout.spec.ts": (
                "import { CheckoutPage } from '../page-objects/CheckoutPage';\n"
            )
        }
        result = score_import_correctness(page_objects, test_code)
        assert result["score"] == 0.0
        assert result["total"] == 1
        assert result["correct"] == 0
        assert len(result["errors"]) == 1
        assert "hyphen" in result["errors"][0]["issue"]

    def test_empty_path_flagged(self):
        """An import with an empty filename (path ending in '/') should be flagged."""
        page_objects = {"/checkout": self._VALID_POM}
        test_code = {
            "checkout.spec.ts": (
                "import { CheckoutPage } from '../page_objects/';\n"
            )
        }
        result = score_import_correctness(page_objects, test_code)
        assert result["score"] == 0.0
        assert result["total"] == 1
        assert result["correct"] == 0
        assert len(result["errors"]) == 1
        assert "empty filename" in result["errors"][0]["issue"]

    def test_missing_pom_flagged(self):
        """An import referencing a class not present in page_objects should be flagged."""
        page_objects = {"/checkout": self._VALID_POM}  # only CheckoutPage exists
        test_code = {
            "login.spec.ts": (
                "import { LoginPage } from '../page_objects/LoginPage';\n"
            )
        }
        result = score_import_correctness(page_objects, test_code)
        assert result["score"] == 0.0
        assert result["total"] == 1
        assert result["correct"] == 0
        assert len(result["errors"]) == 1
        assert "LoginPage" in result["errors"][0]["issue"]

    def test_no_imports_score_1_0(self):
        """A test file with no page_objects import statements should score 1.0."""
        page_objects = {"/checkout": self._VALID_POM}
        test_code = {
            "checkout.spec.ts": (
                "import { test, expect } from '@playwright/test';\n"
                "test('does something', async () => {});\n"
            )
        }
        result = score_import_correctness(page_objects, test_code)
        assert result["score"] == 1.0
        assert result["total"] == 0
        assert result["correct"] == 0
        assert result["errors"] == []
