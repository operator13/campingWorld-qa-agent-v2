"""Tests for config module."""

from qa_agent.config import (
    CONF_SURE,
    MAX_ATTEMPTS,
    EnvConfig,
    RouteMapping,
    get_model,
    load_figma_route_map,
)


def test_constants():
    """Thresholds have expected defaults."""
    assert CONF_SURE == 0.75
    assert MAX_ATTEMPTS == 3


def test_get_model_defaults():
    """get_model returns the mapped model for known nodes."""
    assert "sonnet" in get_model("design_reader")
    assert "sonnet" in get_model("planner")
    assert "sonnet" in get_model("generator")
    assert "sonnet" in get_model("triage")


def test_get_model_unknown_fallback():
    """Unknown node names fall back to sonnet."""
    assert "sonnet" in get_model("nonexistent_node")


def test_env_config_defaults():
    """EnvConfig has sane defaults."""
    cfg = EnvConfig()
    assert cfg.app_base_url == "http://localhost:3000"
    assert cfg.langsmith_project == "qa-agent"
    assert cfg.langsmith_tracing is True


def test_load_figma_route_map():
    """figma_route_map parses raw dict into RouteMapping objects."""
    raw = {
        "1:24": {"route": "/checkout", "testid_prefix": "checkout-"},
        "1:88": {"route": "/login", "testid_prefix": "login-"},
    }
    result = load_figma_route_map(raw)
    assert len(result) == 2
    assert isinstance(result["1:24"], RouteMapping)
    assert result["1:24"].route == "/checkout"
    assert result["1:88"].testid_prefix == "login-"
