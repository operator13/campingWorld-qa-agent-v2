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
from qa_agent.eval.run_eval import score_triage_accuracy
from qa_agent.eval.scorecard import build_scorecard, load_latest_scorecard, save_scorecard
from qa_agent.memory import MemoryStore
from qa_agent.nodes.triage import triage
from qa_agent.schemas.models import RunResult
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
