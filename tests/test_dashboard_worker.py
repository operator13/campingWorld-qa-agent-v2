"""Tests for Dashboard ↔ Worker integration (Phase 2).

Tests proxy endpoints, worker health detection, broadcast receiver,
and subprocess removal verification.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from qa_agent.dashboard.server import app


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Worker proxy tests
# ---------------------------------------------------------------------------


def _mock_proxy_response(status_code: int, json_data: dict):
    """Helper to mock _proxy_to_worker to return a pre-built JSONResponse."""
    async def mock_proxy(method, path, body=None):
        return JSONResponse(content=json_data, status_code=status_code)
    return mock_proxy


def test_dashboard_proxies_ecc_eval_to_worker(client):
    """Dashboard POST /api/eval/ecc/run forwards to worker POST /api/worker/eval/ecc/run."""
    with patch("qa_agent.dashboard.server._proxy_to_worker",
               side_effect=_mock_proxy_response(200, {"status": "started", "agents": ["security-reviewer"]})):
        resp = client.post("/api/eval/ecc/run", json={"agents": ["security-reviewer"]})
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


def test_dashboard_proxies_pipeline_eval_to_worker(client):
    """Dashboard POST /api/eval/run forwards to worker POST /api/worker/eval/run."""
    with patch("qa_agent.dashboard.server._proxy_to_worker",
               side_effect=_mock_proxy_response(200, {"status": "started", "agents": ["triage"]})):
        resp = client.post("/api/eval/run", json={"agents": ["triage"]})
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


def test_dashboard_proxies_test_run_to_worker(client):
    """Dashboard POST /api/tests/run forwards to worker POST /api/worker/test/run."""
    with patch("qa_agent.dashboard.server._proxy_to_worker",
               side_effect=_mock_proxy_response(200, {"status": "started", "run_id": "09_07_2026_12-00-00"})):
        resp = client.post("/api/tests/run", json={"specs": ["cart.spec.ts"]})
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


def test_dashboard_worker_offline_returns_503(client):
    """Dashboard returns 503 when worker is unreachable."""
    with patch("qa_agent.dashboard.server._check_worker_health", new_callable=AsyncMock, return_value=False):
        resp = client.post("/api/eval/run", json={"agent": "triage"})
    assert resp.status_code == 503
    assert "Worker offline" in resp.json()["error"]


# ---------------------------------------------------------------------------
# Worker health endpoint
# ---------------------------------------------------------------------------


def test_dashboard_health_includes_worker_status(client):
    """GET /api/worker/online includes worker_online status."""
    with patch("qa_agent.dashboard.server._check_worker_health", new_callable=AsyncMock, return_value=True):
        resp = client.get("/api/worker/online")
    assert resp.status_code == 200
    assert resp.json()["online"] is True


def test_dashboard_worker_offline_indicator(client):
    """GET /api/worker/online returns false when worker is down."""
    with patch("qa_agent.dashboard.server._check_worker_health", new_callable=AsyncMock, return_value=False):
        resp = client.get("/api/worker/online")
    assert resp.status_code == 200
    assert resp.json()["online"] is False


# ---------------------------------------------------------------------------
# Broadcast receiver
# ---------------------------------------------------------------------------


def test_worker_broadcast_endpoint(client):
    """POST /api/worker/broadcast receives events from worker."""
    resp = client.post("/api/worker/broadcast", json={
        "event": "runner:start", "run_id": "test-123", "specs": ["all"],
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_worker_broadcast_invalid_event(client):
    """POST /api/worker/broadcast with invalid event is ignored."""
    resp = client.post("/api/worker/broadcast", json={
        "event": "invalid:event", "data": "test",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# Subprocess removal verification
# ---------------------------------------------------------------------------


def test_subprocess_removed_from_server():
    """server.py no longer contains asyncio.create_subprocess_exec for eval/test execution."""
    import inspect
    from qa_agent.dashboard import server

    source = inspect.getsource(server)
    # The subprocess execution functions should be gone
    assert "create_subprocess_exec" not in source
    # The subprocess module import should be gone
    assert "import subprocess" not in source


def test_no_sys_import_in_server():
    """server.py no longer imports sys (was only used for sys.executable in subprocesses)."""
    import inspect
    from qa_agent.dashboard import server

    source = inspect.getsource(server)
    assert "import sys" not in source


# ---------------------------------------------------------------------------
# ECC eval broadcast still works
# ---------------------------------------------------------------------------


def test_ecc_broadcast_endpoint_still_works(client):
    """POST /api/eval/ecc/broadcast still accepts events from CLI runners."""
    resp = client.post("/api/eval/ecc/broadcast", json={
        "event": "ecc_eval:agent:start", "agent": "security-reviewer",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Eval stop still works
# ---------------------------------------------------------------------------


def test_eval_stop_endpoint(client):
    """POST /api/eval/stop proxies to worker."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "stopped"}

    with patch("qa_agent.dashboard.server._check_worker_health", new_callable=AsyncMock, return_value=True), \
         patch("qa_agent.dashboard.server.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_resp)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        # eval/stop is still handled locally (not proxied)
        resp = client.post("/api/eval/stop")
    # This should still work since eval/stop is still local
    assert resp.status_code == 200
