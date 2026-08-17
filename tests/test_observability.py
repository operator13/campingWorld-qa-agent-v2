"""Tests for observability — alerting and auto-tuning."""

from qa_agent.nodes.metrics import MetricsDB
from qa_agent.observability import (
    CONF_SURE_MAX,
    CONF_SURE_STEP,
    ESCAPE_RATE_ALERT,
    TRIAGE_ACCURACY_ALERT,
    check_alerts,
    compute_recommended_conf_sure,
    run_observability_check,
)


class TestAlerts:
    def test_no_alerts_when_healthy(self, tmp_path):
        db = MetricsDB(tmp_path / "test.db")
        # 10 green runs, no escapes
        for i in range(10):
            db.record_run(
                goal=f"t-{i}", route="/", passed=True,
                failed_cases=[], failure_class=None,
                confidence=0.0, attempts=0, fingerprint=None, outcome="pass",
            )
        alerts = check_alerts(db)
        assert len(alerts) == 0

    def test_escape_rate_alert(self, tmp_path):
        db = MetricsDB(tmp_path / "test.db")
        run_ids = []
        for i in range(10):
            rid = db.record_run(
                goal=f"t-{i}", route="/", passed=True,
                failed_cases=[], failure_class=None,
                confidence=0.0, attempts=0, fingerprint=None, outcome="pass",
            )
            run_ids.append(rid)

        # 2 escapes out of 10 = 20% > 10% threshold
        db.record_escape(run_ids[0], "BUG-1", "/checkout")
        db.record_escape(run_ids[1], "BUG-2", "/login")

        alerts = check_alerts(db)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "escape_rate_high"
        assert alerts[0]["value"] > ESCAPE_RATE_ALERT

    def test_triage_accuracy_alert(self, tmp_path):
        db = MetricsDB(tmp_path / "test.db")
        run_id = db.record_run(
            goal="t", route="/", passed=False,
            failed_cases=["tc-1"], failure_class="unknown",
            confidence=0.5, attempts=0, fingerprint=None, outcome="failed",
        )

        # 6 triage calls: 3 correct, 3 wrong = 50% < 70%
        for i in range(6):
            tid = db.record_triage_call(run_id, "unknown", 0.5)
            db.mark_triage_correctness(tid, i < 3)

        alerts = check_alerts(db)
        assert any(a["type"] == "triage_accuracy_low" for a in alerts)

    def test_no_alert_with_insufficient_data(self, tmp_path):
        """Alerts require minimum sample size."""
        db = MetricsDB(tmp_path / "test.db")
        # Only 2 runs (< 5 minimum)
        for i in range(2):
            rid = db.record_run(
                goal=f"t-{i}", route="/", passed=True,
                failed_cases=[], failure_class=None,
                confidence=0.0, attempts=0, fingerprint=None, outcome="pass",
            )
            db.record_escape(rid, f"BUG-{i}", "/")

        alerts = check_alerts(db)
        assert len(alerts) == 0  # not enough data


class TestAutoTuning:
    def test_no_tuning_with_good_accuracy(self, tmp_path):
        db = MetricsDB(tmp_path / "test.db")
        run_id = db.record_run(
            goal="t", route="/", passed=False,
            failed_cases=["tc-1"], failure_class="locator_drift",
            confidence=0.9, attempts=0, fingerprint=None, outcome="healed",
        )
        # 5 correct out of 5
        for _ in range(5):
            tid = db.record_triage_call(run_id, "locator_drift", 0.9)
            db.mark_triage_correctness(tid, True)

        recommended = compute_recommended_conf_sure(db)
        assert recommended == 0.75  # unchanged

    def test_raises_conf_sure_on_low_accuracy(self, tmp_path):
        db = MetricsDB(tmp_path / "test.db")
        run_id = db.record_run(
            goal="t", route="/", passed=False,
            failed_cases=["tc-1"], failure_class="unknown",
            confidence=0.5, attempts=0, fingerprint=None, outcome="failed",
        )
        # 2 correct out of 6 = 33% < 70%
        for i in range(6):
            tid = db.record_triage_call(run_id, "unknown", 0.5)
            db.mark_triage_correctness(tid, i < 2)

        recommended = compute_recommended_conf_sure(db)
        assert recommended == 0.75 + CONF_SURE_STEP  # raised

    def test_never_exceeds_max(self, tmp_path):
        db = MetricsDB(tmp_path / "test.db")
        run_id = db.record_run(
            goal="t", route="/", passed=False,
            failed_cases=["tc-1"], failure_class="unknown",
            confidence=0.5, attempts=0, fingerprint=None, outcome="failed",
        )
        for i in range(10):
            tid = db.record_triage_call(run_id, "unknown", 0.5)
            db.mark_triage_correctness(tid, False)

        recommended = compute_recommended_conf_sure(db)
        assert recommended <= CONF_SURE_MAX


class TestObservabilityCheck:
    def test_full_report(self, tmp_path):
        db = MetricsDB(tmp_path / "test.db")
        db.record_run(
            goal="t", route="/", passed=True,
            failed_cases=[], failure_class=None,
            confidence=0.0, attempts=0, fingerprint=None, outcome="pass",
        )
        report = run_observability_check(db_path=str(tmp_path / "test.db"))
        assert "dashboard" in report
        assert "alerts" in report
        assert "current_conf_sure" in report
        assert "recommended_conf_sure" in report
        assert isinstance(report["alert_count"], int)
