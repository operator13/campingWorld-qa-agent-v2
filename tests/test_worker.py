"""Tests for the Eval Worker server (Phase 1).

Tests worker endpoints: health, eval/run, eval/ecc/run, test/run, test/stop, status,
broadcast resilience, and duplicate rejection.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from qa_agent.dashboard.worker import app


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------


def test_worker_health_check(client):
    """GET /api/worker/health returns 200 with status, API key presence, uptime."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-123"}):
        resp = client.get("/api/worker/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "api_key" in data
    assert "uptime_seconds" in data
    assert "eval_state" in data
    assert "ecc_eval_state" in data
    assert "test_state" in data


def test_worker_health_no_api_key(client):
    """Health check reports api_key: false when ANTHROPIC_API_KEY is missing."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", ""):
        resp = client.get("/api/worker/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key"] is False


def test_worker_health_alias(client):
    """GET /health also works (for Docker HEALTHCHECK)."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------


def test_worker_status_endpoint(client):
    """GET /api/worker/status returns current state for eval, ecc_eval, and test."""
    resp = client.get("/api/worker/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "eval" in data
    assert "ecc_eval" in data
    assert "test" in data
    assert data["eval"]["state"] == "idle"
    assert data["ecc_eval"]["state"] == "idle"


# ---------------------------------------------------------------------------
# Pipeline eval tests
# ---------------------------------------------------------------------------


def test_pipeline_eval_run_single(client):
    """POST /api/worker/eval/run {agent: "triage"} returns 200."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", "sk-test"), \
         patch("qa_agent.dashboard.worker._execute_pipeline_eval", new_callable=AsyncMock) as mock_exec, \
         patch("qa_agent.dashboard.worker._eval_status", {"state": "idle", "current_agent": None, "completed": [], "progress": {}, "last_activity": 0}):
        resp = client.post("/api/worker/eval/run", json={"agent": "triage"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert "triage" in data["agents"]


def test_pipeline_eval_run_all(client):
    """POST /api/worker/eval/run {all: true} returns 200, starts all 4 agents."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", "sk-test"), \
         patch("qa_agent.dashboard.worker._execute_pipeline_eval", new_callable=AsyncMock), \
         patch("qa_agent.dashboard.worker._eval_status", {"state": "idle", "current_agent": None, "completed": [], "progress": {}, "last_activity": 0}):
        resp = client.post("/api/worker/eval/run", json={"all": True})
    assert resp.status_code == 200
    assert set(resp.json()["agents"]) == {"triage", "planner", "generator", "healer"}


def test_pipeline_eval_invalid_agent(client):
    """POST /api/worker/eval/run {agent: "fake"} returns 400."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", "sk-test"), \
         patch("qa_agent.dashboard.worker._eval_status", {"state": "idle", "current_agent": None, "completed": [], "progress": {}, "last_activity": 0}):
        resp = client.post("/api/worker/eval/run", json={"agent": "fake"})
    assert resp.status_code == 400


def test_pipeline_eval_no_api_key(client):
    """POST /api/worker/eval/run without API key returns 503."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", ""):
        resp = client.post("/api/worker/eval/run", json={"agent": "triage"})
    assert resp.status_code == 503


def test_pipeline_eval_reject_duplicate(client):
    """Second POST while eval running returns 409 Conflict."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", "sk-test"), \
         patch("qa_agent.dashboard.worker._eval_status", {"state": "running", "current_agent": "triage", "completed": [], "progress": {}, "last_activity": 0}):
        resp = client.post("/api/worker/eval/run", json={"agent": "triage"})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# ECC eval tests
# ---------------------------------------------------------------------------


def test_ecc_eval_run_single_agent(client):
    """POST /api/worker/eval/ecc/run {agents: ["security-reviewer"]} returns 200."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", "sk-test"), \
         patch("qa_agent.dashboard.worker._execute_ecc_eval", new_callable=AsyncMock), \
         patch("qa_agent.dashboard.worker._ecc_eval_status", {"state": "idle", "current_agent": None, "completed": [], "progress": {}, "last_activity": 0}):
        resp = client.post("/api/worker/eval/ecc/run", json={"agents": ["security-reviewer"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert "security-reviewer" in data["agents"]


def test_ecc_eval_run_all(client):
    """POST /api/worker/eval/ecc/run {all: true} returns 200, starts all 12 agents."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", "sk-test"), \
         patch("qa_agent.dashboard.worker._execute_ecc_eval", new_callable=AsyncMock), \
         patch("qa_agent.dashboard.worker._ecc_eval_status", {"state": "idle", "current_agent": None, "completed": [], "progress": {}, "last_activity": 0}):
        resp = client.post("/api/worker/eval/ecc/run", json={"all": True})
    assert resp.status_code == 200
    assert len(resp.json()["agents"]) == 12


def test_ecc_eval_run_invalid_agent(client):
    """POST /api/worker/eval/ecc/run {agents: ["fake-agent"]} returns 400."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", "sk-test"), \
         patch("qa_agent.dashboard.worker._ecc_eval_status", {"state": "idle", "current_agent": None, "completed": [], "progress": {}, "last_activity": 0}):
        resp = client.post("/api/worker/eval/ecc/run", json={"agents": ["fake-agent"]})
    assert resp.status_code == 400


def test_ecc_eval_reject_duplicate(client):
    """Second POST while ECC eval running returns 409 Conflict."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", "sk-test"), \
         patch("qa_agent.dashboard.worker._ecc_eval_status", {"state": "running", "current_agent": "security-reviewer", "completed": [], "progress": {}, "last_activity": 0}):
        resp = client.post("/api/worker/eval/ecc/run", json={"agents": ["code-reviewer"]})
    assert resp.status_code == 409


def test_ecc_eval_no_api_key(client):
    """POST /api/worker/eval/ecc/run without API key returns 503."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", ""):
        resp = client.post("/api/worker/eval/ecc/run", json={"agents": ["security-reviewer"]})
    assert resp.status_code == 503


def test_ecc_eval_tier_detection(client):
    """POST /api/worker/eval/ecc/run {tier: "detection"} returns 7 agents."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", "sk-test"), \
         patch("qa_agent.dashboard.worker._execute_ecc_eval", new_callable=AsyncMock), \
         patch("qa_agent.dashboard.worker._ecc_eval_status", {"state": "idle", "current_agent": None, "completed": [], "progress": {}, "last_activity": 0}):
        resp = client.post("/api/worker/eval/ecc/run", json={"tier": "detection"})
    assert resp.status_code == 200
    assert len(resp.json()["agents"]) == 7


def test_ecc_eval_tier_generative(client):
    """POST /api/worker/eval/ecc/run {tier: "generative"} returns 5 agents."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", "sk-test"), \
         patch("qa_agent.dashboard.worker._execute_ecc_eval", new_callable=AsyncMock), \
         patch("qa_agent.dashboard.worker._ecc_eval_status", {"state": "idle", "current_agent": None, "completed": [], "progress": {}, "last_activity": 0}):
        resp = client.post("/api/worker/eval/ecc/run", json={"tier": "generative"})
    assert resp.status_code == 200
    assert len(resp.json()["agents"]) == 5


# ---------------------------------------------------------------------------
# Test runner tests
# ---------------------------------------------------------------------------


def test_test_run_selected(client):
    """POST /api/worker/test/run {specs: ["cart.spec.ts"]} returns 200."""
    with patch("qa_agent.dashboard.worker._execute_test_run", new_callable=AsyncMock):
        resp = client.post("/api/worker/test/run", json={"specs": ["cart.spec.ts"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert "run_id" in data


def test_test_run_all(client):
    """POST /api/worker/test/run {all: true} returns 200."""
    with patch("qa_agent.dashboard.worker._execute_test_run", new_callable=AsyncMock):
        resp = client.post("/api/worker/test/run", json={"all": True})
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


def test_test_stop(client):
    """POST /api/worker/test/stop returns 200."""
    resp = client.post("/api/worker/test/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("stopped", "not_running")


def test_test_stop_nothing_running(client):
    """POST /api/worker/test/stop when idle returns 200 (no-op)."""
    resp = client.post("/api/worker/test/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_running"


def test_test_run_invalid_spec(client):
    """Specs not in allowlist are silently filtered out."""
    with patch("qa_agent.dashboard.worker._execute_test_run", new_callable=AsyncMock):
        resp = client.post("/api/worker/test/run", json={"specs": ["evil.spec.ts", "cart.spec.ts"]})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Broadcast resilience tests
# ---------------------------------------------------------------------------


def test_worker_broadcasts_to_dashboard():
    """Worker POSTs progress events to dashboard broadcast endpoint."""
    import asyncio
    from qa_agent.dashboard.worker import _broadcast_to_dashboard

    with patch("qa_agent.dashboard.worker.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        asyncio.get_event_loop().run_until_complete(
            _broadcast_to_dashboard({"event": "ecc_eval:agent:start", "agent": "security-reviewer"})
        )
        mock_instance.post.assert_called_once()
        call_url = mock_instance.post.call_args[0][0]
        assert "/api/eval/ecc/broadcast" in call_url


def test_worker_broadcast_failure_resilient():
    """Worker continues eval even if dashboard broadcast POST fails."""
    import asyncio
    from qa_agent.dashboard.worker import _broadcast_to_dashboard

    with patch("qa_agent.dashboard.worker.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(side_effect=Exception("Connection refused"))
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        # Should not raise
        asyncio.get_event_loop().run_until_complete(
            _broadcast_to_dashboard({"event": "ecc_eval:log", "agent": "test", "line": "test"})
        )
