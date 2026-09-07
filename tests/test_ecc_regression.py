"""Tests for ECC regression detection, alerts, and cost tracking."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from qa_agent.eval.ecc.alerts import (
    RegressionAlert,
    check_cost_alerts,
    check_regression_alerts,
    format_alerts_ci,
    format_alerts_console,
)
from qa_agent.eval.ecc.cost_tracker import (
    compute_cost_trend,
    estimate_cost_from_tokens,
    load_recent_reports,
)
from qa_agent.eval.ecc.ecc_regression import (
    detect_ecc_regression,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _detection_scorecard(
    recall: float = 0.90,
    recall_threshold: float = 0.90,
    scenarios: list | None = None,
    token_estimate: int = 5000,
) -> dict:
    return {
        "agent": "security-reviewer",
        "tier": "detection",
        "timestamp": "2026-09-07T00:00:00+00:00",
        "scores": {"recall": recall, "precision": 0.80, "false_positive_rate": 0.10},
        "thresholds": {"recall": recall_threshold, "precision": 0.80},
        "passed": recall >= recall_threshold,
        "token_estimate": token_estimate,
        "scenarios": scenarios or [],
    }


def _generative_scorecard(
    quality: float = 0.85,
    quality_threshold: float = 0.70,
    scenarios: list | None = None,
    token_estimate: int = 3000,
) -> dict:
    return {
        "agent": "planner-ecc",
        "tier": "generative",
        "timestamp": "2026-09-07T00:00:00+00:00",
        "scores": {"quality": quality, "per_scenario": [quality]},
        "thresholds": {"quality": quality_threshold},
        "passed": quality >= quality_threshold,
        "token_estimate": token_estimate,
        "scenarios": scenarios or [],
    }


# ===========================================================================
# ECC Regression Detection
# ===========================================================================


class TestDetectEccRegression:
    def test_first_run(self):
        current = _detection_scorecard(recall=0.95)
        result = detect_ecc_regression(current, None)
        assert result["status"] == "first_run"
        assert result["current_score"] == 0.95
        assert result["previous_score"] is None
        assert result["delta"] == 0.0

    def test_stable_detection(self):
        previous = _detection_scorecard(recall=0.90)
        current = _detection_scorecard(recall=0.88)
        result = detect_ecc_regression(current, previous)
        assert result["status"] == "stable"
        assert result["severity"] is None

    def test_minor_regression_detection(self):
        previous = _detection_scorecard(recall=0.90)
        current = _detection_scorecard(recall=0.83)
        result = detect_ecc_regression(current, previous)
        assert result["status"] == "regression"
        assert result["severity"] == "minor"
        assert result["delta"] == pytest.approx(-0.07, abs=0.01)

    def test_major_regression_detection(self):
        previous = _detection_scorecard(recall=0.95)
        current = _detection_scorecard(recall=0.80)
        result = detect_ecc_regression(current, previous)
        assert result["status"] == "regression"
        assert result["severity"] == "major"

    def test_improvement_detection(self):
        previous = _detection_scorecard(recall=0.80)
        current = _detection_scorecard(recall=0.95)
        result = detect_ecc_regression(current, previous)
        assert result["status"] == "improvement"
        assert result["severity"] is None

    def test_threshold_crossed(self):
        current = _detection_scorecard(recall=0.85, recall_threshold=0.90)
        result = detect_ecc_regression(current, None)
        assert result["threshold_crossed"] is True

    def test_threshold_not_crossed(self):
        current = _detection_scorecard(recall=0.95, recall_threshold=0.90)
        result = detect_ecc_regression(current, None)
        assert result["threshold_crossed"] is False

    def test_generative_regression(self):
        previous = _generative_scorecard(quality=0.90)
        current = _generative_scorecard(quality=0.78)
        result = detect_ecc_regression(current, previous)
        assert result["status"] == "regression"
        assert result["severity"] == "major"

    def test_detection_miss_diff(self):
        prev_scenarios = [
            {"scenario_id": "sec_001", "missed": ["sqli_1"]},
            {"scenario_id": "sec_002", "missed": []},
        ]
        curr_scenarios = [
            {"scenario_id": "sec_001", "missed": []},
            {"scenario_id": "sec_002", "missed": ["xss_1"]},
        ]
        previous = _detection_scorecard(recall=0.90, scenarios=prev_scenarios)
        current = _detection_scorecard(recall=0.90, scenarios=curr_scenarios)
        result = detect_ecc_regression(current, previous)
        assert "sec_002:xss_1" in result["new_failures"]
        assert "sec_001:sqli_1" in result["recovered"]

    def test_generative_failure_diff(self):
        prev_scenarios = [
            {"scenario_id": "plan_001", "quality_score": 0.30},
            {"scenario_id": "plan_002", "quality_score": 0.80},
        ]
        curr_scenarios = [
            {"scenario_id": "plan_001", "quality_score": 0.80},
            {"scenario_id": "plan_002", "quality_score": 0.30},
        ]
        previous = _generative_scorecard(quality=0.55, scenarios=prev_scenarios)
        current = _generative_scorecard(quality=0.55, scenarios=curr_scenarios)
        result = detect_ecc_regression(current, previous)
        assert "plan_002" in result["new_failures"]
        assert "plan_001" in result["recovered"]


# ===========================================================================
# Alerts
# ===========================================================================


class TestAlerts:
    def test_no_alerts_on_stable(self):
        scorecard = _detection_scorecard(recall=0.95)
        regression = {"status": "stable", "delta": -0.01, "threshold_crossed": False, "new_failures": []}
        alerts = check_regression_alerts("security-reviewer", scorecard, regression)
        assert alerts == []

    def test_alert_on_recall_drop(self):
        scorecard = _detection_scorecard(recall=0.82)
        regression = {
            "status": "regression",
            "delta": -0.08,
            "current_score": 0.82,
            "previous_score": 0.90,
            "threshold_crossed": False,
            "new_failures": [],
        }
        alerts = check_regression_alerts("security-reviewer", scorecard, regression)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "recall_drop"
        assert alerts[0].severity == "warning"

    def test_critical_on_large_drop(self):
        scorecard = _detection_scorecard(recall=0.75)
        regression = {
            "status": "regression",
            "delta": -0.15,
            "current_score": 0.75,
            "previous_score": 0.90,
            "threshold_crossed": True,
            "new_failures": [],
        }
        alerts = check_regression_alerts("security-reviewer", scorecard, regression)
        types = {a.alert_type for a in alerts}
        assert "recall_drop" in types
        assert "threshold_crossed" in types
        assert any(a.severity == "critical" for a in alerts)

    def test_alert_on_threshold_crossed(self):
        scorecard = _detection_scorecard(recall=0.85, recall_threshold=0.90)
        regression = {
            "status": "stable",
            "delta": 0.0,
            "threshold_crossed": True,
            "new_failures": [],
        }
        alerts = check_regression_alerts("security-reviewer", scorecard, regression)
        assert any(a.alert_type == "threshold_crossed" for a in alerts)

    def test_no_alerts_on_first_run(self):
        scorecard = _detection_scorecard(recall=0.95)
        regression = {"status": "first_run"}
        alerts = check_regression_alerts("security-reviewer", scorecard, regression)
        assert alerts == []

    def test_cost_alert(self):
        cost_trend = {"alert": True, "current_cost": 1.50, "avg_cost": 0.50, "percent_change": 200}
        alerts = check_cost_alerts("security-reviewer", cost_trend)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "cost_spike"

    def test_no_cost_alert(self):
        cost_trend = {"alert": False, "current_cost": 0.50, "avg_cost": 0.48, "percent_change": 4}
        alerts = check_cost_alerts("security-reviewer", cost_trend)
        assert alerts == []

    def test_format_console(self):
        alerts = [
            RegressionAlert(
                agent="security-reviewer",
                alert_type="recall_drop",
                severity="warning",
                message="test message",
                current_value=0.82,
            ),
        ]
        output = format_alerts_console(alerts)
        assert "REGRESSION ALERTS" in output
        assert "test message" in output

    def test_format_console_empty(self):
        assert format_alerts_console([]) == ""

    def test_format_ci(self):
        alerts = [
            RegressionAlert(
                agent="security-reviewer",
                alert_type="threshold_crossed",
                severity="critical",
                message="below threshold",
                current_value=0.70,
            ),
        ]
        output = format_alerts_ci(alerts)
        assert "::error::below threshold" in output


# ===========================================================================
# Cost Tracker
# ===========================================================================


class TestCostTracker:
    def test_estimate_cost_from_tokens(self):
        cost = estimate_cost_from_tokens(10000)
        assert cost > 0
        assert cost < 1.0

    def test_no_data(self):
        with patch("qa_agent.eval.ecc.cost_tracker.REPORTS_DIR", Path("/nonexistent")):
            trend = compute_cost_trend("security-reviewer")
        assert trend["trend"] == "no_data"
        assert trend["alert"] is False

    def test_cost_trend_stable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent_dir = Path(tmpdir) / "security-reviewer"
            agent_dir.mkdir()
            for i in range(5):
                report = {"token_estimate": 5000, "timestamp": f"2026-09-0{i+1}T00:00:00Z"}
                (agent_dir / f"2026090{i+1}-000000.json").write_text(json.dumps(report))

            with patch("qa_agent.eval.ecc.cost_tracker.REPORTS_DIR", Path(tmpdir)):
                trend = compute_cost_trend("security-reviewer")

            assert trend["trend"] == "stable"
            assert trend["alert"] is False

    def test_cost_trend_spike(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent_dir = Path(tmpdir) / "security-reviewer"
            agent_dir.mkdir()
            # Previous runs: low tokens
            for i in range(4):
                report = {"token_estimate": 1000, "timestamp": f"2026-09-0{i+1}T00:00:00Z"}
                (agent_dir / f"2026090{i+1}-000000.json").write_text(json.dumps(report))
            # Current run: high tokens
            report = {"token_estimate": 50000, "timestamp": "2026-09-05T00:00:00Z"}
            (agent_dir / "20260905-000000.json").write_text(json.dumps(report))

            with patch("qa_agent.eval.ecc.cost_tracker.REPORTS_DIR", Path(tmpdir)):
                trend = compute_cost_trend("security-reviewer")

            assert trend["trend"] == "increasing"
            assert trend["alert"] is True

    def test_load_recent_reports_empty(self):
        with patch("qa_agent.eval.ecc.cost_tracker.REPORTS_DIR", Path("/nonexistent")):
            reports = load_recent_reports("security-reviewer")
        assert reports == []

    def test_load_recent_reports_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            agent_dir = Path(tmpdir) / "test-agent"
            agent_dir.mkdir()
            for i in range(15):
                report = {"token_estimate": 1000, "index": i}
                (agent_dir / f"2026090{i:02d}-000000.json").write_text(json.dumps(report))

            with patch("qa_agent.eval.ecc.cost_tracker.REPORTS_DIR", Path(tmpdir)):
                reports = load_recent_reports("test-agent", lookback=5)

            assert len(reports) == 5
