"""ECC eval cost tracking — compute cost trends from report history."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from qa_agent.eval.ecc.config import ALL_ECC_AGENTS, BUDGET_CAPS, REPORTS_DIR

logger = logging.getLogger(__name__)

# Token-to-cost approximation (Sonnet 4 pricing)
INPUT_COST_PER_1K = 0.003
OUTPUT_COST_PER_1K = 0.015
TOKENS_PER_ESTIMATE_RATIO = 0.6  # rough input/output split


def estimate_cost_from_tokens(token_estimate: int) -> float:
    """Estimate USD cost from a token count using blended Sonnet pricing."""
    input_tokens = token_estimate * TOKENS_PER_ESTIMATE_RATIO
    output_tokens = token_estimate * (1 - TOKENS_PER_ESTIMATE_RATIO)
    cost = (input_tokens / 1000) * INPUT_COST_PER_1K + (output_tokens / 1000) * OUTPUT_COST_PER_1K
    return round(cost, 4)


def load_recent_reports(agent_name: str, *, lookback: int = 10) -> list[dict[str, Any]]:
    """Load the most recent N reports for an agent, newest first."""
    agent_dir = REPORTS_DIR / agent_name
    if not agent_dir.exists():
        return []

    report_files = sorted(agent_dir.glob("*.json"), reverse=True)[:lookback]
    reports: list[dict[str, Any]] = []
    for path in report_files:
        try:
            with open(path) as f:
                reports.append(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load report %s: %s", path, e)
    return reports


def compute_cost_trend(agent_name: str, *, lookback: int = 10) -> dict[str, Any]:
    """Compute cost trend from recent reports for a single agent.

    Returns:
        Dict with current_cost, avg_cost, trend, percent_change, history, alert.
    """
    reports = load_recent_reports(agent_name, lookback=lookback)
    if not reports:
        return {
            "agent": agent_name,
            "current_cost": 0.0,
            "avg_cost": 0.0,
            "trend": "no_data",
            "percent_change": 0.0,
            "history": [],
            "alert": False,
        }

    history: list[dict[str, Any]] = []
    for report in reports:
        tokens = report.get("token_estimate", 0)
        cost = estimate_cost_from_tokens(tokens)
        history.append({
            "timestamp": report.get("timestamp", ""),
            "tokens": tokens,
            "cost": cost,
        })

    current_cost = history[0]["cost"]

    # Average of previous runs (excluding current)
    if len(history) > 1:
        prev_costs = [h["cost"] for h in history[1:]]
        avg_cost = sum(prev_costs) / len(prev_costs)
    else:
        avg_cost = current_cost

    # Trend direction
    if avg_cost == 0:
        percent_change = 0.0
        trend = "stable"
    else:
        percent_change = ((current_cost - avg_cost) / avg_cost) * 100
        if percent_change > 20:
            trend = "increasing"
        elif percent_change < -20:
            trend = "decreasing"
        else:
            trend = "stable"

    # Alert if cost increased >50% over rolling average
    alert = percent_change > 50 and len(history) > 1
    budget_cap = BUDGET_CAPS.get(agent_name, 1.00)
    if current_cost > budget_cap:
        alert = True

    return {
        "agent": agent_name,
        "current_cost": round(current_cost, 4),
        "avg_cost": round(avg_cost, 4),
        "trend": trend,
        "percent_change": round(percent_change, 1),
        "budget_cap": budget_cap,
        "budget_exceeded": current_cost > budget_cap,
        "history": history,
        "alert": alert,
    }


def compute_all_agents_cost_summary() -> dict[str, Any]:
    """Aggregate cost data across all ECC agents.

    Returns a summary dict suitable for the dashboard cost odometer.
    """
    agent_trends: dict[str, dict[str, Any]] = {}
    total_current = 0.0
    total_budget = 0.0
    alerts_count = 0

    for agent_name in ALL_ECC_AGENTS:
        trend = compute_cost_trend(agent_name)
        agent_trends[agent_name] = trend
        total_current += trend["current_cost"]
        total_budget += trend["budget_cap"]
        if trend["alert"]:
            alerts_count += 1

    return {
        "total_current_cost": round(total_current, 4),
        "total_budget_cap": round(total_budget, 2),
        "budget_utilization": round(total_current / total_budget * 100, 1) if total_budget else 0.0,
        "agents_with_alerts": alerts_count,
        "agents": agent_trends,
    }
