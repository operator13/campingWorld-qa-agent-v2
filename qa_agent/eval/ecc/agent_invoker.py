"""Invoke ECC agents via Claude Code CLI and capture output."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from qa_agent.eval.ecc.config import AGENT_FILE_MAP, PROJECT_ROOT, SCENARIO_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentResponse:
    """Captured response from an ECC agent invocation."""

    agent_name: str
    output: str
    exit_code: int
    timed_out: bool
    token_estimate: int
    error: str | None


async def invoke_ecc_agent(
    agent_name: str,
    prompt: str,
    code_files: dict[str, str] | None = None,
    *,
    timeout_seconds: int = SCENARIO_TIMEOUT_SECONDS,
) -> AgentResponse:
    """Invoke an ECC agent via Claude Code CLI and capture its output."""
    agent_file = AGENT_FILE_MAP.get(agent_name, agent_name)

    with tempfile.TemporaryDirectory(prefix=f"ecc_eval_{agent_name}_") as tmpdir:
        if code_files:
            for filename, content in code_files.items():
                filepath = Path(tmpdir) / filename
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content)

        full_prompt = prompt
        if code_files:
            full_prompt += "\n\n## Files to review:\n\n"
            for filename, content in code_files.items():
                full_prompt += f"### `{filename}`\n```\n{content}\n```\n\n"

        cmd = ["claude", "--agent", agent_file, "--print", "--output-format", "text"]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(PROJECT_ROOT),
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=full_prompt.encode("utf-8")),
                timeout=timeout_seconds,
            )

            output = stdout.decode("utf-8", errors="replace")
            error_output = stderr.decode("utf-8", errors="replace").strip()
            token_estimate = (len(full_prompt) + len(output)) // 4

            return AgentResponse(
                agent_name=agent_name,
                output=output,
                exit_code=proc.returncode or 0,
                timed_out=False,
                token_estimate=token_estimate,
                error=error_output if error_output and proc.returncode != 0 else None,
            )

        except asyncio.TimeoutError:
            logger.warning("Agent %s timed out after %ds", agent_name, timeout_seconds)
            try:
                proc.kill()
            except Exception:
                pass
            return AgentResponse(
                agent_name=agent_name,
                output="",
                exit_code=-1,
                timed_out=True,
                token_estimate=0,
                error=f"Timed out after {timeout_seconds}s",
            )
        except FileNotFoundError:
            logger.error("Claude CLI not found")
            return AgentResponse(
                agent_name=agent_name,
                output="",
                exit_code=-1,
                timed_out=False,
                token_estimate=0,
                error="Claude CLI not found",
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
