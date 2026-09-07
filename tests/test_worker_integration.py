"""Real integration tests for the Docker two-container stack.

These tests require `docker compose up` to be running.
They hit the actual containers over HTTP — no mocks.

Run with: pytest tests/test_worker_integration.py -v
Skip if containers aren't running: tests auto-skip via the `docker_stack` fixture.
"""
import json
import subprocess
import time

import pytest
import requests

DASHBOARD_URL = "http://localhost:8080"
WORKER_URL = "http://localhost:8081"


@pytest.fixture(scope="module")
def docker_stack():
    """Skip all tests if the Docker stack isn't running."""
    try:
        r = requests.get(f"{WORKER_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("Worker container not running")
    except requests.ConnectionError:
        pytest.skip("Docker stack not running (worker unreachable)")
    try:
        r = requests.get(f"{DASHBOARD_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("Dashboard container not running")
    except requests.ConnectionError:
        pytest.skip("Docker stack not running (dashboard unreachable)")
    return True


# ---------------------------------------------------------------------------
# Phase 1: Worker container verification
# ---------------------------------------------------------------------------


class TestWorkerHealth:
    """Verify the worker container is properly configured."""

    def test_worker_health_returns_ok(self, docker_stack):
        """Worker health endpoint returns status ok."""
        r = requests.get(f"{WORKER_URL}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

    def test_worker_has_api_key(self, docker_stack):
        """Worker has ANTHROPIC_API_KEY loaded from .env."""
        r = requests.get(f"{WORKER_URL}/health")
        data = r.json()
        assert data["api_key"] is True, "Worker missing ANTHROPIC_API_KEY — check .env and docker-compose env_file"

    def test_worker_has_node(self, docker_stack):
        """Worker container has Node.js installed."""
        r = requests.get(f"{WORKER_URL}/health")
        assert r.json()["node"] is True

    def test_worker_has_playwright(self, docker_stack):
        """Worker container has Playwright available."""
        r = requests.get(f"{WORKER_URL}/health")
        assert r.json()["playwright"] is True

    def test_worker_uptime_positive(self, docker_stack):
        """Worker reports positive uptime (it's actually running)."""
        r = requests.get(f"{WORKER_URL}/health")
        assert r.json()["uptime_seconds"] > 0

    def test_worker_status_endpoint_responds(self, docker_stack):
        """Worker status endpoint returns valid state for all subsystems."""
        r = requests.get(f"{WORKER_URL}/api/worker/status")
        assert r.status_code == 200
        data = r.json()
        assert data["eval"]["state"] in ("idle", "running")
        assert data["ecc_eval"]["state"] in ("idle", "running")
        assert data["test"]["state"] in ("idle", "running", "complete")


class TestWorkerCLI:
    """Verify CLI tools work inside the worker container (Phase 3)."""

    def test_node_version(self, docker_stack):
        """Node.js v20+ is installed in the worker container."""
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "node", "--version"],
            capture_output=True, text=True, timeout=10,
            cwd="/Users/oantazo/Desktop/claud_projects/campingWorld-qa-agent-v2/qa_agent/dashboard",
        )
        assert result.returncode == 0
        version = result.stdout.strip()
        assert version.startswith("v2"), f"Expected Node v20+, got {version}"

    def test_playwright_version(self, docker_stack):
        """Playwright CLI is available in the worker container."""
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "npx", "playwright", "--version"],
            capture_output=True, text=True, timeout=15,
            cwd="/Users/oantazo/Desktop/claud_projects/campingWorld-qa-agent-v2/qa_agent/dashboard",
        )
        assert result.returncode == 0
        assert result.stdout.strip(), "Playwright version should be non-empty"

    def test_playwright_test_module_resolves(self, docker_stack):
        """@playwright/test module can be imported (the bug we caught)."""
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "node", "-e", "require('@playwright/test')"],
            capture_output=True, text=True, timeout=10,
            cwd="/Users/oantazo/Desktop/claud_projects/campingWorld-qa-agent-v2/qa_agent/dashboard",
        )
        assert result.returncode == 0, f"@playwright/test failed to load: {result.stderr}"

    def test_playwright_can_list_tests(self, docker_stack):
        """Playwright can parse and list test specs without errors."""
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "npx", "playwright", "test", "--list"],
            capture_output=True, text=True, timeout=30,
            cwd="/Users/oantazo/Desktop/claud_projects/campingWorld-qa-agent-v2/qa_agent/dashboard",
        )
        # --list should succeed and show test names
        assert result.returncode == 0, f"playwright test --list failed: {result.stderr}"
        assert "spec.ts" in result.stdout, f"No specs found in output: {result.stdout[:500]}"

    def test_qa_agent_importable(self, docker_stack):
        """qa_agent package can be imported inside the worker."""
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "python", "-c", "import qa_agent; print('ok')"],
            capture_output=True, text=True, timeout=10,
            cwd="/Users/oantazo/Desktop/claud_projects/campingWorld-qa-agent-v2/qa_agent/dashboard",
        )
        assert result.returncode == 0
        assert "ok" in result.stdout


# ---------------------------------------------------------------------------
# Phase 1-2: Dashboard ↔ Worker communication
# ---------------------------------------------------------------------------


class TestDashboardWorkerCommunication:
    """Verify dashboard can reach worker and proxy requests."""

    def test_dashboard_health_reports_worker_online(self, docker_stack):
        """Dashboard /health endpoint reports worker_online: true."""
        r = requests.get(f"{DASHBOARD_URL}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["worker_online"] is True, "Dashboard can't reach worker"

    def test_dashboard_worker_online_endpoint(self, docker_stack):
        """Dashboard /api/worker/online returns true."""
        r = requests.get(f"{DASHBOARD_URL}/api/worker/online")
        assert r.status_code == 200
        assert r.json()["online"] is True

    def test_dashboard_proxies_to_worker_health(self, docker_stack):
        """Dashboard can forward requests to worker (verifying network connectivity)."""
        # Hit worker health directly
        r1 = requests.get(f"{WORKER_URL}/health")
        # Hit it through dashboard proxy awareness
        r2 = requests.get(f"{DASHBOARD_URL}/api/worker/online")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["online"] is True

    def test_no_secrets_in_dashboard_container(self, docker_stack):
        """Dashboard container does NOT have ANTHROPIC_API_KEY."""
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "dashboard", "printenv", "ANTHROPIC_API_KEY"],
            capture_output=True, text=True, timeout=10,
            cwd="/Users/oantazo/Desktop/claud_projects/campingWorld-qa-agent-v2/qa_agent/dashboard",
        )
        # Should fail (env var not set) or return empty
        assert result.stdout.strip() == "", "Dashboard should NOT have ANTHROPIC_API_KEY"


# ---------------------------------------------------------------------------
# Phase 1: Shared volume
# ---------------------------------------------------------------------------


class TestSharedVolume:
    """Verify shared volume works between containers."""

    def test_worker_can_write_to_shared_volume(self, docker_stack):
        """Worker can write a file that the dashboard can read."""
        test_file = "/data/health-reports/_integration_test.json"
        test_content = '{"test": true}'
        compose_dir = "/Users/oantazo/Desktop/claud_projects/campingWorld-qa-agent-v2/qa_agent/dashboard"

        # Worker writes
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "sh", "-c",
             f"echo '{test_content}' > {test_file}"],
            capture_output=True, text=True, timeout=10, cwd=compose_dir,
        )
        assert result.returncode == 0, f"Worker write failed: {result.stderr}"

        # Dashboard reads
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "dashboard", "cat", test_file],
            capture_output=True, text=True, timeout=10, cwd=compose_dir,
        )
        assert result.returncode == 0, f"Dashboard read failed: {result.stderr}"
        assert '"test": true' in result.stdout

        # Cleanup
        subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "rm", "-f", test_file],
            capture_output=True, timeout=10, cwd=compose_dir,
        )

    def test_eval_reports_readable_by_dashboard(self, docker_stack):
        """Dashboard can read eval reports from the shared volume."""
        r = requests.get(f"{DASHBOARD_URL}/api/eval/ecc/scores")
        assert r.status_code == 200
        data = r.json()
        # At least one agent should have data (scores loaded from bind mount)
        agents_with_data = [a for a, v in data.items() if v.get("score") is not None]
        assert len(agents_with_data) > 0, "No ECC eval scores found — shared volume may be empty"

    def test_health_reports_readable_by_dashboard(self, docker_stack):
        """Dashboard can read health reports from the shared volume."""
        r = requests.get(f"{DASHBOARD_URL}/api/health/latest")
        assert r.status_code == 200
        data = r.json()
        assert "overall_score" in data, "No health data — shared volume may not have health-reports"
        assert "domains" in data
        assert len(data["domains"]) > 0


# ---------------------------------------------------------------------------
# Eval report write path — worker writes, dashboard reads
# ---------------------------------------------------------------------------


class TestEvalReportWritePath:
    """Verify that when the worker runs evals, the reports are visible to the dashboard.

    This tests the critical path: eval runner inside worker writes to /app/qa_agent/eval/reports/
    which must be bind-mounted to the same host directory that the dashboard reads from
    /data/qa_agent/eval/reports/. Without this, evals complete but scores/tokens never update.
    """

    def test_worker_eval_reports_dir_is_mounted(self, docker_stack):
        """Worker's /app/qa_agent/eval/reports/ is the same as /data/qa_agent/eval/reports/."""
        compose_dir = "/Users/oantazo/Desktop/claud_projects/campingWorld-qa-agent-v2/qa_agent/dashboard"
        # Write a marker file via the code path (where eval runner writes)
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "sh", "-c",
             "echo 'mount_test' > /app/qa_agent/eval/reports/_mount_test.txt"],
            capture_output=True, text=True, timeout=10, cwd=compose_dir,
        )
        assert result.returncode == 0

        # Read it from the data path (where dashboard reads)
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "dashboard", "cat",
             "/data/qa_agent/eval/reports/_mount_test.txt"],
            capture_output=True, text=True, timeout=10, cwd=compose_dir,
        )
        assert result.returncode == 0
        assert "mount_test" in result.stdout, \
            "Worker code path /app/qa_agent/eval/reports/ is NOT mounted to shared volume — eval reports won't be visible to dashboard"

        # Cleanup
        subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "rm", "-f",
             "/app/qa_agent/eval/reports/_mount_test.txt"],
            capture_output=True, timeout=10, cwd=compose_dir,
        )

    def test_worker_ecc_reports_dir_is_mounted(self, docker_stack):
        """Worker's /app/qa_agent/eval/ecc/reports/ maps to dashboard's /data path."""
        compose_dir = "/Users/oantazo/Desktop/claud_projects/campingWorld-qa-agent-v2/qa_agent/dashboard"
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "sh", "-c",
             "echo 'ecc_mount_test' > /app/qa_agent/eval/ecc/reports/_mount_test.txt"],
            capture_output=True, text=True, timeout=10, cwd=compose_dir,
        )
        assert result.returncode == 0

        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "dashboard", "cat",
             "/data/qa_agent/eval/ecc/reports/_mount_test.txt"],
            capture_output=True, text=True, timeout=10, cwd=compose_dir,
        )
        assert result.returncode == 0
        assert "ecc_mount_test" in result.stdout, \
            "Worker code path /app/qa_agent/eval/ecc/reports/ is NOT mounted — ECC eval reports won't be visible"

        subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "rm", "-f",
             "/app/qa_agent/eval/ecc/reports/_mount_test.txt"],
            capture_output=True, timeout=10, cwd=compose_dir,
        )

    def test_worker_memory_audit_dir_is_mounted(self, docker_stack):
        """Worker's /app/memory/audit_runs/ maps to dashboard's /data path."""
        compose_dir = "/Users/oantazo/Desktop/claud_projects/campingWorld-qa-agent-v2/qa_agent/dashboard"
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "sh", "-c",
             "echo 'audit_test' > /app/memory/audit_runs/_mount_test.txt"],
            capture_output=True, text=True, timeout=10, cwd=compose_dir,
        )
        assert result.returncode == 0

        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "dashboard", "cat",
             "/data/memory/audit_runs/_mount_test.txt"],
            capture_output=True, text=True, timeout=10, cwd=compose_dir,
        )
        assert result.returncode == 0
        assert "audit_test" in result.stdout, \
            "Worker code path /app/memory/audit_runs/ is NOT mounted — cost/token tracking won't be visible"

        subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "rm", "-f",
             "/app/memory/audit_runs/_mount_test.txt"],
            capture_output=True, timeout=10, cwd=compose_dir,
        )

    def test_worker_test_results_dir_is_mounted(self, docker_stack):
        """Worker's /data/test-results/ is readable by dashboard."""
        compose_dir = "/Users/oantazo/Desktop/claud_projects/campingWorld-qa-agent-v2/qa_agent/dashboard"
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "sh", "-c",
             "echo 'results_test' > /data/test-results/_mount_test.txt"],
            capture_output=True, text=True, timeout=10, cwd=compose_dir,
        )
        assert result.returncode == 0

        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "dashboard", "cat",
             "/data/test-results/_mount_test.txt"],
            capture_output=True, text=True, timeout=10, cwd=compose_dir,
        )
        assert result.returncode == 0
        assert "results_test" in result.stdout

        subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "rm", "-f",
             "/data/test-results/_mount_test.txt"],
            capture_output=True, timeout=10, cwd=compose_dir,
        )

    def test_worker_health_reports_dir_is_writable(self, docker_stack):
        """Worker can write health reports to the shared bind mount."""
        compose_dir = "/Users/oantazo/Desktop/claud_projects/campingWorld-qa-agent-v2/qa_agent/dashboard"
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "sh", "-c",
             "echo 'health_test' > /data/health-reports/_mount_test.txt"],
            capture_output=True, text=True, timeout=10, cwd=compose_dir,
        )
        assert result.returncode == 0

        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "dashboard", "cat",
             "/data/health-reports/_mount_test.txt"],
            capture_output=True, text=True, timeout=10, cwd=compose_dir,
        )
        assert result.returncode == 0
        assert "health_test" in result.stdout

        subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "rm", "-f",
             "/data/health-reports/_mount_test.txt"],
            capture_output=True, timeout=10, cwd=compose_dir,
        )


# ---------------------------------------------------------------------------
# Phase 2: Dashboard data endpoints return real data
# ---------------------------------------------------------------------------


class TestDashboardDataEndpoints:
    """Verify dashboard serves real data from shared volume."""

    def test_health_gauge_data(self, docker_stack):
        """Health endpoint returns valid score and domain data."""
        r = requests.get(f"{DASHBOARD_URL}/api/health/latest")
        data = r.json()
        assert 0 <= data["overall_score"] <= 1
        assert data["overall_status"] in ("HEALTHY", "DEGRADED", "CRITICAL")
        assert data["total_tests"] > 0

    def test_eval_summary_has_scores(self, docker_stack):
        """Pipeline eval summary returns real scores for agents."""
        r = requests.get(f"{DASHBOARD_URL}/api/eval/summary")
        data = r.json()
        assert "triage" in data
        assert "planner" in data
        assert "generator" in data
        assert "healer" in data
        # At least one agent should have a real score
        scores = [v["score"] for v in data.values() if v.get("score") is not None]
        assert len(scores) > 0, "No pipeline eval scores found"

    def test_ecc_scores_have_metrics(self, docker_stack):
        """ECC eval scores include tier-specific metrics (recall/quality)."""
        r = requests.get(f"{DASHBOARD_URL}/api/eval/ecc/scores")
        data = r.json()
        # Check a detection agent has recall
        for agent in ["security-reviewer", "code-reviewer", "silent-failure-hunter"]:
            if data.get(agent, {}).get("scores"):
                scores = data[agent]["scores"]
                assert "recall" in scores, f"{agent} missing recall metric"
                break
        # Check a generative agent has quality
        for agent in ["tdd-guide", "build-error-resolver", "e2e-runner"]:
            if data.get(agent, {}).get("scores"):
                scores = data[agent]["scores"]
                assert "quality" in scores, f"{agent} missing quality metric"
                break

    def test_run_history_has_entries(self, docker_stack):
        """Run history returns past test runs."""
        r = requests.get(f"{DASHBOARD_URL}/api/health/history")
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0, "No run history entries"
        entry = data[0]
        assert "run_id" in entry
        assert "timestamp" in entry

    def test_ecc_tokens_and_cost_tracked(self, docker_stack):
        """ECC eval cards include token counts and cost estimates."""
        r = requests.get(f"{DASHBOARD_URL}/api/eval/ecc/scores")
        data = r.json()
        agents_with_tokens = [
            a for a, v in data.items()
            if v.get("tokens") is not None and v["tokens"] > 0
        ]
        assert len(agents_with_tokens) > 0, "No agents have token usage recorded"
        # Verify cost is calculated
        agents_with_cost = [
            a for a, v in data.items()
            if v.get("cost") is not None and v["cost"] > 0
        ]
        assert len(agents_with_cost) > 0, "No agents have cost calculated"
