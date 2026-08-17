"""Observability — escape-rate alerting and automatic threshold tuning.

Monitors the metrics DB and adjusts CONF_SURE when Triage accuracy drops,
routing more cases to human review to maintain safety.
"""

from __future__ import annotations

import logging
from typing import Any

from qa_agent.config import CONF_SURE
from qa_agent.nodes.metrics import MetricsDB

logger = logging.getLogger(__name__)

# Alert thresholds
ESCAPE_RATE_ALERT = 0.10     # alert if escape rate exceeds 10%
TRIAGE_ACCURACY_ALERT = 0.70  # alert if triage accuracy drops below 70%
CONF_SURE_STEP = 0.05        # how much to raise CONF_SURE per tuning cycle
CONF_SURE_MAX = 0.95          # never raise above this


class AlertFired(Exception):
    """Raised when a metrics alert condition is met."""


def check_alerts(db: MetricsDB) -> list[dict[str, Any]]:
    """Check for alert conditions. Returns a list of fired alerts."""
    alerts: list[dict[str, Any]] = []

    escape = db.compute_escape_rate()
    if escape["escape_rate"] > ESCAPE_RATE_ALERT and escape["total_green_runs"] >= 5:
        alerts.append({
            "type": "escape_rate_high",
            "message": (
                f"Escape rate {escape['escape_rate']:.1%} exceeds threshold "
                f"{ESCAPE_RATE_ALERT:.1%} ({escape['escapes']}/{escape['total_green_runs']} runs)"
            ),
            "value": escape["escape_rate"],
            "threshold": ESCAPE_RATE_ALERT,
        })

    accuracy = db.compute_triage_accuracy()
    if (accuracy["accuracy"] < TRIAGE_ACCURACY_ALERT
            and accuracy["total_audited"] >= 5):
        alerts.append({
            "type": "triage_accuracy_low",
            "message": (
                f"Triage accuracy {accuracy['accuracy']:.1%} below threshold "
                f"{TRIAGE_ACCURACY_ALERT:.1%} ({accuracy['correct']}/{accuracy['total_audited']} calls)"
            ),
            "value": accuracy["accuracy"],
            "threshold": TRIAGE_ACCURACY_ALERT,
        })

    for alert in alerts:
        logger.warning("ALERT: %s", alert["message"])

    return alerts


def compute_recommended_conf_sure(db: MetricsDB) -> float:
    """Compute a recommended CONF_SURE based on current Triage accuracy.

    If accuracy is low, raise CONF_SURE to send more cases to human review.
    If accuracy is high, keep the current value (never lower automatically).
    """
    accuracy = db.compute_triage_accuracy()
    current = CONF_SURE

    if accuracy["total_audited"] < 5:
        # Not enough data to tune
        return current

    if accuracy["accuracy"] < TRIAGE_ACCURACY_ALERT:
        # Accuracy below alert threshold — raise CONF_SURE
        recommended = min(current + CONF_SURE_STEP, CONF_SURE_MAX)
        logger.info(
            "Auto-tune: accuracy %.1%% < %.1%% → recommend CONF_SURE %.2f → %.2f",
            accuracy["accuracy"], TRIAGE_ACCURACY_ALERT, current, recommended,
        )
        return recommended

    return current


def run_observability_check(db_path: str | None = None) -> dict[str, Any]:
    """Run a full observability check: dashboard, alerts, and tuning recommendation.

    Returns a report dict suitable for logging or dashboard display.
    """
    db = MetricsDB(db_path=db_path) if db_path else MetricsDB()
    dashboard = db.get_dashboard()
    alerts = check_alerts(db)
    recommended_conf = compute_recommended_conf_sure(db)

    return {
        "dashboard": dashboard,
        "alerts": alerts,
        "alert_count": len(alerts),
        "current_conf_sure": CONF_SURE,
        "recommended_conf_sure": recommended_conf,
        "needs_tuning": recommended_conf != CONF_SURE,
    }
