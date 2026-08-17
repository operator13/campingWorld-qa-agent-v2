"""Table-driven tests for the routing functions.

Covers every (failure_class, confidence, attempts) combination to ensure
the routers return the correct next node.
"""

import pytest

from qa_agent.graph import route_after_execute, route_after_triage
from qa_agent.schemas.models import RunResult
from qa_agent.state import QAState


# ---------------------------------------------------------------------------
# route_after_execute — pass → metrics, fail → triage
# ---------------------------------------------------------------------------

class TestRouteAfterExecute:
    def test_pass_goes_to_metrics(self):
        state = QAState(
            goal="test",
            run_results=RunResult(passed=True, failed_cases=[], logs="ok"),
        )
        assert route_after_execute(state) == "metrics"

    def test_fail_goes_to_triage(self):
        state = QAState(
            goal="test",
            run_results=RunResult(passed=False, failed_cases=["tc-1"], logs="fail"),
        )
        assert route_after_execute(state) == "triage"

    def test_no_results_goes_to_triage(self):
        state = QAState(goal="test")
        assert route_after_execute(state) == "triage"


# ---------------------------------------------------------------------------
# route_after_triage — the confidence-gated fan-out
# ---------------------------------------------------------------------------

class TestRouteAfterTriage:
    """Table-driven: every combo of (failure_class, confidence, attempts)."""

    @pytest.mark.parametrize(
        "failure_class, confidence, attempts, expected",
        [
            # --- MAX_ATTEMPTS reached: always defect_report ---
            ("locator_drift", 0.95, 3, "defect_report"),
            ("app_defect",    0.95, 3, "defect_report"),
            ("unknown",       0.50, 3, "defect_report"),
            ("locator_drift", 0.50, 4, "defect_report"),

            # --- Low confidence (< 0.75): always human_review ---
            ("locator_drift", 0.60, 0, "human_review"),
            ("app_defect",    0.50, 1, "human_review"),
            ("unknown",       0.30, 0, "human_review"),
            ("locator_drift", 0.74, 2, "human_review"),

            # --- Sure drift (>= 0.75): healer ---
            ("locator_drift", 0.75, 0, "healer"),
            ("locator_drift", 0.90, 1, "healer"),
            ("locator_drift", 1.00, 2, "healer"),

            # --- Sure bug (>= 0.75): defect_report ---
            ("app_defect",    0.80, 0, "defect_report"),
            ("app_defect",    0.95, 1, "defect_report"),
            ("unknown",       0.80, 0, "defect_report"),
        ],
        ids=[
            "max_attempts_drift",
            "max_attempts_bug",
            "max_attempts_unknown",
            "max_attempts_exceeded",
            "low_conf_drift",
            "low_conf_bug",
            "low_conf_unknown",
            "low_conf_edge_074",
            "sure_drift_075",
            "sure_drift_090",
            "sure_drift_100",
            "sure_bug_080",
            "sure_bug_095",
            "sure_unknown_080",
        ],
    )
    def test_routing(self, failure_class, confidence, attempts, expected):
        state = QAState(
            goal="test",
            failure_class=failure_class,
            confidence=confidence,
            attempts=attempts,
        )
        assert route_after_triage(state) == expected

    def test_boundary_conf_sure_exactly(self):
        """Confidence exactly at CONF_SURE (0.75) is treated as 'sure'."""
        state = QAState(
            goal="test",
            failure_class="locator_drift",
            confidence=0.75,
            attempts=0,
        )
        assert route_after_triage(state) == "healer"

    def test_boundary_max_attempts_exactly(self):
        """Attempts exactly at MAX_ATTEMPTS (3) triggers defect_report."""
        state = QAState(
            goal="test",
            failure_class="locator_drift",
            confidence=0.95,
            attempts=3,
        )
        assert route_after_triage(state) == "defect_report"

    def test_max_attempts_overrides_confidence(self):
        """MAX_ATTEMPTS takes priority over high confidence."""
        state = QAState(
            goal="test",
            failure_class="locator_drift",
            confidence=1.0,
            attempts=3,
        )
        assert route_after_triage(state) == "defect_report"

    def test_low_confidence_overrides_failure_class(self):
        """Low confidence routes to human_review regardless of failure_class."""
        for fc in ("locator_drift", "app_defect", "unknown"):
            state = QAState(
                goal="test",
                failure_class=fc,
                confidence=0.5,
                attempts=0,
            )
            assert route_after_triage(state) == "human_review", f"Failed for {fc}"
