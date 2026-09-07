"""Tests for cloud deployment readiness (Phase 4).

Tests health check endpoints, graceful shutdown, Dockerfile existence,
and GitHub Actions workflow validity.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from qa_agent.dashboard.server import app as dashboard_app
from qa_agent.dashboard.worker import app as worker_app

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def dashboard_client():
    return TestClient(dashboard_app)


@pytest.fixture
def worker_client():
    return TestClient(worker_app)


# ---------------------------------------------------------------------------
# Health endpoint tests
# ---------------------------------------------------------------------------


def test_dashboard_health_endpoint(dashboard_client):
    """GET /health returns 200 with {status: "ok", worker_online: bool}."""
    with patch("qa_agent.dashboard.server._check_worker_health", new_callable=AsyncMock, return_value=False):
        resp = dashboard_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "worker_online" in data
    assert isinstance(data["worker_online"], bool)


def test_dashboard_health_with_worker_online(dashboard_client):
    """GET /health reports worker_online: true when worker is reachable."""
    with patch("qa_agent.dashboard.server._check_worker_health", new_callable=AsyncMock, return_value=True):
        resp = dashboard_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["worker_online"] is True


def test_worker_health_endpoint(worker_client):
    """GET /health returns 200 with {status: "ok", api_key: bool, cli: bool}."""
    resp = worker_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "api_key" in data
    assert "cli" in data
    assert isinstance(data["api_key"], bool)
    assert isinstance(data["cli"], bool)


def test_worker_health_reports_eval_states(worker_client):
    """Worker health includes eval and test state information."""
    resp = worker_client.get("/health")
    data = resp.json()
    assert "eval_state" in data
    assert "ecc_eval_state" in data
    assert "test_state" in data
    assert data["eval_state"] == "idle"


# ---------------------------------------------------------------------------
# Worker startup API key validation
# ---------------------------------------------------------------------------


def test_worker_startup_validates_api_key(worker_client):
    """Worker without ANTHROPIC_API_KEY starts but health reports api_key: false."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", ""):
        resp = worker_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["api_key"] is False


def test_worker_no_api_key_eval_returns_503(worker_client):
    """Eval endpoints return 503 when API key is missing."""
    with patch("qa_agent.dashboard.worker.ANTHROPIC_API_KEY", ""):
        resp = worker_client.post("/api/worker/eval/run", json={"agent": "triage"})
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Dockerfile existence tests
# ---------------------------------------------------------------------------


def test_dockerfile_dashboard_exists():
    """Dockerfile for dashboard exists."""
    dockerfile = PROJECT_ROOT / "qa_agent" / "dashboard" / "Dockerfile"
    assert dockerfile.exists(), f"Missing: {dockerfile}"


def test_dockerfile_worker_exists():
    """Dockerfile.worker for worker exists."""
    dockerfile = PROJECT_ROOT / "qa_agent" / "dashboard" / "Dockerfile.worker"
    assert dockerfile.exists(), f"Missing: {dockerfile}"


def test_docker_compose_exists():
    """docker-compose.yml with two services exists."""
    compose = PROJECT_ROOT / "qa_agent" / "dashboard" / "docker-compose.yml"
    assert compose.exists(), f"Missing: {compose}"
    content = compose.read_text()
    assert "dashboard:" in content
    assert "worker:" in content
    assert "shared-results:" in content


def test_docker_compose_has_env_file():
    """docker-compose.yml references .env file for worker secrets."""
    compose = PROJECT_ROOT / "qa_agent" / "dashboard" / "docker-compose.yml"
    content = compose.read_text()
    assert "env_file" in content


def test_docker_compose_has_healthcheck():
    """docker-compose.yml uses service_healthy condition for depends_on."""
    compose = PROJECT_ROOT / "qa_agent" / "dashboard" / "docker-compose.yml"
    content = compose.read_text()
    assert "service_healthy" in content


# ---------------------------------------------------------------------------
# GitHub Actions workflow tests
# ---------------------------------------------------------------------------


def test_github_actions_build_workflow_exists():
    """docker-build.yml GitHub Actions workflow exists."""
    workflow = PROJECT_ROOT / ".github" / "workflows" / "docker-build.yml"
    assert workflow.exists(), f"Missing: {workflow}"


def test_github_actions_builds_both_images():
    """Workflow builds both dashboard and worker images."""
    workflow = PROJECT_ROOT / ".github" / "workflows" / "docker-build.yml"
    content = workflow.read_text()
    assert "Dockerfile" in content
    assert "Dockerfile.worker" in content
    assert "build-dashboard" in content
    assert "build-worker" in content


# ---------------------------------------------------------------------------
# Deployment docs tests
# ---------------------------------------------------------------------------


def test_cloud_run_docs_exist():
    """Cloud Run deployment docs exist."""
    doc = PROJECT_ROOT / "docs" / "DEPLOY_CLOUD_RUN.md"
    assert doc.exists(), f"Missing: {doc}"
    content = doc.read_text()
    assert "gcloud" in content
    assert "ANTHROPIC_API_KEY" in content


def test_ecs_docs_exist():
    """ECS Fargate deployment docs exist."""
    doc = PROJECT_ROOT / "docs" / "DEPLOY_ECS.md"
    assert doc.exists(), f"Missing: {doc}"
    content = doc.read_text()
    assert "aws ecs" in content
    assert "ANTHROPIC_API_KEY" in content
