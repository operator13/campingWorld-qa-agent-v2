"""Tests for the Metrics node and MetricsDB."""

from __future__ import annotations

import pytest

from qa_agent.nodes.metrics import MetricsDB, metrics
from qa_agent.schemas.models import RunResult
from qa_agent.state import QAState


@pytest.fixture
def db(tmp_path):
    """Create a fresh MetricsDB in a temp directory."""
    return MetricsDB(db_path=tmp_path / "test_metrics.db")


class TestMetricsDB:
    def test_record_and_retrieve_run(self, db):
        """Can record a run and compute stats."""
        run_id = db.record_run(
            goal="test checkout",
            route="/checkout",
            passed=True,
            failed_cases=[],
            failure_class=None,
            confidence=0.0,
            attempts=0,
            fingerprint=None,
            outcome="pass",
        )
        assert run_id >= 1

        stats = db.compute_escape_rate()
        assert stats["total_green_runs"] == 1
        assert stats["escapes"] == 0
        assert stats["escape_rate"] == 0.0

    def test_escape_rate_computation(self, db):
        """Escape rate = escapes / green runs."""
        # Record 4 green runs
        run_ids = []
        for i in range(4):
            rid = db.record_run(
                goal=f"test-{i}", route="/", passed=True,
                failed_cases=[], failure_class=None,
                confidence=0.0, attempts=0, fingerprint=None,
                outcome="pass",
            )
            run_ids.append(rid)

        # 1 escape
        db.record_escape(run_ids[0], "QA-789", "/checkout")

        stats = db.compute_escape_rate()
        assert stats["total_green_runs"] == 4
        assert stats["escapes"] == 1
        assert stats["escape_rate"] == 0.25

    def test_triage_accuracy_computation(self, db):
        """Triage accuracy = correct / audited."""
        run_id = db.record_run(
            goal="test", route="/", passed=False,
            failed_cases=["tc-1"], failure_class="locator_drift",
            confidence=0.9, attempts=0, fingerprint=None,
            outcome="healed",
        )

        # Record 3 triage calls
        t1 = db.record_triage_call(run_id, "locator_drift", 0.9)
        t2 = db.record_triage_call(run_id, "app_defect", 0.8)
        t3 = db.record_triage_call(run_id, "locator_drift", 0.6)

        # Audit: 2 correct, 1 wrong
        db.mark_triage_correctness(t1, True)
        db.mark_triage_correctness(t2, True)
        db.mark_triage_correctness(t3, False)

        stats = db.compute_triage_accuracy()
        assert stats["total_audited"] == 3
        assert stats["correct"] == 2
        assert round(stats["accuracy"], 4) == 0.6667

    def test_triage_accuracy_no_audited(self, db):
        """No audited calls → 0 accuracy (not division by zero)."""
        stats = db.compute_triage_accuracy()
        assert stats["accuracy"] == 0.0
        assert stats["total_audited"] == 0

    def test_escape_rate_no_runs(self, db):
        """No runs → 0 escape rate."""
        stats = db.compute_escape_rate()
        assert stats["escape_rate"] == 0.0

    def test_dashboard(self, db):
        """Dashboard returns both metrics."""
        dashboard = db.get_dashboard()
        assert "escape_rate" in dashboard
        assert "triage_accuracy" in dashboard

    def test_record_triage_with_human_override(self, db):
        """Human override is stored."""
        run_id = db.record_run(
            goal="test", route="/", passed=False,
            failed_cases=["tc-1"], failure_class="unknown",
            confidence=0.5, attempts=0, fingerprint=None,
            outcome="failed",
        )
        t_id = db.record_triage_call(run_id, "unknown", 0.5, human_override="heal")
        assert t_id >= 1


class TestMetricsNode:
    @pytest.mark.asyncio
    async def test_metrics_records_pass(self, tmp_path):
        """Metrics node records a passing run."""
        import qa_agent.nodes.metrics as metrics_mod
        original = metrics_mod._DEFAULT_DB_PATH
        metrics_mod._DEFAULT_DB_PATH = tmp_path / "test.db"

        try:
            state = QAState(
                goal="test checkout",
                run_results=RunResult(passed=True, failed_cases=[], logs="ok"),
            )
            result = await metrics(state)
            assert result == {}

            # Verify it was recorded
            db = MetricsDB(tmp_path / "test.db")
            stats = db.compute_escape_rate()
            assert stats["total_green_runs"] == 1
        finally:
            metrics_mod._DEFAULT_DB_PATH = original

    @pytest.mark.asyncio
    async def test_metrics_records_defect(self, tmp_path):
        """Metrics node records a defect outcome with triage call."""
        import qa_agent.nodes.metrics as metrics_mod
        original = metrics_mod._DEFAULT_DB_PATH
        metrics_mod._DEFAULT_DB_PATH = tmp_path / "test.db"

        try:
            state = QAState(
                goal="test checkout",
                run_results=RunResult(passed=False, failed_cases=["tc-1"], logs="error"),
                failure_class="app_defect",
                confidence=0.9,
                attempts=1,
            )
            result = await metrics(state)
            assert result == {}

            db = MetricsDB(tmp_path / "test.db")
            stats = db.compute_triage_accuracy()
            # One triage call recorded, not yet audited
            assert stats["total_audited"] == 0
        finally:
            metrics_mod._DEFAULT_DB_PATH = original
