"""Scorecard — build, save, and load eval scorecards as timestamped JSON."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def build_scorecard(
    eval_result: dict[str, Any],
    *,
    run_id: str,
    agent: str,
    baseline_mode: bool,
    thresholds: dict[str, float],
    regression_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the final scorecard dict from raw eval results."""
    accuracy = eval_result.get("triage_accuracy", {})
    misses = accuracy.get("misses", [])
    score = accuracy.get("score", 0.0)

    # Per-category breakdown
    by_category = _compute_category_breakdown(eval_result.get("scenarios", []), misses)

    # Pass/fail determination
    passed = None if baseline_mode else (score >= thresholds.get("triage_accuracy", 0.75))

    return {
        "eval_run_id": run_id,
        "agent": agent,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "baseline_mode": baseline_mode,
        "scenarios_total": accuracy.get("total", 0),
        "scenarios_skipped_expired": eval_result.get("skipped_expired", 0),
        "triage_accuracy": {
            "score": round(score, 4),
            "correct": accuracy.get("correct", 0),
            "total": accuracy.get("total", 0),
            "misses": misses,
        },
        "by_category": by_category,
        "thresholds": thresholds,
        "passed": passed,
        "regression_vs_previous": regression_report,
    }


def save_scorecard(scorecard: dict[str, Any], reports_dir: Path | None = None) -> Path:
    """Write scorecard to a timestamped JSON file inside an agent subfolder."""
    base = reports_dir or _REPORTS_DIR
    agent = scorecard.get("agent", "unknown")
    dest = base / agent
    dest.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"{ts}.json"
    filepath = dest / filename

    filepath.write_text(json.dumps(scorecard, indent=2, default=str))
    logger.info("Scorecard written to %s", filepath)
    return filepath


def load_latest_scorecard(agent: str, reports_dir: Path | None = None) -> dict[str, Any] | None:
    """Load the most recent previous scorecard for a given agent."""
    base = reports_dir or _REPORTS_DIR
    dest = base / agent
    if not dest.exists():
        return None

    files = sorted(dest.glob("*.json"), reverse=True)
    if not files:
        return None

    try:
        return json.loads(files[0].read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load previous scorecard %s: %s", files[0], e)
        return None


def _compute_category_breakdown(
    scenarios: list[dict[str, Any]], misses: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Compute per-category accuracy from scenarios and misses."""
    categories: dict[str, dict[str, int]] = {}

    # Count totals per category
    for s in scenarios:
        cat = s.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"total": 0, "correct": 0}
        categories[cat]["total"] += 1
        categories[cat]["correct"] += 1  # assume correct, subtract misses below

    # Subtract misses
    miss_scenarios = {m.get("scenario", "") for m in misses}
    for s in scenarios:
        if s.get("scenario") in miss_scenarios:
            cat = s.get("category", "unknown")
            categories[cat]["correct"] -= 1

    # Compute scores
    result = {}
    for cat, data in sorted(categories.items()):
        total = data["total"]
        correct = data["correct"]
        result[cat] = {
            "score": round(correct / total, 4) if total > 0 else 0.0,
            "correct": correct,
            "total": total,
        }

    return result
