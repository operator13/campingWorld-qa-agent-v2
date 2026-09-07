"""ECC eval alerting — generate alerts for regressions and cost spikes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegressionAlert:
    """A single alertable event from an ECC eval run."""

    agent: str
    alert_type: str  # "recall_drop" | "threshold_crossed" | "quality_drop" | "cost_spike"
    severity: str  # "warning" | "critical"
    message: str
    current_value: float
    previous_value: float | None = None
    threshold: float | None = None


def check_regression_alerts(
    agent_name: str,
    scorecard: dict[str, Any],
    regression_report: dict[str, Any],
) -> list[RegressionAlert]:
    """Check for alertable regression conditions.

    Returns a list of alerts (may be empty).
    """
    alerts: list[RegressionAlert] = []
    tier = scorecard.get("tier", "detection")

    if regression_report.get("status") == "first_run":
        return alerts

    # 1. Score drop > 5%
    delta = regression_report.get("delta", 0.0)
    if delta < -0.05:
        metric = "recall" if tier == "detection" else "quality"
        severity = "critical" if delta < -0.10 else "warning"
        alerts.append(RegressionAlert(
            agent=agent_name,
            alert_type=f"{metric}_drop",
            severity=severity,
            message=(
                f"{agent_name}: {metric} dropped {abs(delta):.1%} "
                f"({regression_report.get('previous_score', 0):.1%} → "
                f"{regression_report.get('current_score', 0):.1%})"
            ),
            current_value=regression_report.get("current_score", 0.0),
            previous_value=regression_report.get("previous_score"),
            threshold=None,
        ))

    # 2. Threshold crossed
    if regression_report.get("threshold_crossed", False):
        thresholds = scorecard.get("thresholds", {})
        metric = "recall" if tier == "detection" else "quality"
        threshold_val = thresholds.get(metric, 0.75 if tier == "detection" else 0.70)
        current_score = regression_report.get("current_score", 0.0)
        alerts.append(RegressionAlert(
            agent=agent_name,
            alert_type="threshold_crossed",
            severity="critical",
            message=(
                f"{agent_name}: {metric} ({current_score:.1%}) is below "
                f"threshold ({threshold_val:.1%})"
            ),
            current_value=current_score,
            threshold=threshold_val,
        ))

    # 3. New failures appeared
    new_failures = regression_report.get("new_failures", [])
    if new_failures:
        alerts.append(RegressionAlert(
            agent=agent_name,
            alert_type="new_failures",
            severity="warning",
            message=(
                f"{agent_name}: {len(new_failures)} new missed issue(s): "
                f"{', '.join(new_failures[:5])}"
                + ("..." if len(new_failures) > 5 else "")
            ),
            current_value=len(new_failures),
        ))

    return alerts


def check_cost_alerts(
    agent_name: str,
    cost_trend: dict[str, Any],
) -> list[RegressionAlert]:
    """Check for cost spike alerts.

    Returns a list of alerts (may be empty).
    """
    alerts: list[RegressionAlert] = []

    if cost_trend.get("alert", False):
        alerts.append(RegressionAlert(
            agent=agent_name,
            alert_type="cost_spike",
            severity="warning",
            message=(
                f"{agent_name}: cost spike — ${cost_trend.get('current_cost', 0):.2f} "
                f"vs avg ${cost_trend.get('avg_cost', 0):.2f} "
                f"({cost_trend.get('percent_change', 0):+.0f}%)"
            ),
            current_value=cost_trend.get("current_cost", 0.0),
            previous_value=cost_trend.get("avg_cost"),
        ))

    return alerts


def format_alerts_console(alerts: list[RegressionAlert]) -> str:
    """Format alerts for CLI console output."""
    if not alerts:
        return ""

    lines: list[str] = ["\n⚠ REGRESSION ALERTS:"]
    for alert in alerts:
        icon = "🔴" if alert.severity == "critical" else "🟡"
        lines.append(f"  {icon} [{alert.severity.upper()}] {alert.message}")
    return "\n".join(lines)


def format_alerts_ci(alerts: list[RegressionAlert]) -> str:
    """Format alerts as GitHub Actions annotations."""
    lines: list[str] = []
    for alert in alerts:
        level = "error" if alert.severity == "critical" else "warning"
        lines.append(f"::{level}::{alert.message}")
    return "\n".join(lines)
