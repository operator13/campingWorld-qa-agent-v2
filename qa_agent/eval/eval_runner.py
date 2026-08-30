"""Eval Runner — orchestrates evaluation of agent nodes against golden scenarios.

MVP: Triage eval only. Loads golden scenarios, builds synthetic QAState,
runs the real triage() node, scores accuracy, produces a scorecard.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qa_agent.confidence import score_confidence
from qa_agent.eval.recommendations import generate_recommendations, format_report_markdown
from qa_agent.eval.regression import detect_regression
from qa_agent.eval.run_eval import (
    score_ac_coverage,
    score_assertion_integrity,
    score_diff_minimality,
    score_locator_quality,
    score_pom_validity,
    score_test_validity,
    score_triage_accuracy,
)
from qa_agent.eval.scorecard import build_scorecard, load_latest_scorecard, save_scorecard
from qa_agent.memory import MemoryStore
from qa_agent.nodes.generator import generator
from qa_agent.nodes.healer import healer
from qa_agent.nodes.planner import planner
from qa_agent.nodes.triage import triage
from qa_agent.schemas.models import RunResult, TestCase
from qa_agent.state import QAState

logger = logging.getLogger(__name__)

_GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
_DEFAULT_THRESHOLD = 0.75


def load_triage_scenarios(golden_path: Path | None = None) -> tuple[list[dict], int]:
    """Load and validate golden scenarios, filtering expired ones.

    Returns:
        (valid_scenarios, skipped_count)
    """
    path = golden_path or (_GOLDEN_DIR / "triage_scenarios.json")
    with open(path) as f:
        all_scenarios = json.load(f)

    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    valid = []
    skipped = 0

    for s in all_scenarios:
        # Validate required fields
        if "scenario" not in s or "expected_class" not in s or "error" not in s:
            logger.warning("Skipping invalid scenario (missing required fields): %s", s)
            skipped += 1
            continue

        # Check expiry
        valid_until = s.get("valid_until")
        if valid_until and valid_until < today:
            logger.warning("Skipping expired scenario %s (valid_until=%s)", s["scenario"], valid_until)
            skipped += 1
            continue

        valid.append(s)

    logger.info("Loaded %d triage scenarios (%d skipped)", len(valid), skipped)
    return valid, skipped


def build_synthetic_state(scenario: dict[str, Any]) -> QAState:
    """Build a minimal QAState from a golden scenario dict."""
    # Build a synthetic DOM snippet if DOM context is provided
    dom_snippet = None
    if scenario.get("dom_has_element") and scenario.get("dom_element_renamed"):
        dom_snippet = f'<button>{scenario["dom_element_renamed"]}</button>'
    elif scenario.get("dom_has_element") is False:
        dom_snippet = "<div><!-- element not found --></div>"

    return QAState(
        goal=f"eval-{scenario['scenario']}",
        error=scenario["error"],
        dom_snapshot=dom_snippet,
        run_results=RunResult(
            passed=False,
            failed_cases=[f"eval-{scenario['scenario']}"],
            logs=scenario["error"],
        ),
        attempts=0,
    )


async def run_triage_eval(
    scenarios: list[dict[str, Any]] | None = None,
    *,
    baseline_mode: bool = False,
    threshold: float | None = None,
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    """Run all triage scenarios through the real triage node and produce a scorecard.

    Args:
        scenarios: Golden scenarios. If None, loads from default path.
        baseline_mode: If True, record metrics without pass/fail.
        threshold: Override triage accuracy threshold.
        reports_dir: Override reports output directory.

    Returns:
        The full scorecard dict.
    """
    # Load scenarios
    skipped = 0
    if scenarios is None:
        scenarios, skipped = load_triage_scenarios()

    effective_threshold = threshold or _DEFAULT_THRESHOLD
    total = len(scenarios)
    logger.info("Running triage eval: %d scenarios, threshold=%.2f, baseline=%s",
                total, effective_threshold, baseline_mode)

    # Run each scenario through triage
    triage_results = []
    memory = MemoryStore()
    for i, scenario in enumerate(scenarios, 1):
        state = build_synthetic_state(scenario)
        logger.info("[%d/%d] %s", i, total, scenario["scenario"])

        try:
            result = await triage(state)
            failure_class = result.get("failure_class", "unknown")
            confidence = result.get("confidence", 0.0)

            # Reconstruct confidence breakdown for diagnostics
            breakdown = score_confidence(
                error=scenario["error"],
                failure_class=failure_class,
                dom_snapshot=state.dom_snapshot,
                memory=memory,
            )

            triage_results.append({
                "scenario": scenario["scenario"],
                "failure_class": failure_class,
                "confidence": confidence,
                "error": scenario["error"],
                "confidence_breakdown": breakdown.to_dict(),
            })
        except Exception as e:
            logger.error("Scenario %s failed: %s", scenario["scenario"], e)
            triage_results.append({
                "scenario": scenario["scenario"],
                "failure_class": "error",
                "confidence": 0.0,
                "error": scenario.get("error", ""),
                "confidence_breakdown": None,
            })

    # Build expected list for scorer
    expected = [
        {
            "scenario": s["scenario"],
            "expected_class": s["expected_class"],
            "expected_confidence_min": s.get("expected_confidence_min", 0.0),
        }
        for s in scenarios
    ]

    # Score using existing scorer
    accuracy = score_triage_accuracy(triage_results, expected)

    # Build eval result
    eval_result = {
        "triage_accuracy": accuracy,
        "scenarios": scenarios,
        "skipped_expired": skipped,
    }

    # Load previous scorecard for regression detection
    previous = load_latest_scorecard("triage", reports_dir)

    # Detect regression
    regression_report = None
    if not baseline_mode:
        temp_scorecard = {"triage_accuracy": accuracy}
        regression_report = detect_regression(temp_scorecard, previous)

    # Build and save scorecard
    run_id = f"eval-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    thresholds = {"triage_accuracy": effective_threshold}

    scorecard = build_scorecard(
        eval_result,
        run_id=run_id,
        agent="triage",
        baseline_mode=baseline_mode,
        thresholds=thresholds,
        regression_report=regression_report,
    )

    # Generate recommendations
    recommendations = generate_recommendations(scorecard)
    scorecard["recommendations"] = recommendations

    # Save scorecard JSON
    scorecard_path = save_scorecard(scorecard, reports_dir)

    # Save markdown report alongside the JSON
    report_md = format_report_markdown(scorecard)
    report_path = scorecard_path.with_suffix(".md")
    report_path.write_text(report_md)
    logger.info("Report written to %s", report_path)

    return scorecard


# ---------------------------------------------------------------------------
# Planner eval
# ---------------------------------------------------------------------------

def load_planner_scenarios(golden_path: Path | None = None) -> tuple[list[dict], int]:
    """Load and validate planner golden scenarios, filtering expired ones.

    Returns:
        (valid_scenarios, skipped_count)
    """
    path = golden_path or (_GOLDEN_DIR / "planner_scenarios.json")
    with open(path) as f:
        all_scenarios = json.load(f)

    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    valid = []
    skipped = 0

    for s in all_scenarios:
        # Validate required fields
        required = {"scenario", "goal", "acceptance_criteria", "expected_ac_coverage_min"}
        if not required.issubset(s.keys()):
            missing = required - s.keys()
            logger.warning("Skipping invalid planner scenario (missing: %s): %s", missing, s)
            skipped += 1
            continue

        # Check expiry
        valid_until = s.get("valid_until")
        if valid_until and valid_until < today:
            logger.warning(
                "Skipping expired planner scenario %s (valid_until=%s)",
                s["scenario"], valid_until,
            )
            skipped += 1
            continue

        valid.append(s)

    logger.info("Loaded %d planner scenarios (%d skipped)", len(valid), skipped)
    return valid, skipped


async def run_planner_eval(
    scenarios: list[dict[str, Any]] | None = None,
    *,
    baseline_mode: bool = False,
    threshold: float | None = None,
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    """Run all planner scenarios through the real planner node and produce a scorecard.

    Args:
        scenarios: Golden scenarios. If None, loads from default path.
        baseline_mode: If True, record metrics without pass/fail.
        threshold: Override AC coverage threshold.
        reports_dir: Override reports output directory.

    Returns:
        The full scorecard dict.
    """
    # Load scenarios
    skipped = 0
    if scenarios is None:
        scenarios, skipped = load_planner_scenarios()

    effective_threshold = threshold or _DEFAULT_THRESHOLD
    total = len(scenarios)
    logger.info(
        "Running planner eval: %d scenarios, threshold=%.2f, baseline=%s",
        total, effective_threshold, baseline_mode,
    )

    # Run each scenario through planner and score AC coverage
    all_ac_covered = 0
    all_ac_total = 0
    all_misses: list[dict[str, Any]] = []

    for i, scenario in enumerate(scenarios, 1):
        state = QAState(
            goal=scenario["goal"],
            acceptance_criteria=scenario["acceptance_criteria"],
        )
        logger.info("[%d/%d] %s", i, total, scenario["scenario"])

        try:
            result = await planner(state)
            test_cases = result.get("plan", [])

            # Convert TestCase objects to dicts for the scorer
            tc_dicts = [
                tc.model_dump() if hasattr(tc, "model_dump") else dict(tc)
                for tc in test_cases
            ]

            coverage = score_ac_coverage(scenario["acceptance_criteria"], tc_dicts)
            coverage_score = coverage["score"]
            expected_min = scenario.get("expected_ac_coverage_min", effective_threshold)
            passed_scenario = coverage_score >= expected_min
            test_count = len(tc_dicts)
            expected_count_min = scenario.get("expected_test_count_min", 1)

            all_ac_covered += coverage["covered"]
            all_ac_total += coverage["total"]

            if not passed_scenario or test_count < expected_count_min:
                miss_entry: dict[str, Any] = {
                    "scenario": scenario["scenario"],
                    "coverage_score": coverage_score,
                    "expected_coverage_min": expected_min,
                    "test_count": test_count,
                    "expected_test_count_min": expected_count_min,
                    "uncovered_acs": coverage.get("uncovered", []),
                }
                if not passed_scenario:
                    miss_entry["root_cause"] = "ac_coverage_below_threshold"
                elif test_count < expected_count_min:
                    miss_entry["root_cause"] = "insufficient_test_count"
                all_misses.append(miss_entry)

        except Exception as e:
            logger.error("Planner scenario %s failed: %s", scenario["scenario"], e)
            all_misses.append({
                "scenario": scenario["scenario"],
                "coverage_score": 0.0,
                "expected_coverage_min": scenario.get("expected_ac_coverage_min", effective_threshold),
                "test_count": 0,
                "expected_test_count_min": scenario.get("expected_test_count_min", 1),
                "uncovered_acs": scenario["acceptance_criteria"],
                "root_cause": "planner_error",
                "error": str(e),
            })
            all_ac_total += len(scenario["acceptance_criteria"])

    # Aggregate score: fraction of ACs covered across all scenarios
    overall_score = round(all_ac_covered / all_ac_total, 4) if all_ac_total > 0 else 1.0
    correct_scenarios = total - len(all_misses)

    planner_accuracy = {
        "score": overall_score,
        "correct": correct_scenarios,
        "total": total,
        "misses": all_misses,
    }

    # Build eval result
    eval_result = {
        "planner_accuracy": planner_accuracy,
        "scenarios": [
            {"scenario": s["scenario"], "category": s.get("category", "planner")}
            for s in scenarios
        ],
        "skipped_expired": skipped,
    }

    # Load previous scorecard for regression detection
    previous = load_latest_scorecard("planner", reports_dir)

    # Regression detection — wrap under the key detect_regression expects
    regression_report = None
    if not baseline_mode:
        temp_for_regression = {"triage_accuracy": planner_accuracy}
        prev_for_regression = (
            {"triage_accuracy": previous.get("planner_accuracy", {})} if previous else None
        )
        regression_report = detect_regression(temp_for_regression, prev_for_regression)

    # Build and save scorecard
    run_id = f"eval-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    thresholds = {"planner_accuracy": effective_threshold}

    scorecard = build_scorecard(
        eval_result,
        run_id=run_id,
        agent="planner",
        baseline_mode=baseline_mode,
        thresholds=thresholds,
        regression_report=regression_report,
        accuracy_key="planner_accuracy",
    )

    # Generate recommendations — existing engine reads "triage_accuracy", so alias it
    scorecard_for_recs = dict(scorecard)
    scorecard_for_recs["triage_accuracy"] = scorecard.get("planner_accuracy", {})
    scorecard_for_recs["thresholds"] = {"triage_accuracy": effective_threshold}
    recommendations = generate_recommendations(scorecard_for_recs)
    scorecard["recommendations"] = recommendations

    # Save scorecard JSON
    scorecard_path = save_scorecard(scorecard, reports_dir)

    # Save markdown report alongside the JSON
    report_md = format_report_markdown(scorecard)
    report_path = scorecard_path.with_suffix(".md")
    report_path.write_text(report_md)
    logger.info("Report written to %s", report_path)

    return scorecard


# ---------------------------------------------------------------------------
# Healer eval
# ---------------------------------------------------------------------------

def load_healer_scenarios(golden_path: Path | None = None) -> tuple[list[dict], int]:
    """Load and validate healer golden scenarios, filtering expired ones.

    Returns:
        (valid_scenarios, skipped_count)
    """
    path = golden_path or (_GOLDEN_DIR / "healer_scenarios.json")
    with open(path) as f:
        all_scenarios = json.load(f)

    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    valid = []
    skipped = 0

    for s in all_scenarios:
        # Validate required fields
        required = {"scenario", "error", "route", "old_source", "dom_snippet"}
        if not required.issubset(s.keys()):
            missing = required - s.keys()
            logger.warning("Skipping invalid healer scenario (missing: %s): %s", missing, s)
            skipped += 1
            continue

        # Check expiry
        valid_until = s.get("valid_until")
        if valid_until and valid_until < today:
            logger.warning(
                "Skipping expired healer scenario %s (valid_until=%s)",
                s["scenario"], valid_until,
            )
            skipped += 1
            continue

        valid.append(s)

    logger.info("Loaded %d healer scenarios (%d skipped)", len(valid), skipped)
    return valid, skipped


def _build_healer_state(scenario: dict[str, Any]) -> QAState:
    """Build a synthetic QAState for a healer scenario."""
    route = scenario["route"]
    test_case = TestCase(
        id=f"eval-{scenario['scenario']}",
        title=f"Eval scenario: {scenario['scenario']}",
        feature="eval",
        route=route,
        steps=["eval step"],
        expected=["eval expected"],
    )
    return QAState(
        goal=f"eval-{scenario['scenario']}",
        error=scenario["error"],
        dom_snapshot=scenario["dom_snippet"],
        page_objects={route: scenario["old_source"]},
        plan=[test_case],
        run_results=RunResult(
            passed=False,
            failed_cases=[f"eval-{scenario['scenario']}"],
            logs=scenario["error"],
        ),
        attempts=0,
    )


async def run_healer_eval(
    scenarios: list[dict[str, Any]] | None = None,
    *,
    baseline_mode: bool = False,
    threshold: float | None = None,
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    """Run all healer scenarios through the real healer node and produce a scorecard.

    Args:
        scenarios: Golden scenarios. If None, loads from default path.
        baseline_mode: If True, record metrics without pass/fail.
        threshold: Override assertion integrity threshold.
        reports_dir: Override reports output directory.

    Returns:
        The full scorecard dict.
    """
    skipped = 0
    if scenarios is None:
        scenarios, skipped = load_healer_scenarios()

    effective_threshold = threshold or _DEFAULT_THRESHOLD
    total = len(scenarios)
    logger.info(
        "Running healer eval: %d scenarios, threshold=%.2f, baseline=%s",
        total, effective_threshold, baseline_mode,
    )

    # Collect old/new sources for scoring
    old_sources: dict[str, str] = {}
    new_sources: dict[str, str] = {}
    healer_results: list[dict[str, Any]] = []

    for i, scenario in enumerate(scenarios, 1):
        state = _build_healer_state(scenario)
        route = scenario["route"]
        logger.info("[%d/%d] %s", i, total, scenario["scenario"])

        try:
            result = await healer(state)
            patched_page_objects = result.get("page_objects", {})
            new_source = patched_page_objects.get(route, scenario["old_source"])

            old_sources[route] = scenario["old_source"]
            new_sources[route] = new_source

            expected_fix = scenario.get("expected_fix_contains", "")
            fix_present = bool(expected_fix and expected_fix in new_source)

            healer_results.append({
                "scenario": scenario["scenario"],
                "route": route,
                "fix_present": fix_present,
                "expected_fix_contains": expected_fix,
                "attempts": result.get("attempts", 0),
            })
        except Exception as e:
            logger.error("Healer scenario %s failed: %s", scenario["scenario"], e)
            old_sources[route] = scenario["old_source"]
            new_sources[route] = scenario["old_source"]
            healer_results.append({
                "scenario": scenario["scenario"],
                "route": route,
                "fix_present": False,
                "expected_fix_contains": scenario.get("expected_fix_contains", ""),
                "attempts": 0,
                "error": str(e),
            })

    # Score
    assertion_integrity = score_assertion_integrity(old_sources, new_sources)
    diff_minimality = score_diff_minimality(old_sources, new_sources)

    # Fix presence rate (how many scenarios had the expected fix in output)
    fix_present_count = sum(1 for r in healer_results if r.get("fix_present"))
    fix_rate = fix_present_count / total if total > 0 else 1.0

    # Primary metric for scorecard pass/fail is assertion_integrity
    primary_accuracy = {
        "score": assertion_integrity["score"],
        "correct": assertion_integrity["clean"],
        "total": assertion_integrity["total"],
        "misses": [
            {"scenario": route, "reason": "assertion_violation"}
            for route in assertion_integrity.get("violation_routes", [])
        ],
    }

    eval_result = {
        "healer_accuracy": primary_accuracy,
        "assertion_integrity": assertion_integrity,
        "diff_minimality": diff_minimality,
        "fix_rate": {"score": round(fix_rate, 4), "correct": fix_present_count, "total": total},
        "scenarios": [
            {"scenario": s["scenario"], "category": "locator_drift"}
            for s in scenarios
        ],
        "skipped_expired": skipped,
    }

    # Load previous scorecard for regression detection
    previous = load_latest_scorecard("healer", reports_dir)

    regression_report = None
    if not baseline_mode:
        temp_for_regression = {"triage_accuracy": primary_accuracy}
        prev_for_regression = (
            {"triage_accuracy": previous.get("healer_accuracy", {})} if previous else None
        )
        regression_report = detect_regression(temp_for_regression, prev_for_regression)

    run_id = f"eval-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    thresholds = {"healer_accuracy": effective_threshold}

    scorecard = build_scorecard(
        eval_result,
        run_id=run_id,
        agent="healer",
        baseline_mode=baseline_mode,
        thresholds=thresholds,
        regression_report=regression_report,
        accuracy_key="healer_accuracy",
    )

    # Attach extra healer-specific metrics to scorecard
    scorecard["assertion_integrity"] = assertion_integrity
    scorecard["diff_minimality"] = diff_minimality
    scorecard["fix_rate"] = eval_result["fix_rate"]

    # Generate recommendations — alias healer_accuracy to triage_accuracy for engine compatibility
    scorecard_for_recs = dict(scorecard)
    scorecard_for_recs["triage_accuracy"] = scorecard.get("healer_accuracy", {})
    scorecard_for_recs["thresholds"] = {"triage_accuracy": effective_threshold}
    healer_recs = generate_recommendations(scorecard_for_recs)
    scorecard["recommendations"] = healer_recs

    # Save scorecard JSON
    scorecard_path = save_scorecard(scorecard, reports_dir)

    # Save markdown report
    healer_report_md = format_report_markdown(scorecard)
    healer_report_path = scorecard_path.with_suffix(".md")
    healer_report_path.write_text(healer_report_md)
    logger.info("Report written to %s", healer_report_path)

    return scorecard


# ---------------------------------------------------------------------------
# Generator eval
# ---------------------------------------------------------------------------

def load_generator_scenarios(golden_path: Path | None = None) -> tuple[list[dict], int]:
    """Load and validate generator golden scenarios, filtering expired ones.

    Returns:
        (valid_scenarios, skipped_count)
    """
    path = golden_path or (_GOLDEN_DIR / "generator_scenarios.json")
    with open(path) as f:
        all_scenarios = json.load(f)

    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    valid = []
    skipped = 0

    for s in all_scenarios:
        # Validate required fields
        if "scenario" not in s or "goal" not in s or "plan" not in s:
            logger.warning(
                "Skipping invalid generator scenario (missing required fields): %s", s
            )
            skipped += 1
            continue

        # Check expiry
        valid_until = s.get("valid_until")
        if valid_until and valid_until < today:
            logger.warning(
                "Skipping expired generator scenario %s (valid_until=%s)",
                s["scenario"],
                valid_until,
            )
            skipped += 1
            continue

        valid.append(s)

    logger.info("Loaded %d generator scenarios (%d skipped)", len(valid), skipped)
    return valid, skipped


def _build_generator_state(scenario: dict[str, Any]) -> QAState:
    """Build a QAState for generator eval from a generator golden scenario."""
    plan = [
        TestCase(
            id=tc["id"],
            title=tc["title"],
            feature=tc["feature"],
            route=tc["route"],
            steps=tc["steps"],
            expected=tc["expected"],
            tags=tc.get("tags", []),
            source=tc.get("source", "jira"),
        )
        for tc in scenario["plan"]
    ]
    return QAState(
        goal=scenario["goal"],
        plan=plan,
        attempts=0,
    )


async def run_generator_eval(
    scenarios: list[dict[str, Any]] | None = None,
    *,
    baseline_mode: bool = False,
    locator_threshold: float | None = None,
    pom_threshold: float | None = None,
    test_threshold: float | None = None,
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    """Run all generator scenarios through the real generator node and produce a scorecard.

    Args:
        scenarios: Generator golden scenarios. If None, loads from default path.
        baseline_mode: If True, record metrics without pass/fail.
        locator_threshold: Override locator quality threshold (default 0.70).
        pom_threshold: Override POM validity threshold (default 0.80).
        test_threshold: Override test validity threshold (default 0.80).
        reports_dir: Override reports output directory.

    Returns:
        The full scorecard dict.
    """
    skipped = 0
    if scenarios is None:
        scenarios, skipped = load_generator_scenarios()

    effective_locator_threshold = locator_threshold if locator_threshold is not None else 0.70
    effective_pom_threshold = pom_threshold if pom_threshold is not None else 0.80
    effective_test_threshold = test_threshold if test_threshold is not None else 0.80

    total = len(scenarios)
    logger.info(
        "Running generator eval: %d scenarios, baseline=%s",
        total,
        baseline_mode,
    )

    all_page_objects: dict[str, str] = {}
    all_test_code: dict[str, str] = {}
    scenario_results: list[dict[str, Any]] = []

    for i, scenario in enumerate(scenarios, 1):
        state = _build_generator_state(scenario)
        logger.info("[%d/%d] %s", i, total, scenario["scenario"])

        try:
            result = await generator(state)
            po = result.get("page_objects", {})
            tc = result.get("test_code", {})
            all_page_objects.update(po)
            all_test_code.update(tc)
            scenario_results.append({
                "scenario": scenario["scenario"],
                "page_objects_count": len(po),
                "test_files_count": len(tc),
                "error": None,
            })
        except Exception as e:
            logger.error("Generator scenario %s failed: %s", scenario["scenario"], e)
            scenario_results.append({
                "scenario": scenario["scenario"],
                "page_objects_count": 0,
                "test_files_count": 0,
                "error": str(e),
            })

    # Score all accumulated outputs
    locator_result = score_locator_quality(all_page_objects)
    pom_result = score_pom_validity(all_page_objects)
    test_result = score_test_validity(all_test_code)

    thresholds = {
        "locator_quality": effective_locator_threshold,
        "pom_validity": effective_pom_threshold,
        "test_validity": effective_test_threshold,
    }

    # Determine overall pass/fail
    passed: bool | None = None
    if not baseline_mode:
        passed = (
            locator_result["score"] >= effective_locator_threshold
            and pom_result["score"] >= effective_pom_threshold
            and test_result["score"] >= effective_test_threshold
        )

    run_id = f"eval-generator-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    scorecard: dict[str, Any] = {
        "eval_run_id": run_id,
        "agent": "generator",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "baseline_mode": baseline_mode,
        "scenarios_total": total,
        "scenarios_skipped_expired": skipped,
        "locator_quality": locator_result,
        "pom_validity": pom_result,
        "test_validity": test_result,
        "thresholds": thresholds,
        "passed": passed,
        "scenario_results": scenario_results,
    }

    # Generate recommendations
    recommendations = _generate_generator_recommendations(scorecard)
    scorecard["recommendations"] = recommendations

    # Save scorecard JSON
    scorecard_path = save_scorecard(scorecard, reports_dir)

    # Save markdown report alongside the JSON
    report_md = _format_generator_report_markdown(scorecard)
    report_path = scorecard_path.with_suffix(".md")
    report_path.write_text(report_md)
    logger.info("Generator report written to %s", report_path)

    return scorecard


def _generate_generator_recommendations(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate actionable recommendations from a generator scorecard."""
    recs: list[dict[str, Any]] = []
    thresholds = scorecard.get("thresholds", {})

    locator = scorecard.get("locator_quality", {})
    pom = scorecard.get("pom_validity", {})
    test = scorecard.get("test_validity", {})

    locator_score = locator.get("score", 0.0)
    pom_score = pom.get("score", 0.0)
    test_score = test.get("score", 0.0)

    locator_threshold = thresholds.get("locator_quality", 0.70)
    pom_threshold = thresholds.get("pom_validity", 0.80)
    test_threshold = thresholds.get("test_validity", 0.80)

    if locator_score < locator_threshold:
        brittle = locator.get("brittle", 0)
        total_loc = locator.get("total", 0)
        recs.append({
            "priority": "high",
            "category": "locator_quality",
            "finding": (
                f"Locator quality {locator_score:.1%} is below threshold {locator_threshold:.1%}. "
                f"{brittle}/{total_loc} locators use brittle CSS selectors."
            ),
            "action": (
                "Update GENERATOR.md prompt to enforce getByRole(), getByTestId(), "
                "getByLabel(), and getByText() — ban CSS selectors in POMs."
            ),
        })

    if pom_score < pom_threshold:
        invalid_poms = pom.get("invalid", [])
        recs.append({
            "priority": "high",
            "category": "pom_validity",
            "finding": (
                f"POM validity {pom_score:.1%} is below threshold {pom_threshold:.1%}. "
                f"{len(invalid_poms)} POM(s) are missing required structure."
            ),
            "action": (
                "Ensure GENERATOR.md prompt requires: class declaration, "
                "constructor(page: Page), navigate() method, export statement, and Locator types."
            ),
        })

    if test_score < test_threshold:
        invalid_tests = test.get("invalid", [])
        recs.append({
            "priority": "high",
            "category": "test_validity",
            "finding": (
                f"Test validity {test_score:.1%} is below threshold {test_threshold:.1%}. "
                f"{len(invalid_tests)} test file(s) are missing required structure."
            ),
            "action": (
                "Ensure GENERATOR.md prompt requires: test.describe() block, "
                "test() cases, beforeEach() hook, and at least one expect() assertion."
            ),
        })

    if (
        locator_score >= locator_threshold
        and pom_score >= pom_threshold
        and test_score >= test_threshold
    ):
        recs.append({
            "priority": "low",
            "category": "overall",
            "finding": "All generator metrics pass. Generated code quality is above all thresholds.",
            "action": "No action needed. Consider adding more complex golden scenarios.",
        })

    priority_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 9))
    return recs


def _format_generator_report_markdown(scorecard: dict[str, Any]) -> str:
    """Generate a human-readable markdown report from a generator scorecard."""
    lines = ["# Generator Eval Report", ""]

    passed = scorecard.get("passed")
    status = "BASELINE" if passed is None else ("PASS" if passed else "FAIL")
    mode = " (baseline)" if scorecard.get("baseline_mode") else ""

    lines.append(f"**Run:** {scorecard.get('eval_run_id', 'unknown')}{mode}")
    lines.append(f"**Timestamp:** {scorecard.get('timestamp', 'unknown')}")
    lines.append(f"**Result:** {status}")
    lines.append("")

    thresholds = scorecard.get("thresholds", {})
    for key, label in [
        ("locator_quality", "Locator Quality"),
        ("pom_validity", "POM Validity"),
        ("test_validity", "Test Validity"),
    ]:
        metric = scorecard.get(key, {})
        score = metric.get("score", 0.0)
        threshold = thresholds.get(key, 0.0)
        status_str = "PASS" if score >= threshold else "FAIL"
        lines.append(
            f"## {label}: {score * 100:.1f}% (threshold: {threshold * 100:.1f}%) — {status_str}"
        )
        lines.append("")
        if key == "locator_quality":
            lines.append(f"- Good locators: {metric.get('good', 0)}")
            lines.append(f"- Brittle locators: {metric.get('brittle', 0)}")
        else:
            lines.append(f"- Valid: {metric.get('valid', 0)}/{metric.get('total', 0)}")
            invalid_items = metric.get("invalid", [])
            if invalid_items:
                lines.append(f"- Invalid items: {len(invalid_items)}")
        lines.append("")

    recs = scorecard.get("recommendations", [])
    if recs:
        lines.append("## Recommendations")
        lines.append("")
        for r in recs:
            priority = r["priority"].upper()
            lines.append(f"### [{priority}] {r.get('category', 'general')}")
            lines.append("")
            lines.append(f"**Finding:** {r['finding']}")
            lines.append("")
            lines.append(f"**Action:** {r['action']}")
            lines.append("")

    return "\n".join(lines)
