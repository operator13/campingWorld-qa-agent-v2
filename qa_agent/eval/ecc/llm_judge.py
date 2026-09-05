"""LLM-as-judge for scoring generative ECC agent output quality."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

RUBRIC_DIMENSIONS = [
    "completeness",
    "actionability",
    "correctness",
    "risk_awareness",
    "convention_adherence",
]

JUDGE_SYSTEM_PROMPT = """\
You are an expert evaluator scoring the quality of an AI agent's output.
You will receive:
1. The original task/scenario description
2. The agent's output
3. A scoring rubric

Score each dimension from 1-5:
1 = Very poor / missing
2 = Below average / partially addressed
3 = Adequate / meets basic expectations
4 = Good / above average
5 = Excellent / comprehensive

Respond with ONLY a JSON object, no other text:
{
  "completeness": <1-5>,
  "actionability": <1-5>,
  "correctness": <1-5>,
  "risk_awareness": <1-5>,
  "convention_adherence": <1-5>,
  "reasoning": "<brief explanation for each score>"
}
"""

RUBRIC_DESCRIPTIONS = {
    "completeness": "Does the output cover all requirements? (1=missing most, 5=all covered)",
    "actionability": "Are steps specific enough to implement? (1=vague, 5=exact file paths and code changes)",
    "correctness": "Is the approach technically sound? (1=wrong approach, 5=optimal)",
    "risk_awareness": "Are risks and edge cases identified? (1=none, 5=comprehensive)",
    "convention_adherence": "Does output follow project conventions? (1=ignores, 5=fully aligned)",
}


@dataclass(frozen=True)
class JudgeScore:
    """Result of LLM judge evaluation."""

    scores: dict[str, int]  # dimension -> 1-5 score
    normalized_score: float  # 0.0 to 1.0
    reasoning: str
    raw_response: str
    error: str | None


def _build_judge_prompt(
    scenario_description: str,
    agent_output: str,
    acceptance_criteria: list[str] | None = None,
) -> str:
    """Build the prompt to send to the LLM judge."""
    prompt = f"## Task/Scenario\n\n{scenario_description}\n\n"

    if acceptance_criteria:
        prompt += "## Acceptance Criteria\n\n"
        for ac in acceptance_criteria:
            prompt += f"- {ac}\n"
        prompt += "\n"

    prompt += f"## Agent Output\n\n{agent_output}\n\n"

    prompt += "## Scoring Rubric\n\n"
    for dim, desc in RUBRIC_DESCRIPTIONS.items():
        prompt += f"- **{dim}**: {desc}\n"

    prompt += "\nScore each dimension 1-5 and respond with ONLY the JSON object."
    return prompt


def _parse_judge_response(response_text: str) -> tuple[dict[str, int], str]:
    """Parse the judge's JSON response into scores and reasoning."""
    # Try to extract JSON from the response
    text = response_text.strip()

    # Handle markdown code blocks
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    parsed = json.loads(text)

    scores = {}
    for dim in RUBRIC_DIMENSIONS:
        val = parsed.get(dim, 3)
        scores[dim] = max(1, min(5, int(val)))

    reasoning = parsed.get("reasoning", "")
    return scores, reasoning


async def judge_output(
    scenario_description: str,
    agent_output: str,
    acceptance_criteria: list[str] | None = None,
) -> JudgeScore:
    """Score a generative agent's output using an LLM judge.

    Uses Claude Haiku for cost-effective scoring.

    Args:
        scenario_description: What the agent was asked to do.
        agent_output: The agent's response text.
        acceptance_criteria: Optional list of criteria to evaluate against.

    Returns:
        JudgeScore with per-dimension scores and normalized total.
    """
    from dotenv import load_dotenv
    load_dotenv()

    prompt = _build_judge_prompt(scenario_description, agent_output, acceptance_criteria)

    try:
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            max_tokens=500,
            temperature=0,
        )

        response = await llm.ainvoke([
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])

        raw = response.content if hasattr(response, "content") else str(response)
        scores, reasoning = _parse_judge_response(raw)

        # Normalize: average of 5 dimensions, mapped from 1-5 to 0-1
        avg = sum(scores.values()) / len(scores)
        normalized = (avg - 1) / 4  # 1->0.0, 5->1.0

        return JudgeScore(
            scores=scores,
            normalized_score=round(normalized, 4),
            reasoning=reasoning,
            raw_response=raw,
            error=None,
        )

    except json.JSONDecodeError as e:
        logger.error("Judge response was not valid JSON: %s", e)
        return JudgeScore(
            scores={d: 1 for d in RUBRIC_DIMENSIONS},
            normalized_score=0.0,
            reasoning="",
            raw_response=raw if "raw" in dir() else "",
            error=f"Invalid JSON from judge: {e}",
        )
    except Exception as e:
        logger.error("LLM judge failed: %s", e)
        return JudgeScore(
            scores={d: 1 for d in RUBRIC_DIMENSIONS},
            normalized_score=0.0,
            reasoning="",
            raw_response="",
            error=str(e),
        )
