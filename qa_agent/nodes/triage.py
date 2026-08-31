"""Step 5 · Triage — judges a failed run: broken test vs broken app.

Rates its own confidence. When unsure, the graph routes to Human Review
instead of auto-healing.

Memory-enhanced: checks for similar past failures and injects human
calibration context into the prompt.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from qa_agent.audit import AuditStore
from qa_agent.confidence import score_confidence
from qa_agent.config import get_model
from qa_agent.memory import MemoryStore
from pathlib import Path

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "TRIAGE.md").read_text()
from qa_agent.state import QAState

logger = logging.getLogger(__name__)


async def triage(state: QAState) -> dict:
    """Classify a test failure and rate confidence.

    Memory-enhanced:
    1. Checks for similar past failures → fast classification hint
    2. Injects human calibration context → few-shot corrections
    """
    logger.info("Triage: analyzing failure for goal=%r", state.goal)

    memory = MemoryStore()

    # Check memory for similar past failure
    similar = None
    if state.error:
        similar = memory.find_similar_failure(state.error)
        if similar:
            logger.info(
                "Triage: found similar past failure %s (class=%s, resolution=%s)",
                similar.get("id"), similar.get("failure_class"), similar.get("resolution"),
            )

    # Build test stability context — has this test passed before?
    stability_context = _build_stability_context(state, memory)

    # Build calibration context from human decisions + lessons
    calibration_context = memory.build_triage_calibration_context()
    lessons_context = memory.build_lessons_context(max_tokens=250)
    if lessons_context:
        calibration_context = (calibration_context + "\n\n" + lessons_context).strip()

    # Pre-compute partial rubric score (C1, C3, C5 only — C2 and C4 need failure_class)
    # This gives the LLM a starting signal without biasing toward any classification
    from qa_agent.confidence import score_c1_error_type, score_c3_history_match, score_c5_consistency, ConfidenceBreakdown
    c1 = score_c1_error_type(state.error or "")
    c3 = score_c3_history_match(state.error or "", memory)
    c5 = score_c5_consistency(c1, 0.0, c3, 0.1)  # neutral C2=0, C4=0.1
    rubric_breakdown = ConfidenceBreakdown(
        c1_error_type=c1, c2_dom_evidence=0.0, c3_history_match=c3,
        c4_human_calibration=0.0, c5_consistency=c5,
        raw_score=round(c1 + c3 + c5, 2), final_score=round(c1 + c3 + c5, 2),
    )

    model = ChatAnthropic(
        model=get_model("triage"),
        temperature=0,
        max_tokens=2048,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_prompt(
            state,
            similar=similar,
            calibration=calibration_context,
            rubric_breakdown=rubric_breakdown.to_prompt_string(),
            stability_context=stability_context,
        )),
    ]

    response = await model.ainvoke(messages)
    AuditStore.record_llm_call(response, model=get_model("triage"))
    AuditStore.record_prompt_version(SYSTEM_PROMPT, "TRIAGE.md")
    AuditStore.record_prompt_data(
        raw_prompt=messages[-1].content,
        raw_response=response.content if hasattr(response, "content") else str(response),
    )
    AuditStore.record_memory_context(
        files_read=["FAILURES.md", "HUMAN_DECISIONS.md", "LESSONS.md"],
        similar_failures=1 if similar else 0,
        calibration_examples=calibration_context.count("| ") if calibration_context else 0,
    )
    result = _parse_response(response)

    failure_class = result.get("failure_class", "unknown")
    llm_confidence = result.get("confidence", 0.0)
    reasoning = result.get("reasoning", "")

    # Re-score with the LLM's chosen failure_class for accurate guard application
    final_breakdown = score_confidence(
        error=state.error or "",
        failure_class=failure_class,
        dom_snapshot=state.dom_snapshot,
        memory=memory,
    )

    # Use the rubric's final score, clamped to within ±0.05 of LLM's suggestion
    confidence = final_breakdown.final_score
    if abs(llm_confidence - confidence) <= 0.05:
        confidence = llm_confidence  # LLM is within rubric tolerance

    logger.info(
        "Triage: class=%s confidence=%.2f (rubric=%.2f, llm=%.2f) reason=%s",
        failure_class,
        confidence,
        final_breakdown.final_score,
        llm_confidence,
        reasoning[:100],
    )

    return {
        "failure_class": failure_class,
        "confidence": confidence,
        "reasoning": reasoning,
        "confidence_breakdown": final_breakdown.to_dict(),
    }


def _build_prompt(
    state: QAState,
    similar: dict[str, Any] | None = None,
    calibration: str = "",
    rubric_breakdown: str = "",
    stability_context: str = "",
) -> str:
    """Build the human message prompt for Triage."""
    parts = ["A test just failed. Analyze the failure and classify it.\n"]

    if state.error:
        parts.append("## Error message")
        parts.append(f"```\n{state.error}\n```\n")

    # Memory: similar past failure
    if similar:
        parts.append("## Memory: Similar past failure")
        parts.append(f"This error pattern has been seen before ({similar.get('occurrences', 1)} time(s)).")
        parts.append(f"Previous classification: **{similar.get('failure_class', 'unknown')}**")
        parts.append(f"Previous resolution: {similar.get('resolution', 'unknown')}")
        parts.append("Use this as a hint, but verify against the current evidence.\n")

    # Memory: test stability history
    if stability_context:
        parts.append(stability_context)
        parts.append("")

    # Memory: human calibration
    if calibration:
        parts.append(calibration)
        parts.append("")

    if state.run_results:
        parts.append("## Run results")
        parts.append(f"Passed: {state.run_results.passed}")
        if state.run_results.failed_cases:
            parts.append(f"Failed cases: {', '.join(state.run_results.failed_cases)}")
        if state.run_results.logs:
            logs = state.run_results.logs[:3000]
            parts.append(f"\n### Logs (truncated)\n```\n{logs}\n```\n")

    if state.dom_snapshot:
        snapshot = state.dom_snapshot[:2000]
        parts.append(f"## DOM snapshot (truncated)\n```html\n{snapshot}\n```\n")

    if state.expected_ui:
        parts.append("## Expected UI elements")
        for el in state.expected_ui.elements:
            parts.append(f"  - {el.role}: '{el.name}' (testid: {el.testid or 'none'})")

    parts.append(f"\nAttempts so far: {state.attempts}")

    # Rubric pre-score
    if rubric_breakdown:
        parts.append(f"\n## Pre-computed rubric score\n{rubric_breakdown}")
        parts.append("Use this as your starting point. Adjust within ±0.05 with justification.")

    return "\n".join(parts)


def _parse_response(response: Any) -> dict:
    """Parse the LLM response into failure_class + confidence."""
    content = response.content if hasattr(response, "content") else str(response)

    try:
        if isinstance(content, str):
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            data = json.loads(json_str.strip())
        elif isinstance(content, list):
            for block in content:
                if hasattr(block, "text"):
                    data = json.loads(block.text)
                    break
            else:
                data = {}
        else:
            data = json.loads(content)
    except (json.JSONDecodeError, IndexError):
        logger.error("Triage: could not parse JSON, defaulting to unknown/low confidence")
        data = {"failure_class": "unknown", "confidence": 0.0}

    fc = data.get("failure_class", "unknown")
    if fc not in ("locator_drift", "app_defect", "test_flake", "unknown"):
        fc = "unknown"

    conf = float(data.get("confidence", 0.0))
    conf = max(0.0, min(1.0, conf))

    return {
        "failure_class": fc,
        "confidence": conf,
        "reasoning": data.get("reasoning", ""),
    }


def _build_stability_context(state: QAState, memory: MemoryStore) -> str:
    """Build test stability context from historical data.

    Checks TEST_STABILITY.md for past pass/fail records and health reports
    for recent domain-level results. If a test has passed before, this is
    strong evidence that a current failure may be a flake, not a real defect.
    """
    parts = []

    # 1. Check TEST_STABILITY.md for this specific test
    if state.run_results and state.run_results.failed_cases:
        for failed_id in state.run_results.failed_cases:
            history = memory.get_test_history(failed_id)
            if history and history.get("runs", 0) > 0:
                parts.append("## Memory: Test execution history")
                parts.append(f"Test **{history['test_id']}** has been run **{history['runs']}** time(s):")
                parts.append(f"  - Passed: {history['passes']}, Failed: {history['fails']}")
                parts.append(f"  - Flakiness score: {history['flakiness']:.0%}")
                parts.append(f"  - Last run: {history['last_run']}, Last failure: {history['last_failure']}")
                if history['passes'] > 0 and history['fails'] > 0:
                    parts.append("  - **This test has PASSED before and FAILED before — intermittent failure pattern.**")
                    parts.append("  - Consider classifying as `test_flake` if the error is timing-related.")
                elif history['passes'] > 0 and history['fails'] == 0:
                    parts.append("  - This test has always passed before — first-time failure.")

    # 2. Check health reports for recent domain pass/fail history
    goal = state.goal or ""
    spec_file = ""
    if ":" in goal:
        for p in goal.split(":"):
            if p.endswith(".spec.ts"):
                spec_file = p
                break

    if spec_file:
        domain_history = _get_domain_history_from_health_reports(spec_file)
        if domain_history:
            parts.append("## Memory: Recent domain health history")
            parts.append(f"Spec file **{spec_file}** recent results:")
            for entry in domain_history[-5:]:
                parts.append(f"  - {entry['run_id']}: {entry['passed']}/{entry['total']} passed ({entry['status']})")
            total_runs = len(domain_history)
            full_passes = sum(1 for e in domain_history if e['failed'] == 0)
            if full_passes > 0 and any(e['failed'] > 0 for e in domain_history):
                parts.append(f"  - **Passed fully in {full_passes}/{total_runs} recent runs — intermittent pattern.**")
                parts.append("  - If the failure is not a clear app defect, consider `test_flake`.")

    return "\n".join(parts) if parts else ""


def _get_domain_history_from_health_reports(spec_file: str, lookback: int = 10) -> list[dict]:
    """Get recent health report results for the domain corresponding to a spec file."""
    import json as _json

    health_dir = Path(__file__).resolve().parent.parent.parent / "health-reports"
    if not health_dir.exists():
        return []

    # Derive domain name from spec file name
    # e.g., "cart.spec.ts" → "Cart", "rvs-for-sale.spec.ts" → "Rvs For Sale"
    base = spec_file.replace(".spec.ts", "")
    # Convert kebab-case to title case: "rvs-for-sale" → "Rvs For Sale"
    domain_name = " ".join(word.capitalize() for word in base.split("-"))

    files = sorted(health_dir.glob("*.json"))
    recent = [f for f in files if "-triage" not in f.stem][-lookback:]

    results = []
    for f in recent:
        try:
            data = _json.load(open(f))
            for dom in data.get("domains", []):
                if dom.get("name") == domain_name:
                    results.append({
                        "run_id": data.get("run_id", f.stem),
                        "passed": dom.get("passed", 0),
                        "failed": dom.get("failed", 0),
                        "total": dom.get("total", 0),
                        "status": dom.get("status", "UNKNOWN"),
                    })
                    break
        except Exception:
            continue
    return results
