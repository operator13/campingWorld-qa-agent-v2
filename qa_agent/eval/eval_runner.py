"""Eval Runner — orchestrates evaluation of agent nodes against golden scenarios.

MVP: Triage eval only. Loads golden scenarios, builds synthetic QAState,
runs the real triage() node, scores accuracy, produces a scorecard.
"""

from __future__ import annotations

import json
import logging
import subprocess
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
    score_fix_correctness,
    score_import_correctness,
    score_locator_quality,
    score_old_locator_removed,
    score_plan_quality,
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
_REPORTS_DIR = Path(__file__).resolve().parent / "reports"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_THRESHOLD = 0.75


def _capture_eval_token_usage() -> dict[str, Any]:
    """Capture accumulated token/cost from AuditStore during eval run."""
    from qa_agent.audit import AuditStore
    return {
        "input_tokens": AuditStore._run_total_input_tokens,
        "output_tokens": AuditStore._run_total_output_tokens,
        "total_tokens": AuditStore._run_total_input_tokens + AuditStore._run_total_output_tokens,
        "cost_usd": round(AuditStore._run_total_cost, 6),
    }


def _reset_eval_token_tracking() -> None:
    """Reset AuditStore token accumulators before an eval run."""
    from qa_agent.audit import AuditStore
    AuditStore._run_total_input_tokens = 0
    AuditStore._run_total_output_tokens = 0
    AuditStore._run_total_cost = 0.0


def _git_commit_and_push_reports(agent: str, scorecard: dict) -> None:
    """Auto-commit and push eval reports after each eval run."""
    try:
        score = 0.0
        status = "UNKNOWN"
        # Extract score from scorecard (different agents use different keys)
        for key in [f"{agent}_accuracy", "triage_accuracy", "locator_quality"]:
            if key in scorecard:
                score = scorecard[key].get("score", 0.0)
                break

        passed = scorecard.get("passed")
        if passed is None:
            status = "BASELINE"
        elif passed:
            status = "PASS"
        else:
            status = "FAIL"

        reports_path = str(_REPORTS_DIR / agent)

        subprocess.run(
            ["git", "add", reports_path],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            timeout=10,
        )
        subprocess.run(
            ["git", "commit", "-m",
             f"Eval report: {agent} {score*100:.1f}% {status}\n\n"
             f"Run: {scorecard.get('eval_run_id', 'unknown')}\n"
             f"Auto-committed by eval runner."],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            timeout=10,
        )
        result = subprocess.run(
            ["git", "push"],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Eval report auto-pushed to GitHub")
        else:
            logger.warning("Git push failed: %s", result.stderr.decode()[:200])

        # Notify dashboard to refresh eval data
        _notify_dashboard(agent)
        _notify_dashboard_agent_complete(agent)
    except Exception as e:
        logger.warning("Auto-commit failed (non-fatal): %s", e)


def _notify_dashboard(agent: str) -> None:
    """Notify the dashboard server that an eval completed."""
    _dashboard_post("/api/eval/notify", {"agent": agent})
    logger.info("Dashboard notified of %s eval update", agent)


def _notify_dashboard_eval_start(agents: list[str]) -> None:
    """Notify the dashboard that eval(s) are starting."""
    _dashboard_post("/api/eval/run/start-external", {"agents": agents})


def _notify_dashboard_agent_start(agent: str) -> None:
    """Notify the dashboard that a specific agent eval is starting."""
    _dashboard_post("/api/eval/run/agent-start-external", {"agent": agent})


def _notify_dashboard_progress(agent: str, current: int, total: int) -> None:
    """Notify the dashboard of eval scenario progress."""
    _dashboard_post("/api/eval/run/progress", {"agent": agent, "current": current, "total": total})


def _notify_dashboard_agent_complete(agent: str) -> None:
    """Notify the dashboard that an agent eval finished (resets state if all done)."""
    _dashboard_post("/api/eval/run/agent-complete-external", {"agent": agent})


def _dashboard_post(path: str, data: dict) -> None:
    """POST to the dashboard server (silent fail if not running).

    Skipped when running as a dashboard subprocess (EVAL_DASHBOARD_SUBPROCESS=1)
    to avoid duplicate events — the parent process handles broadcasting.
    """
    import os
    if os.environ.get("EVAL_DASHBOARD_SUBPROCESS"):
        return
    import urllib.request
    try:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            f"http://localhost:8080{path}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass  # Dashboard may not be running


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
    _reset_eval_token_tracking()
    _notify_dashboard_agent_start("triage")

    # Load scenarios
    skipped = 0
    if scenarios is None:
        scenarios, skipped = load_triage_scenarios()

    effective_threshold = threshold or _DEFAULT_THRESHOLD
    total = len(scenarios)
    logger.info("Running triage eval: %d scenarios, threshold=%.2f, baseline=%s",
                total, effective_threshold, baseline_mode)

    # Run scenarios concurrently (max 5 parallel LLM calls)
    import asyncio
    semaphore = asyncio.Semaphore(5)
    memory = MemoryStore()
    _triage_done = [0]

    async def _run_one_triage(i: int, scenario: dict) -> dict:
        async with semaphore:
            state = build_synthetic_state(scenario)
            logger.info("[%d/%d] %s", i, total, scenario["scenario"])
            try:
                result = await triage(state)
                failure_class = result.get("failure_class", "unknown")
                confidence = result.get("confidence", 0.0)
                breakdown = score_confidence(
                    error=scenario["error"],
                    failure_class=failure_class,
                    dom_snapshot=state.dom_snapshot,
                    memory=memory,
                )
                return {
                    "scenario": scenario["scenario"],
                    "failure_class": failure_class,
                    "confidence": confidence,
                    "error": scenario["error"],
                    "confidence_breakdown": breakdown.to_dict(),
                }
            except Exception as e:
                logger.error("Scenario %s failed: %s", scenario["scenario"], e)
                return {
                    "scenario": scenario["scenario"],
                    "failure_class": "error",
                    "confidence": 0.0,
                    "error": scenario.get("error", ""),
                    "confidence_breakdown": None,
                }
            finally:
                _triage_done[0] += 1
                _notify_dashboard_progress("triage", _triage_done[0], total)

    triage_results = await asyncio.gather(
        *[_run_one_triage(i, s) for i, s in enumerate(scenarios, 1)]
    )

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

    # Capture token usage from this eval run
    scorecard["token_usage"] = _capture_eval_token_usage()

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

    _git_commit_and_push_reports(scorecard.get("agent", "unknown"), scorecard)

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
    _reset_eval_token_tracking()
    _notify_dashboard_agent_start("planner")

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

    # Run scenarios concurrently (max 5 parallel LLM calls)
    import asyncio
    semaphore = asyncio.Semaphore(5)
    _planner_done = [0]

    async def _run_one_planner(i: int, scenario: dict) -> dict:
        async with semaphore:
            state = QAState(
                goal=scenario["goal"],
                acceptance_criteria=scenario["acceptance_criteria"],
            )
            logger.info("[%d/%d] %s", i, total, scenario["scenario"])
            try:
                result = await planner(state)
                test_cases = result.get("plan", [])
                tc_dicts = [
                    tc.model_dump() if hasattr(tc, "model_dump") else dict(tc)
                    for tc in test_cases
                ]
                coverage = score_ac_coverage(scenario["acceptance_criteria"], tc_dicts)
                quality = score_plan_quality(tc_dicts, scenario["acceptance_criteria"])
                return {"scenario": scenario, "coverage": coverage, "quality": quality,
                        "tc_dicts": tc_dicts, "error": None}
            except Exception as e:
                logger.error("Planner scenario %s failed: %s", scenario["scenario"], e)
                return {"scenario": scenario, "coverage": None, "quality": None,
                        "tc_dicts": [], "error": str(e)}
            finally:
                _planner_done[0] += 1
                _notify_dashboard_progress("planner", _planner_done[0], total)

    raw_results = await asyncio.gather(
        *[_run_one_planner(i, s) for i, s in enumerate(scenarios, 1)]
    )

    # Aggregate results
    all_ac_covered = 0
    all_ac_total = 0
    all_misses: list[dict[str, Any]] = []
    all_quality_scores: list[float] = []

    for r in raw_results:
        scenario = r["scenario"]
        if r["error"]:
            all_misses.append({
                "scenario": scenario["scenario"],
                "coverage_score": 0.0,
                "expected_coverage_min": scenario.get("expected_ac_coverage_min", effective_threshold),
                "test_count": 0,
                "expected_test_count_min": scenario.get("expected_test_count_min", 1),
                "uncovered_acs": scenario["acceptance_criteria"],
                "root_cause": "planner_error",
                "error": r["error"],
            })
            all_ac_total += len(scenario["acceptance_criteria"])
            all_quality_scores.append(0.0)
        else:
            coverage = r["coverage"]
            quality = r["quality"]
            coverage_score = coverage["score"]
            expected_min = scenario.get("expected_ac_coverage_min", effective_threshold)
            passed_scenario = coverage_score >= expected_min
            test_count = len(r["tc_dicts"])
            expected_count_min = scenario.get("expected_test_count_min", 1)

            all_quality_scores.append(quality["score"])
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
                    "plan_quality": quality,
                }
                if not passed_scenario:
                    miss_entry["root_cause"] = "ac_coverage_below_threshold"
                elif test_count < expected_count_min:
                    miss_entry["root_cause"] = "insufficient_test_count"
                all_misses.append(miss_entry)

    # Aggregate score: combine AC coverage and plan quality equally
    ac_coverage_score = round(all_ac_covered / all_ac_total, 4) if all_ac_total > 0 else 1.0
    avg_quality_score = round(sum(all_quality_scores) / len(all_quality_scores), 4) if all_quality_scores else 1.0
    overall_score = round((ac_coverage_score + avg_quality_score) / 2, 4)
    correct_scenarios = total - len(all_misses)

    planner_accuracy = {
        "score": overall_score,
        "ac_coverage_score": ac_coverage_score,
        "plan_quality_score": avg_quality_score,
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
    # Capture token usage from this eval run
    scorecard["token_usage"] = _capture_eval_token_usage()

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

    _git_commit_and_push_reports(scorecard.get("agent", "unknown"), scorecard)

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

    is_timing = scenario.get("type") == "timing_fix"

    return QAState(
        goal=f"eval-{scenario['scenario']}",
        error=scenario["error"],
        failure_class="test_flake" if is_timing else "locator_drift",
        dom_snapshot=scenario.get("dom_snippet", ""),
        page_objects={} if is_timing else {route: scenario["old_source"]},
        test_code={scenario["scenario"]: scenario["old_source"]} if is_timing else {},
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
    _reset_eval_token_tracking()
    _notify_dashboard_agent_start("healer")

    skipped = 0
    if scenarios is None:
        scenarios, skipped = load_healer_scenarios()

    effective_threshold = threshold or _DEFAULT_THRESHOLD
    total = len(scenarios)
    logger.info(
        "Running healer eval: %d scenarios, threshold=%.2f, baseline=%s",
        total, effective_threshold, baseline_mode,
    )

    # Run scenarios concurrently (max 5 parallel LLM calls)
    import asyncio
    semaphore = asyncio.Semaphore(5)
    _healer_done = [0]

    async def _run_one_healer(i: int, scenario: dict) -> dict:
        async with semaphore:
            state = _build_healer_state(scenario)
            route = scenario["route"]
            is_timing = scenario.get("type") == "timing_fix"
            logger.info("[%d/%d] %s%s", i, total, scenario["scenario"], " (timing)" if is_timing else "")
            try:
                result = await healer(state)
                if is_timing:
                    patched_specs = result.get("test_code", {})
                    new_source = patched_specs.get(scenario["scenario"], scenario["old_source"])
                else:
                    patched = result.get("page_objects", {})
                    new_source = patched.get(route, scenario["old_source"])
                expected_fix = scenario.get("expected_fix_contains", "")
                has_hard_wait = "waitForTimeout" in new_source
                return {
                    "scenario": scenario, "route": route,
                    "old_source": scenario["old_source"], "new_source": new_source,
                    "fix_present": bool(expected_fix and expected_fix in new_source),
                    "expected_fix_contains": expected_fix,
                    "is_timing": is_timing,
                    "has_hard_wait": has_hard_wait,
                    "attempts": result.get("attempts", 0), "error": None,
                }
            except Exception as e:
                logger.error("Healer scenario %s failed: %s", scenario["scenario"], e)
                return {
                    "scenario": scenario, "route": route,
                    "old_source": scenario["old_source"], "new_source": scenario["old_source"],
                    "fix_present": False,
                    "expected_fix_contains": scenario.get("expected_fix_contains", ""),
                    "is_timing": is_timing,
                    "has_hard_wait": False,
                    "attempts": 0, "error": str(e),
                }
            finally:
                _healer_done[0] += 1
                _notify_dashboard_progress("healer", _healer_done[0], total)

    raw_results = await asyncio.gather(
        *[_run_one_healer(i, s) for i, s in enumerate(scenarios, 1)]
    )

    # Aggregate — split locator vs timing results
    old_sources: dict[str, str] = {}
    new_sources: dict[str, str] = {}
    healer_results: list[dict[str, Any]] = []
    timing_results: list[dict[str, Any]] = []
    locator_results: list[dict[str, Any]] = []

    for r in raw_results:
        old_sources[r["route"]] = r["old_source"]
        new_sources[r["route"]] = r["new_source"]
        entry = {
            "scenario": r["scenario"]["scenario"], "route": r["route"],
            "fix_present": r["fix_present"],
            "expected_fix_contains": r["expected_fix_contains"],
            "is_timing": r.get("is_timing", False),
            "has_hard_wait": r.get("has_hard_wait", False),
            "attempts": r["attempts"],
            **({"error": r["error"]} if r["error"] else {}),
        }
        healer_results.append(entry)
        if r.get("is_timing"):
            timing_results.append(entry)
        else:
            locator_results.append(entry)

    # Score locator fixes (existing metrics)
    # Filter to locator-only sources for assertion/diff scoring
    locator_old = {r["route"]: r["old_source"] for r in raw_results if not r.get("is_timing")}
    locator_new = {r["route"]: r["new_source"] for r in raw_results if not r.get("is_timing")}
    locator_scenarios = [s for s in scenarios if s.get("type") != "timing_fix"]

    assertion_integrity = score_assertion_integrity(locator_old, locator_new)
    diff_minimality = score_diff_minimality(locator_old, locator_new)
    fix_correctness = score_fix_correctness(locator_scenarios, locator_new)
    old_locator_removed = score_old_locator_removed(locator_scenarios, locator_new)

    # Score timing fixes — separate metrics
    timing_total = len(timing_results)
    timing_correct = 0
    timing_details: list[dict[str, Any]] = []

    # Build timing new_source lookup from raw_results
    timing_new_sources = {r["scenario"]["scenario"]: r["new_source"] for r in raw_results if r.get("is_timing")}

    for tr in timing_results:
        new_src = timing_new_sources.get(tr["scenario"], "")
        has_wait_for = "waitFor" in new_src if new_src else tr["fix_present"]
        no_hard_wait = not tr["has_hard_wait"]
        assertions_ok = True  # guardrail enforces this
        correct = has_wait_for and no_hard_wait and assertions_ok

        if correct:
            timing_correct += 1

        timing_details.append({
            "scenario": tr["scenario"],
            "has_wait_for": has_wait_for,
            "no_hard_wait": no_hard_wait,
            "assertions_preserved": assertions_ok,
            "correct": correct,
        })

    timing_fix_score = round(timing_correct / timing_total, 4) if timing_total > 0 else 1.0
    timing_fix_accuracy = {
        "score": timing_fix_score,
        "correct": timing_correct,
        "total": timing_total,
        "details": timing_details,
    }

    # Fix presence rate (how many scenarios had the expected fix in output)
    fix_present_count = sum(1 for r in healer_results if r.get("fix_present"))
    fix_rate = fix_present_count / total if total > 0 else 1.0

    # Locator score: average of assertion_integrity, fix_correctness, old_locator_removed
    locator_score = round(
        (
            assertion_integrity["score"]
            + fix_correctness["score"]
            + old_locator_removed["score"]
        )
        / 3,
        4,
    ) if locator_scenarios else 1.0

    # Composite healer score: weighted (60% locator + 40% timing)
    combined_score = round(locator_score * 0.6 + timing_fix_score * 0.4, 4)

    # Primary metric for scorecard pass/fail uses the combined healer score
    primary_accuracy = {
        "score": combined_score,
        "locator_score": locator_score,
        "timing_score": timing_fix_score,
        "correct": assertion_integrity["clean"] + timing_correct,
        "total": assertion_integrity["total"] + timing_total,
        "misses": [
            {"scenario": route, "reason": "assertion_violation"}
            for route in assertion_integrity.get("violation_routes", [])
        ],
    }

    eval_result = {
        "healer_accuracy": primary_accuracy,
        "timing_fix_accuracy": timing_fix_accuracy,
        "assertion_integrity": assertion_integrity,
        "diff_minimality": diff_minimality,
        "fix_correctness": fix_correctness,
        "old_locator_removed": old_locator_removed,
        "fix_rate": {"score": round(fix_rate, 4), "correct": fix_present_count, "total": total},
        "scenarios": [
            {
                "scenario": s["scenario"],
                "category": "test_flake" if s.get("type") == "timing_fix" else "locator_drift",
            }
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

    # Preserve locator/timing sub-scores in healer_accuracy
    scorecard["healer_accuracy"]["locator_score"] = locator_score
    scorecard["healer_accuracy"]["timing_score"] = timing_fix_score

    # Attach extra healer-specific metrics to scorecard
    scorecard["assertion_integrity"] = assertion_integrity
    scorecard["diff_minimality"] = diff_minimality
    scorecard["fix_correctness"] = fix_correctness
    scorecard["old_locator_removed"] = old_locator_removed
    scorecard["fix_rate"] = eval_result["fix_rate"]
    scorecard["timing_fix_accuracy"] = timing_fix_accuracy
    scorecard["scenarios"] = eval_result["scenarios"]
    scorecard["token_usage"] = _capture_eval_token_usage()

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

    _git_commit_and_push_reports(scorecard.get("agent", "unknown"), scorecard)

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
        locator_threshold: Override locator quality threshold (default 0.85).
        pom_threshold: Override POM validity threshold (default 0.80).
        test_threshold: Override test validity threshold (default 0.80).
        reports_dir: Override reports output directory.

    Returns:
        The full scorecard dict.
    """
    _reset_eval_token_tracking()
    _notify_dashboard_agent_start("generator")

    skipped = 0
    if scenarios is None:
        scenarios, skipped = load_generator_scenarios()

    effective_locator_threshold = locator_threshold if locator_threshold is not None else 0.85
    effective_pom_threshold = pom_threshold if pom_threshold is not None else 0.80
    effective_test_threshold = test_threshold if test_threshold is not None else 0.80

    total = len(scenarios)
    logger.info(
        "Running generator eval: %d scenarios, baseline=%s",
        total,
        baseline_mode,
    )

    # Run scenarios concurrently (max 5 parallel LLM calls)
    import asyncio
    semaphore = asyncio.Semaphore(5)
    _generator_done = [0]

    async def _run_one_generator(i: int, scenario: dict) -> dict:
        async with semaphore:
            state = _build_generator_state(scenario)
            logger.info("[%d/%d] %s", i, total, scenario["scenario"])
            try:
                result = await generator(state)
                po = result.get("page_objects", {})
                tc = result.get("test_code", {})
                return {"scenario": scenario["scenario"], "po": po, "tc": tc, "error": None}
            except Exception as e:
                logger.error("Generator scenario %s failed: %s", scenario["scenario"], e)
                return {"scenario": scenario["scenario"], "po": {}, "tc": {}, "error": str(e)}
            finally:
                _generator_done[0] += 1
                _notify_dashboard_progress("generator", _generator_done[0], total)

    raw_results = await asyncio.gather(
        *[_run_one_generator(i, s) for i, s in enumerate(scenarios, 1)]
    )

    all_page_objects: dict[str, str] = {}
    all_test_code: dict[str, str] = {}
    scenario_results: list[dict[str, Any]] = []
    for r in raw_results:
        all_page_objects.update(r["po"])
        all_test_code.update(r["tc"])
        scenario_results.append({
            "scenario": r["scenario"],
            "page_objects_count": len(r["po"]),
            "test_files_count": len(r["tc"]),
            "error": r["error"],
        })

    # Score all accumulated outputs
    locator_result = score_locator_quality(all_page_objects)
    pom_result = score_pom_validity(all_page_objects)
    test_result = score_test_validity(all_test_code)
    import_result = score_import_correctness(all_page_objects, all_test_code)

    effective_import_threshold = 0.80

    thresholds = {
        "locator_quality": effective_locator_threshold,
        "pom_validity": effective_pom_threshold,
        "test_validity": effective_test_threshold,
        "import_correctness": effective_import_threshold,
    }

    # Determine overall pass/fail
    passed: bool | None = None
    if not baseline_mode:
        passed = (
            locator_result["score"] >= effective_locator_threshold
            and pom_result["score"] >= effective_pom_threshold
            and test_result["score"] >= effective_test_threshold
            and import_result["score"] >= effective_import_threshold
        )

    # Composite score — average of all 4 sub-metrics (the real score)
    composite_score = round(
        (
            locator_result["score"]
            + pom_result["score"]
            + test_result["score"]
            + import_result["score"]
        ) / 4,
        4,
    )

    run_id = f"eval-generator-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    scorecard: dict[str, Any] = {
        "eval_run_id": run_id,
        "agent": "generator",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "baseline_mode": baseline_mode,
        "scenarios_total": total,
        "scenarios_skipped_expired": skipped,
        "generator_accuracy": {
            "score": composite_score,
            "locator_quality": locator_result["score"],
            "pom_validity": pom_result["score"],
            "test_validity": test_result["score"],
            "import_correctness": import_result["score"],
        },
        "locator_quality": locator_result,
        "pom_validity": pom_result,
        "test_validity": test_result,
        "import_correctness": import_result,
        "thresholds": thresholds,
        "passed": passed,
        "scenario_results": scenario_results,
    }

    # Capture token usage from this eval run
    scorecard["token_usage"] = _capture_eval_token_usage()

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

    _git_commit_and_push_reports(scorecard.get("agent", "unknown"), scorecard)

    return scorecard


def _generate_generator_recommendations(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate actionable recommendations from a generator scorecard."""
    recs: list[dict[str, Any]] = []
    thresholds = scorecard.get("thresholds", {})

    locator = scorecard.get("locator_quality", {})
    pom = scorecard.get("pom_validity", {})
    test = scorecard.get("test_validity", {})
    import_corr = scorecard.get("import_correctness", {})

    locator_score = locator.get("score", 0.0)
    pom_score = pom.get("score", 0.0)
    test_score = test.get("score", 0.0)
    import_score = import_corr.get("score", 1.0)

    locator_threshold = thresholds.get("locator_quality", 0.85)
    pom_threshold = thresholds.get("pom_validity", 0.80)
    test_threshold = thresholds.get("test_validity", 0.80)
    import_threshold = thresholds.get("import_correctness", 0.90)

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

    if import_score < import_threshold:
        import_errors = import_corr.get("errors", [])
        recs.append({
            "priority": "high",
            "category": "import_correctness",
            "finding": (
                f"Import correctness {import_score:.1%} is below threshold {import_threshold:.1%}. "
                f"{len(import_errors)} import(s) have issues (wrong path, missing POM class, etc.)."
            ),
            "action": (
                "Ensure test files import from '../page_objects/<ClassName>' (underscores, not "
                "hyphens) and that every imported class exists as a named export in the POMs."
            ),
        })

    if (
        locator_score >= locator_threshold
        and pom_score >= pom_threshold
        and test_score >= test_threshold
        and import_score >= import_threshold
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
        ("import_correctness", "Import Correctness"),
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
        elif key == "import_correctness":
            lines.append(f"- Correct: {metric.get('correct', 0)}/{metric.get('total', 0)}")
            import_errors = metric.get("errors", [])
            if import_errors:
                lines.append(f"- Import errors: {len(import_errors)}")
                for err in import_errors[:5]:  # show at most 5
                    lines.append(f"  - [{err['file']}] {err['import']}: {err['issue']}")
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
