"""Defect Report — terminal node that files a bug and stops the loop.

Logs to console AND files a deduped Jira ticket (when Jira is configured).
"""

from __future__ import annotations

import logging
from typing import Any

from qa_agent.state import QAState
from qa_agent.surfaces.jira_defect import JiraDefectSurface, compute_fingerprint

logger = logging.getLogger(__name__)


async def defect_report(state: QAState) -> dict:
    """Package a real failure as a bug report and stop the loop."""
    logger.info("Defect Report: filing bug for goal=%r", state.goal)

    report = _build_report(state)

    # Always log to console
    _log_report(report)

    # Try to file a Jira ticket (gracefully degrades if Jira not configured)
    jira_result = await _file_jira(state, report)

    error_msg = f"DEFECT: {report.get('error', 'Unknown error')}"
    if jira_result and jira_result.get("issue_key"):
        error_msg += f" [Jira: {jira_result['issue_key']}]"

    return {"error": error_msg}


async def _file_jira(state: QAState, report: dict[str, Any]) -> dict[str, Any] | None:
    """Attempt to file or dedup a Jira ticket. Returns None if Jira not configured."""
    jira = JiraDefectSurface()

    # Determine route from the first failed test case or goal
    route = "/"
    if state.plan:
        route = state.plan[0].route

    try:
        result = await jira.file_or_dedup(
            goal=state.goal,
            route=route,
            failure_class=report["failure_class"],
            confidence=report["confidence"],
            error=report.get("error", ""),
            run_results=state.run_results,
            attempts=report["attempts"],
        )
        if result["action"] == "created":
            logger.info("Defect Report: created Jira ticket %s", result["issue_key"])
        elif result["action"] == "deduped":
            logger.info("Defect Report: duplicate — existing ticket %s", result["issue_key"])
        else:
            logger.warning("Defect Report: failed to create Jira ticket")
        return result
    except Exception as e:
        logger.error("Defect Report: Jira filing failed: %s", e)
        return None


def _log_report(report: dict[str, Any]) -> None:
    """Log the defect report to console."""
    logger.warning("=" * 60)
    logger.warning("DEFECT REPORT")
    logger.warning("=" * 60)
    logger.warning("Goal: %s", report["goal"])
    logger.warning("Failure class: %s (confidence: %.2f)",
                    report["failure_class"], report["confidence"])
    logger.warning("Fingerprint: %s", report.get("fingerprint", "n/a"))
    logger.warning("Attempts: %d", report["attempts"])
    if report.get("error"):
        logger.warning("Error: %s", report["error"][:500])
    if report.get("failed_cases"):
        logger.warning("Failed cases: %s", ", ".join(report["failed_cases"]))
    logger.warning("=" * 60)


def _build_report(state: QAState) -> dict[str, Any]:
    """Build a structured defect report from state."""
    failed_cases = state.run_results.failed_cases if state.run_results else []
    route = state.plan[0].route if state.plan else "/"

    fingerprint = compute_fingerprint(
        route=route,
        error_class=state.failure_class or "unknown",
        failed_cases=failed_cases,
    )

    report: dict[str, Any] = {
        "goal": state.goal,
        "failure_class": state.failure_class or "unknown",
        "confidence": state.confidence,
        "attempts": state.attempts,
        "error": state.error,
        "fingerprint": fingerprint,
        "failed_cases": failed_cases,
        "screenshots": [],
    }

    if state.run_results:
        report["logs"] = state.run_results.logs[:3000]
        report["screenshots"] = state.run_results.screenshots

    return report
