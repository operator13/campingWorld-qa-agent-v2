"""Regression detection — compare current scorecard against previous runs."""

from __future__ import annotations

from typing import Any


def detect_regression(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    threshold_delta: float = 0.05,
) -> dict[str, Any]:
    """Compare current scorecard to previous. Returns regression report.

    Args:
        current: Current eval scorecard.
        previous: Previous eval scorecard, or None for first run.
        threshold_delta: Minimum absolute score drop to flag as regression.

    Returns:
        Dict with status, severity, delta, new_failures, recovered.
    """
    if previous is None:
        return {
            "status": "first_run",
            "severity": None,
            "delta": 0.0,
            "previous_score": None,
            "current_score": _extract_score(current),
            "new_failures": [],
            "recovered": [],
            "threshold_delta": threshold_delta,
        }

    current_score = _extract_score(current)
    previous_score = _extract_score(previous)
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

    # Diff the misses lists
    current_misses = _extract_miss_scenarios(current)
    previous_misses = _extract_miss_scenarios(previous)

    new_failures = sorted(current_misses - previous_misses)
    recovered = sorted(previous_misses - current_misses)

    return {
        "status": status,
        "severity": severity,
        "delta": round(delta, 4),
        "previous_score": round(previous_score, 4),
        "current_score": round(current_score, 4),
        "new_failures": new_failures,
        "recovered": recovered,
        "threshold_delta": threshold_delta,
    }


def _extract_score(scorecard: dict[str, Any]) -> float:
    """Extract the triage accuracy score from a scorecard."""
    return scorecard.get("triage_accuracy", {}).get("score", 0.0)


def _extract_miss_scenarios(scorecard: dict[str, Any]) -> set[str]:
    """Extract scenario IDs from the misses list."""
    misses = scorecard.get("triage_accuracy", {}).get("misses", [])
    return {m.get("scenario", m.get("error", "")[:50]) for m in misses}
