"""ECC regression detection — compare current ECC scorecard against previous runs."""

from __future__ import annotations

from typing import Any


def detect_ecc_regression(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    threshold_delta: float = 0.05,
) -> dict[str, Any]:
    """Compare current ECC scorecard to previous. Returns regression report.

    Handles both detection-tier (recall-based) and generative-tier (quality-based)
    scorecards by dispatching on the ``tier`` field.

    Args:
        current: Current ECC eval scorecard.
        previous: Previous ECC eval scorecard, or None for first run.
        threshold_delta: Minimum absolute score drop to flag as regression (5%).

    Returns:
        Dict with status, severity, delta, new_failures, recovered, threshold_crossed.
    """
    tier = current.get("tier", "detection")
    current_score = _extract_primary_score(current)

    if previous is None:
        return {
            "status": "first_run",
            "severity": None,
            "delta": 0.0,
            "previous_score": None,
            "current_score": round(current_score, 4),
            "new_failures": [],
            "recovered": [],
            "threshold_crossed": _check_threshold_crossed(current),
            "threshold_delta": threshold_delta,
        }

    previous_score = _extract_primary_score(previous)
    delta = current_score - previous_score

    # Determine severity
    if delta < -0.10:
        severity = "major"
    elif delta < -threshold_delta:
        severity = "minor"
    else:
        severity = None

    # Determine status
    if delta < -threshold_delta:
        status = "regression"
    elif delta <= threshold_delta:
        status = "stable"
    else:
        status = "improvement"

    # Diff missed issues/scenarios between runs
    if tier == "detection":
        new_failures, recovered = _diff_detection_misses(current, previous)
    else:
        new_failures, recovered = _diff_generative_failures(current, previous)

    return {
        "status": status,
        "severity": severity,
        "delta": round(delta, 4),
        "previous_score": round(previous_score, 4),
        "current_score": round(current_score, 4),
        "new_failures": new_failures,
        "recovered": recovered,
        "threshold_crossed": _check_threshold_crossed(current),
        "threshold_delta": threshold_delta,
    }


def _extract_primary_score(scorecard: dict[str, Any]) -> float:
    """Extract the primary metric from an ECC scorecard.

    Detection tier: scores.recall
    Generative tier: scores.quality
    """
    tier = scorecard.get("tier", "detection")
    scores = scorecard.get("scores", {})
    if tier == "detection":
        return scores.get("recall", 0.0)
    return scores.get("quality", 0.0)


def _check_threshold_crossed(scorecard: dict[str, Any]) -> bool:
    """Check if the current score is below the configured threshold."""
    tier = scorecard.get("tier", "detection")
    scores = scorecard.get("scores", {})
    thresholds = scorecard.get("thresholds", {})

    if tier == "detection":
        return scores.get("recall", 0.0) < thresholds.get("recall", 0.75)
    return scores.get("quality", 0.0) < thresholds.get("quality", 0.70)


def _diff_detection_misses(
    current: dict[str, Any],
    previous: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Diff missed issue IDs between two detection-tier scorecards."""
    current_misses = _collect_detection_misses(current)
    previous_misses = _collect_detection_misses(previous)

    new_failures = sorted(current_misses - previous_misses)
    recovered = sorted(previous_misses - current_misses)
    return new_failures, recovered


def _collect_detection_misses(scorecard: dict[str, Any]) -> set[str]:
    """Collect all missed issue IDs from a detection scorecard's scenarios."""
    misses: set[str] = set()
    for scenario in scorecard.get("scenarios", []):
        for missed_id in scenario.get("missed", []):
            sid = scenario.get("scenario_id", "unknown")
            misses.add(f"{sid}:{missed_id}")
    return misses


def _diff_generative_failures(
    current: dict[str, Any],
    previous: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Diff low-quality scenarios between two generative-tier scorecards.

    A scenario is a "failure" if its quality_score < 0.50.
    """
    quality_cutoff = 0.50
    current_failures = _collect_generative_failures(current, quality_cutoff)
    previous_failures = _collect_generative_failures(previous, quality_cutoff)

    new_failures = sorted(current_failures - previous_failures)
    recovered = sorted(previous_failures - current_failures)
    return new_failures, recovered


def _collect_generative_failures(
    scorecard: dict[str, Any],
    cutoff: float,
) -> set[str]:
    """Collect scenario IDs with quality_score below cutoff."""
    failures: set[str] = set()
    for scenario in scorecard.get("scenarios", []):
        quality = scenario.get("quality_score", 1.0)
        if quality < cutoff:
            failures.add(scenario.get("scenario_id", "unknown"))
    return failures
