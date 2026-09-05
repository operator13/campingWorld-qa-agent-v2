"""Invoke ECC agents via Anthropic API using agent system prompts."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from qa_agent.eval.ecc.config import AGENT_FILE_MAP, PROJECT_ROOT, SCENARIO_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# Agent definition directory
AGENTS_DIR = PROJECT_ROOT / ".claude" / "agents"

# Model mapping from agent frontmatter shorthand to full model ID
MODEL_MAP = {
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}


@dataclass(frozen=True)
class AgentResponse:
    """Captured response from an ECC agent invocation."""

    agent_name: str
    output: str
    exit_code: int
    timed_out: bool
    token_estimate: int
    error: str | None


def _load_agent_prompt(agent_name: str) -> tuple[str, str]:
    """Load agent system prompt and model from .claude/agents/{name}.md.

    Returns:
        Tuple of (system_prompt, model_id).
    """
    agent_file = AGENT_FILE_MAP.get(agent_name, agent_name)
    agent_path = AGENTS_DIR / f"{agent_file}.md"

    if not agent_path.exists():
        raise FileNotFoundError(f"Agent definition not found: {agent_path}")

    content = agent_path.read_text()

    # Parse YAML frontmatter
    model = "sonnet"
    system_prompt = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            system_prompt = parts[2].strip()
            for line in frontmatter.strip().split("\n"):
                if line.startswith("model:"):
                    model = line.split(":", 1)[1].strip()

    model_id = MODEL_MAP.get(model, model)
    return system_prompt, model_id


async def invoke_ecc_agent(
    agent_name: str,
    prompt: str,
    code_files: dict[str, str] | None = None,
    *,
    timeout_seconds: int = SCENARIO_TIMEOUT_SECONDS,
) -> AgentResponse:
    """Invoke an ECC agent via Anthropic API using the agent's system prompt.

    Reads the agent definition from .claude/agents/{name}.md, extracts the
    system prompt and model, then calls the Anthropic API directly.
    """
    try:
        system_prompt, model_id = _load_agent_prompt(agent_name)
    except FileNotFoundError as e:
        return AgentResponse(
            agent_name=agent_name,
            output="",
            exit_code=-1,
            timed_out=False,
            token_estimate=0,
            error=str(e),
        )

    # Build user message with code files
    user_message = prompt
    if code_files:
        user_message += "\n\n## Files to review:\n\n"
        for filename, content in code_files.items():
            user_message += f"### `{filename}`\n```\n{content}\n```\n\n"

    try:
        from langchain_anthropic import ChatAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return AgentResponse(
                agent_name=agent_name,
                output="",
                exit_code=-1,
                timed_out=False,
                token_estimate=0,
                error="ANTHROPIC_API_KEY not set",
            )

        llm = ChatAnthropic(
            model=model_id,
            anthropic_api_key=api_key,
            max_tokens=4096,
            timeout=float(timeout_seconds),
        )

        response = await llm.ainvoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ])

        output = response.content if hasattr(response, "content") else str(response)

        # Extract token usage if available
        token_estimate = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            token_estimate = (
                (response.usage_metadata.get("input_tokens", 0) or 0)
                + (response.usage_metadata.get("output_tokens", 0) or 0)
            )
        if not token_estimate:
            token_estimate = (len(user_message) + len(output)) // 4

        return AgentResponse(
            agent_name=agent_name,
            output=output,
            exit_code=0,
            timed_out=False,
            token_estimate=token_estimate,
            error=None,
        )

    except TimeoutError:
        logger.warning("Agent %s timed out after %ds", agent_name, timeout_seconds)
        return AgentResponse(
            agent_name=agent_name,
            output="",
            exit_code=-1,
            timed_out=True,
            token_estimate=0,
            error=f"Timed out after {timeout_seconds}s",
        )
    except Exception as e:
        logger.error("Agent %s invocation failed: %s", agent_name, e)
        return AgentResponse(
            agent_name=agent_name,
            output="",
            exit_code=-1,
            timed_out=False,
            token_estimate=0,
            error=str(e),
        )
