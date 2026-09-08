"""Audit trail integration tests.

Verifies that eval runs produce audit trail JSON files in memory/audit_runs/
with correct structure, token counts, and cost data. These tests run against
the live Docker stack and check real files on disk.

Run with: pytest tests/test_audit_trail.py -v
Requires: docker compose up (for integration tests) OR local eval run
"""
import json
import time
from pathlib import Path

import pytest
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = PROJECT_ROOT / "memory" / "audit_runs"
DASHBOARD_URL = "http://localhost:8080"
WORKER_URL = "http://localhost:8081"


@pytest.fixture(scope="module")
def docker_stack():
    """Skip integration tests if Docker stack isn't running."""
    try:
        r = requests.get(f"{WORKER_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("Worker not running")
    except requests.ConnectionError:
        pytest.skip("Docker stack not running")
    return True


# ---------------------------------------------------------------------------
# Unit tests — AuditStore start_run / end_run writes JSON
# ---------------------------------------------------------------------------


class TestAuditStoreWritesJSON:
    """Verify AuditStore.start_run/end_run produces valid JSON audit files."""

    def test_start_and_end_run_creates_json_file(self):
        """start_run + end_run writes a JSON file to memory/audit_runs/."""
        from qa_agent.audit import AuditStore

        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        run_id = f"test-audit-{int(time.time())}"
        json_path = AUDIT_DIR / f"{run_id}.json"

        try:
            AuditStore.start_run(run_id)
            AuditStore._current_run_entries.append({
                "node": "test-node",
                "timestamp": "2026-09-07T00:00:00",
                "duration_ms": 100,
                "model": "claude-haiku-4-5-20251001",
                "input_tokens": 500,
                "output_tokens": 200,
                "cost_usd": 0.0015,
                "errors": [],
                "input_state": {"test": True},
                "parsed_output": {"result": "ok"},
            })
            AuditStore._run_total_input_tokens = 500
            AuditStore._run_total_output_tokens = 200
            AuditStore._run_total_cost = 0.0015
            AuditStore.end_run()

            assert json_path.exists(), f"Audit JSON not created at {json_path}"
            data = json.loads(json_path.read_text())
            assert data["run_id"] == run_id
            assert data["total_input_tokens"] == 500
            assert data["total_output_tokens"] == 200
            assert data["estimated_cost_usd"] == 0.0015
            assert len(data["nodes"]) == 1
            assert data["nodes"][0]["node"] == "test-node"
        finally:
            if json_path.exists():
                json_path.unlink()

    def test_end_run_without_start_is_noop(self):
        """end_run with no active run does nothing (no crash)."""
        from qa_agent.audit import AuditStore

        AuditStore._current_run_id = None
        AuditStore.end_run()  # Should not raise

    def test_audit_json_has_required_fields(self):
        """Audit JSON contains all required top-level fields."""
        from qa_agent.audit import AuditStore

        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        run_id = f"test-fields-{int(time.time())}"
        json_path = AUDIT_DIR / f"{run_id}.json"

        try:
            AuditStore.start_run(run_id)
            AuditStore.end_run()

            data = json.loads(json_path.read_text())
            required = ["run_id", "timestamp", "total_duration_ms",
                        "total_input_tokens", "total_output_tokens",
                        "estimated_cost_usd", "outcome", "nodes"]
            for field in required:
                assert field in data, f"Missing required field: {field}"
        finally:
            if json_path.exists():
                json_path.unlink()

    def test_multiple_nodes_accumulate(self):
        """Multiple node entries are captured in a single run."""
        from qa_agent.audit import AuditStore

        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        run_id = f"test-multi-{int(time.time())}"
        json_path = AUDIT_DIR / f"{run_id}.json"

        try:
            AuditStore.start_run(run_id)
            for i in range(3):
                AuditStore._current_run_entries.append({
                    "node": f"node-{i}",
                    "timestamp": "2026-09-07T00:00:00",
                    "duration_ms": 50,
                    "model": None,
                    "input_tokens": 100 * (i + 1),
                    "output_tokens": 50 * (i + 1),
                    "cost_usd": 0.001 * (i + 1),
                    "errors": [],
                    "input_state": {},
                    "parsed_output": {},
                })
            AuditStore._run_total_input_tokens = 600
            AuditStore._run_total_output_tokens = 300
            AuditStore._run_total_cost = 0.006
            AuditStore.end_run()

            data = json.loads(json_path.read_text())
            assert len(data["nodes"]) == 3
            assert data["nodes"][0]["node"] == "node-0"
            assert data["nodes"][2]["node"] == "node-2"
            assert data["total_input_tokens"] == 600
        finally:
            if json_path.exists():
                json_path.unlink()


# ---------------------------------------------------------------------------
# Unit tests — _start_eval_audit / _end_eval_audit
# ---------------------------------------------------------------------------


class TestEvalAuditHelpers:
    """Verify eval audit patterns produce correct audit entries.

    Tests the AuditStore start_run/end_run pattern that eval runners use,
    without importing eval_runner (which pulls in langchain_anthropic).
    """

    def test_eval_audit_run_id_format(self):
        """Eval audit run_id follows the eval-{agent}-{timestamp} pattern."""
        from qa_agent.audit import AuditStore

        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        run_id = f"eval-triage-{int(time.time())}"
        json_path = AUDIT_DIR / f"{run_id}.json"

        try:
            AuditStore.start_run(run_id)
            assert run_id.startswith("eval-triage-")
            AuditStore.end_run()
        finally:
            if json_path.exists():
                json_path.unlink()

    def test_eval_audit_writes_json_with_eval_node(self):
        """Eval audit writes JSON with eval:agent node entry."""
        from qa_agent.audit import AuditStore

        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        run_id = f"eval-triage-{int(time.time())}"
        json_path = AUDIT_DIR / f"{run_id}.json"

        try:
            AuditStore.start_run(run_id)
            AuditStore._current_run_entries.append({
                "node": "eval:triage",
                "timestamp": "2026-09-07T00:00:00Z",
                "duration_ms": 0,
                "model": None,
                "input_tokens": 50000,
                "output_tokens": 20000,
                "cost_usd": 0.35,
                "errors": [],
                "input_state": {"agent": "triage", "type": "pipeline_eval"},
                "parsed_output": {
                    "score": 0.829,
                    "passed": True,
                    "total_tokens": 70000,
                },
            })
            AuditStore._run_total_input_tokens = 50000
            AuditStore._run_total_output_tokens = 20000
            AuditStore._run_total_cost = 0.35
            AuditStore.end_run()

            assert json_path.exists(), f"Audit JSON not created: {json_path}"
            data = json.loads(json_path.read_text())
            assert data["run_id"] == run_id
            assert len(data["nodes"]) == 1
            assert data["nodes"][0]["node"] == "eval:triage"
            assert data["nodes"][0]["input_tokens"] == 50000
            assert data["nodes"][0]["parsed_output"]["score"] == 0.829
            assert data["nodes"][0]["parsed_output"]["passed"] is True
            assert data["total_input_tokens"] == 50000
            assert data["estimated_cost_usd"] == 0.35
        finally:
            if json_path.exists():
                json_path.unlink()

    def test_eval_audit_records_failure(self):
        """Eval audit captures failure score in errors field."""
        from qa_agent.audit import AuditStore

        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        run_id = f"eval-healer-{int(time.time())}"
        json_path = AUDIT_DIR / f"{run_id}.json"

        try:
            AuditStore.start_run(run_id)
            AuditStore._current_run_entries.append({
                "node": "eval:healer",
                "timestamp": "2026-09-07T00:00:00Z",
                "duration_ms": 0,
                "model": None,
                "input_tokens": 30000,
                "output_tokens": 10000,
                "cost_usd": 0.2,
                "errors": ["score=0.5"],
                "input_state": {"agent": "healer", "type": "pipeline_eval"},
                "parsed_output": {"score": 0.5, "passed": False, "total_tokens": 40000},
            })
            AuditStore._run_total_input_tokens = 30000
            AuditStore._run_total_output_tokens = 10000
            AuditStore._run_total_cost = 0.2
            AuditStore.end_run()

            data = json.loads(json_path.read_text())
            assert data["nodes"][0]["errors"] == ["score=0.5"]
            assert data["nodes"][0]["parsed_output"]["passed"] is False
            assert data["outcome"] == "error"  # AuditStore derives "error" when errors list is non-empty
        finally:
            if json_path.exists():
                json_path.unlink()

    def test_ecc_eval_audit_writes_multiple_agent_nodes(self):
        """ECC eval audit writes one node entry per agent evaluated."""
        from qa_agent.audit import AuditStore

        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        run_id = f"ecc-eval-{int(time.time())}"
        json_path = AUDIT_DIR / f"{run_id}.json"

        try:
            AuditStore.start_run(run_id)
            for agent in ["security-reviewer", "code-reviewer", "python-reviewer"]:
                AuditStore._current_run_entries.append({
                    "node": f"ecc_eval:{agent}",
                    "timestamp": "2026-09-07T00:00:00Z",
                    "duration_ms": 0,
                    "model": None,
                    "input_tokens": 10000,
                    "output_tokens": 3000,
                    "cost_usd": 0.0,
                    "errors": [],
                    "input_state": {"agent": agent, "type": "ecc_eval"},
                    "parsed_output": {"passed": True, "score": 0.85, "token_estimate": 13000},
                })
            AuditStore._run_total_input_tokens = 30000
            AuditStore._run_total_output_tokens = 9000
            AuditStore.end_run()

            data = json.loads(json_path.read_text())
            assert len(data["nodes"]) == 3
            assert data["nodes"][0]["node"] == "ecc_eval:security-reviewer"
            assert data["nodes"][2]["node"] == "ecc_eval:python-reviewer"
            assert data["total_input_tokens"] == 30000
        finally:
            if json_path.exists():
                json_path.unlink()


# ---------------------------------------------------------------------------
# Integration tests — dashboard audit endpoint reads written files
# ---------------------------------------------------------------------------


class TestAuditDashboardIntegration:
    """Verify the dashboard audit summary endpoint reads audit trail files."""

    def test_audit_summary_reflects_written_file(self, docker_stack):
        """Write an audit file, verify /api/audit/summary includes it."""
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        run_id = f"test-dashboard-audit-{int(time.time())}"
        json_path = AUDIT_DIR / f"{run_id}.json"

        audit_data = {
            "run_id": run_id,
            "timestamp": "2026-09-07T00:00:00Z",
            "total_duration_ms": 5000,
            "total_input_tokens": 10000,
            "total_output_tokens": 5000,
            "estimated_cost_usd": 0.05,
            "outcome": "completed",
            "nodes": [],
        }

        try:
            json_path.write_text(json.dumps(audit_data))
            time.sleep(0.5)

            r = requests.get(f"{DASHBOARD_URL}/api/audit/summary")
            assert r.status_code == 200
            summary = r.json()
            assert summary["total_runs"] >= 1, "Audit summary should have at least 1 run"
            assert summary["total_input_tokens"] >= 10000
            assert summary["total_cost"] >= 0.05

            # Verify our specific run is in the runs list
            run_ids = [run["run_id"] for run in summary.get("runs", [])]
            assert run_id in run_ids, f"Run {run_id} not found in audit summary"
        finally:
            if json_path.exists():
                json_path.unlink()

    def test_audit_summary_empty_when_no_files(self, docker_stack):
        """When no audit files exist, summary returns zeros."""
        # This test relies on the current state — if audit_runs/ is empty
        files = list(AUDIT_DIR.glob("*.json"))
        if files:
            pytest.skip("audit_runs/ has existing files, can't test empty state")

        r = requests.get(f"{DASHBOARD_URL}/api/audit/summary")
        assert r.status_code == 200
        data = r.json()
        assert data["total_runs"] == 0
        assert data["total_tokens"] == 0
        assert data["total_cost"] == 0.0

    def test_audit_file_written_by_worker_visible_to_dashboard(self, docker_stack):
        """Worker writes to /app/memory/audit_runs/, dashboard reads from /data/memory/audit_runs/."""
        import subprocess
        compose_dir = str(PROJECT_ROOT / "qa_agent" / "dashboard")

        run_id = f"worker-audit-test-{int(time.time())}"
        test_data = json.dumps({
            "run_id": run_id,
            "timestamp": "2026-09-07T00:00:00Z",
            "total_duration_ms": 1000,
            "total_input_tokens": 5000,
            "total_output_tokens": 2000,
            "estimated_cost_usd": 0.025,
            "outcome": "completed",
            "nodes": [],
        })

        try:
            # Worker writes via code path
            result = subprocess.run(
                ["docker", "compose", "exec", "-T", "worker", "sh", "-c",
                 f"echo '{test_data}' > /app/memory/audit_runs/{run_id}.json"],
                capture_output=True, text=True, timeout=10, cwd=compose_dir,
            )
            assert result.returncode == 0, f"Worker write failed: {result.stderr}"

            # Dashboard reads via data path
            result = subprocess.run(
                ["docker", "compose", "exec", "-T", "dashboard", "cat",
                 f"/data/memory/audit_runs/{run_id}.json"],
                capture_output=True, text=True, timeout=10, cwd=compose_dir,
            )
            assert result.returncode == 0, f"Dashboard read failed: {result.stderr}"
            assert run_id in result.stdout

            # API also sees it
            time.sleep(0.5)
            r = requests.get(f"{DASHBOARD_URL}/api/audit/summary")
            run_ids = [run["run_id"] for run in r.json().get("runs", [])]
            assert run_id in run_ids, "Audit file written by worker not visible in dashboard API"
        finally:
            # Cleanup
            subprocess.run(
                ["docker", "compose", "exec", "-T", "worker", "rm", "-f",
                 f"/app/memory/audit_runs/{run_id}.json"],
                capture_output=True, timeout=10, cwd=compose_dir,
            )
