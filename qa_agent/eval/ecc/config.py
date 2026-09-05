"""ECC eval configuration — thresholds, budget caps, model map, timeouts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ECC_EVAL_ROOT = Path(__file__).resolve().parent
GOLDEN_DIR = ECC_EVAL_ROOT / "golden"
REPORTS_DIR = ECC_EVAL_ROOT / "reports"
PROJECT_ROOT = ECC_EVAL_ROOT.parent.parent.parent

# ---------------------------------------------------------------------------
# Agent tiers
# ---------------------------------------------------------------------------

DETECTION_AGENTS = [
    "security-reviewer",
    "code-reviewer",
    "silent-failure-hunter",
    "python-reviewer",
    "typescript-reviewer",
    "fastapi-reviewer",
    "performance-optimizer",
]

GENERATIVE_AGENTS = [
    "planner-ecc",
    "tdd-guide",
    "build-error-resolver",
    "e2e-runner",
    "refactor-cleaner",
]

ALL_ECC_AGENTS = DETECTION_AGENTS + GENERATIVE_AGENTS

# Maps eval agent name -> .claude/agents/ filename (without .md)
AGENT_FILE_MAP: dict[str, str] = {
    "security-reviewer": "security-reviewer",
    "code-reviewer": "code-reviewer",
    "silent-failure-hunter": "silent-failure-hunter",
    "python-reviewer": "python-reviewer",
    "typescript-reviewer": "typescript-reviewer",
    "fastapi-reviewer": "fastapi-reviewer",
    "performance-optimizer": "performance-optimizer",
    "planner-ecc": "planner",
    "tdd-guide": "tdd-guide",
    "build-error-resolver": "build-error-resolver",
    "e2e-runner": "e2e-runner",
    "refactor-cleaner": "refactor-cleaner",
}

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

RECALL_THRESHOLDS: dict[str, float] = {
    "security-reviewer": 0.90,  # Baseline: 100% x3, spread 0pt
    "code-reviewer": 0.70,  # Baseline: 75-100%, spread 25pt (extraction variance)
    "silent-failure-hunter": 0.95,  # Baseline: 100% x3, spread 0pt
    "python-reviewer": 0.95,  # Baseline: 100% x3, spread 0pt
    "typescript-reviewer": 0.95,  # Baseline: 100% x3, spread 0pt
    "fastapi-reviewer": 0.66,  # Baseline: 71-86%, spread 14pt (extraction variance)
    "performance-optimizer": 0.81,  # Baseline: 86-100%, spread 14pt
}

PRECISION_THRESHOLD = 0.80
SEVERITY_ACCURACY_THRESHOLD = 0.70
FALSE_POSITIVE_RATE_THRESHOLD = 0.20
GENERATIVE_QUALITY_THRESHOLD = 0.70

# ---------------------------------------------------------------------------
# Budget & execution
# ---------------------------------------------------------------------------

SCENARIO_TIMEOUT_SECONDS = 120
MAX_PARALLEL_SCENARIOS = 3

BUDGET_CAPS: dict[str, float] = {
    "security-reviewer": 0.96,
    "code-reviewer": 0.72,
    "silent-failure-hunter": 0.54,
    "python-reviewer": 0.58,
    "typescript-reviewer": 0.58,
    "fastapi-reviewer": 0.48,
    "performance-optimizer": 0.36,
    "planner-ecc": 3.60,
    "tdd-guide": 0.48,
    "build-error-resolver": 0.36,
    "e2e-runner": 0.48,
    "refactor-cleaner": 0.36,
}

# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

LINE_PROXIMITY_THRESHOLD = 5
CATEGORY_OVERLAP_THRESHOLD = 0.30


@dataclass(frozen=True)
class AgentEvalConfig:
    """Per-agent eval configuration."""

    name: str
    tier: str  # "detection" or "generative"
    recall_threshold: float = 0.75
    precision_threshold: float = PRECISION_THRESHOLD
    quality_threshold: float = GENERATIVE_QUALITY_THRESHOLD
    budget_cap: float = 1.00
    timeout_seconds: int = SCENARIO_TIMEOUT_SECONDS


def get_agent_config(agent_name: str) -> AgentEvalConfig:
    """Return the eval config for a given agent."""
    tier = "detection" if agent_name in DETECTION_AGENTS else "generative"
    return AgentEvalConfig(
        name=agent_name,
        tier=tier,
        recall_threshold=RECALL_THRESHOLDS.get(agent_name, 0.75),
        budget_cap=BUDGET_CAPS.get(agent_name, 1.00),
    )
