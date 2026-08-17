"""Configuration — env loading, model map, thresholds, figma↔route map."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# Routing / control constants (the knobs the Metrics loop tunes)
# ---------------------------------------------------------------------------
CONF_SURE: float = 0.75  # >= this => Triage acts automatically
MAX_ATTEMPTS: int = 3  # heal attempts before escalating to a bug


# ---------------------------------------------------------------------------
# Model map — which Claude model each node uses
# ---------------------------------------------------------------------------
MODEL_MAP: dict[str, str] = {
    "design_reader": "claude-sonnet-4-20250514",
    "planner": "claude-opus-4-20250514",
    "generator": "claude-sonnet-4-20250514",
    "triage": "claude-opus-4-20250514",
    "healer": "claude-sonnet-4-20250514",
}


def get_model(node_name: str) -> str:
    """Return the model ID for a given node, with env override support."""
    env_key = f"MODEL_{node_name.upper()}"
    return os.getenv(env_key, MODEL_MAP.get(node_name, "claude-sonnet-4-20250514"))


# ---------------------------------------------------------------------------
# Figma frame → app route mapping
# ---------------------------------------------------------------------------
class RouteMapping(BaseModel):
    route: str
    testid_prefix: str = ""


# Loaded from config or env; start empty, populated per-project
FIGMA_ROUTE_MAP: dict[str, RouteMapping] = {}


def load_figma_route_map(raw: dict[str, dict[str, Any]]) -> dict[str, RouteMapping]:
    """Parse a raw dict (from YAML/JSON config) into typed RouteMapping objects."""
    return {k: RouteMapping(**v) for k, v in raw.items()}


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------
class EnvConfig(BaseModel):
    """Typed access to environment variables."""

    anthropic_api_key: str = Field(default="")
    figma_token: str = Field(default="")
    jira_project_key: str = Field(default="QA")
    app_base_url: str = Field(default="http://localhost:3000")
    app_test_user: str = Field(default="")
    app_test_pass: str = Field(default="")
    langsmith_api_key: str = Field(default="")
    langsmith_project: str = Field(default="qa-agent")
    langsmith_tracing: bool = Field(default=True)

    @classmethod
    def from_env(cls) -> EnvConfig:
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            figma_token=os.getenv("FIGMA_TOKEN", ""),
            jira_project_key=os.getenv("JIRA_PROJECT_KEY", "QA"),
            app_base_url=os.getenv("APP_BASE_URL", "http://localhost:3000"),
            app_test_user=os.getenv("APP_TEST_USER", ""),
            app_test_pass=os.getenv("APP_TEST_PASS", ""),
            langsmith_api_key=os.getenv("LANGSMITH_API_KEY", ""),
            langsmith_project=os.getenv("LANGSMITH_PROJECT", "qa-agent"),
            langsmith_tracing=os.getenv("LANGSMITH_TRACING", "true").lower() == "true",
        )


def setup_langsmith() -> None:
    """Configure LangSmith tracing environment variables."""
    cfg = EnvConfig.from_env()
    if cfg.langsmith_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = cfg.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = cfg.langsmith_project


# ---------------------------------------------------------------------------
# Checkpointer path
# ---------------------------------------------------------------------------
CHECKPOINT_DB_PATH: str = str(_PROJECT_ROOT / "checkpoints.db")
