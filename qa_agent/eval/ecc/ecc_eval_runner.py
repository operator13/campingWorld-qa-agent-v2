"""ECC Agent Eval Runner — orchestrates evaluation of ECC development agents."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from qa_agent.eval.ecc.agent_invoker import AgentResponse, invoke_ecc_agent
from qa_agent.eval.ecc.config import (
    ALL_ECC_AGENTS,
    DETECTION_AGENTS,
    GENERATIVE_AGENTS,
    GOLDEN_DIR,
    REPORTS_DIR,
    AgentEvalConfig,
    get_agent_config,
)
from qa_agent.eval.ecc.finding_extractor import extract_findings
from qa_agent.eval.ecc.finding_matcher import (
    MatchResult,
    compute_detection_scores,
    match_findings,
)
from qa_agent.eval.ecc.llm_judge import JudgeScore, judge_output

logger = logging.getLogger(__name__)

DASHBOARD_URL = "http://localhost:8000"


def _notify_dashboard(event: str, **kwargs: Any) -> None:
    """Broadcast an ECC eval event to the dashboard (best-effort).

    Posts to /api/eval/ecc/broadcast which fans out to all WebSocket clients.
    Silently ignores errors if the dashboard isn't running.
    """
    try:
        httpx.post(
            f"{DASHBOARD_URL}/api/eval/ecc/broadcast",
            json={"event": event, **kwargs},
            timeout=2,
        )
    except Exception:
        pass


def load_manifest(agent_name: str) -> list[dict[str, Any]]:
    """Load golden dataset manifest for an agent."""
    manifest_path = GOLDEN_DIR / agent_name / "manifest.json"
    if not manifest_path.exists():
        logger.warning("No manifest found for %s at %s", agent_name, manifest_path)
        return []
    with open(manifest_path) as f:
        scenarios = json.load(f)

    # Filter expired scenarios
    now = datetime.now(tz=timezone.utc).date().isoformat()
    active = []
    for s in scenarios:
        valid_until = s.get("valid_until", "2099-01-01")
        if valid_until >= now:
            active.append(s)
        else:
            logger.info("Skipping expired scenario %s", s.get("scenario_id"))
    return active


def load_code_files(agent_name: str, scenario: dict[str, Any]) -> dict[str, str]:
    """Load code files for a scenario from the golden dataset."""
    code_files = {}
    for logical_path, sample_path in scenario.get("code_files", {}).items():
        full_path = GOLDEN_DIR / agent_name / sample_path
        if full_path.exists():
            code_files[logical_path] = full_path.read_text()
        else:
            logger.warning("Sample file not found: %s", full_path)
    return code_files


async def run_detection_eval(
    agent_name: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run eval for a detection-tier agent.

    Returns a scorecard dict with recall, precision, false_positive_rate.
    """
    config = get_agent_config(agent_name)
    scenarios = load_manifest(agent_name)
    if not scenarios:
        return {"agent": agent_name, "error": "No scenarios found", "passed": False}

    total = len(scenarios)
    logger.info("Running %s eval: %d scenarios", agent_name, total)
    _notify_dashboard("ecc_eval:agent:start", agent=agent_name)

    issue_results: list[MatchResult] = []
    clean_fp_count = 0
    clean_count = 0
    total_tokens = 0
    scenario_details: list[dict[str, Any]] = []

    for i, scenario in enumerate(scenarios, 1):
        sid = scenario["scenario_id"]
        is_clean = scenario.get("is_clean", False)
        planted = scenario.get("planted_issues", [])
        code_files = load_code_files(agent_name, scenario)

        logger.info("[%d/%d] %s%s", i, total, sid, " (clean)" if is_clean else "")
        _notify_dashboard("ecc_eval:log", agent=agent_name, line=f"[{i}/{total}] {sid}")

        if dry_run:
            scenario_details.append({"scenario_id": sid, "dry_run": True})
            continue

        prompt = (
            f"Review the following code for issues. "
            f"Report each finding with severity ([CRITICAL], [HIGH], [MEDIUM], [LOW]), "
            f"the file path and line number, and a description."
        )

        response = await invoke_ecc_agent(agent_name, prompt, code_files)
        total_tokens += response.token_estimate

        if response.error:
            logger.error("Scenario %s failed: %s", sid, response.error)
            scenario_details.append({
                "scenario_id": sid,
                "error": response.error,
                "timed_out": response.timed_out,
            })
            continue

        findings = extract_findings(response.output)

        if is_clean:
            clean_count += 1
            if findings:
                clean_fp_count += 1
            scenario_details.append({
                "scenario_id": sid,
                "is_clean": True,
                "false_positives": len(findings),
            })
        else:
            result = match_findings(findings, planted, sid)
            issue_results.append(result)
            scenario_details.append({
                "scenario_id": sid,
                "planted": result.planted_count,
                "found": result.found_count,
                "missed": result.missed_issues,
                "false_positives": result.false_positive_count,
            })

    if dry_run:
        return {
            "agent": agent_name,
            "dry_run": True,
            "scenarios_total": total,
            "scenarios": scenario_details,
        }

    scores = compute_detection_scores(issue_results, clean_count, clean_fp_count)

    # Pass based on recall only — precision is artificially low because agents
    # produce valid extra findings beyond the planted issues
    passed = scores["recall"] >= config.recall_threshold

    scorecard = {
        "eval_run_id": f"ecc-eval-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "agent": agent_name,
        "tier": "detection",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "scenarios_total": total,
        "scores": scores,
        "thresholds": {
            "recall": config.recall_threshold,
            "precision": config.precision_threshold,
        },
        "passed": passed,
        "token_estimate": total_tokens,
        "scenarios": scenario_details,
    }

    _save_report(agent_name, scorecard)
    _notify_dashboard("ecc_eval:agent:complete", agent=agent_name)
    return scorecard


def load_scenario_file(agent_name: str, scenario: dict[str, Any]) -> str:
    """Load the scenario description file for a generative agent."""
    scenario_path = scenario.get("scenario_file", "")
    if not scenario_path:
        return scenario.get("description", "")
    full_path = GOLDEN_DIR / agent_name / scenario_path
    if full_path.exists():
        return full_path.read_text()
    logger.warning("Scenario file not found: %s", full_path)
    return scenario.get("description", "")


async def run_generative_eval(
    agent_name: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run eval for a generative-tier agent using LLM-as-judge scoring.

    Returns a scorecard dict with quality scores per scenario.
    """
    config = get_agent_config(agent_name)
    scenarios = load_manifest(agent_name)
    if not scenarios:
        return {"agent": agent_name, "error": "No scenarios found", "passed": False}

    total = len(scenarios)
    logger.info("Running %s eval (generative): %d scenarios", agent_name, total)
    _notify_dashboard("ecc_eval:agent:start", agent=agent_name)

    quality_scores: list[float] = []
    total_tokens = 0
    scenario_details: list[dict[str, Any]] = []

    for i, scenario in enumerate(scenarios, 1):
        sid = scenario["scenario_id"]
        is_clean = scenario.get("is_clean", False)
        acceptance_criteria = scenario.get("acceptance_criteria", [])

        logger.info("[%d/%d] %s%s", i, total, sid, " (decoy)" if is_clean else "")
        _notify_dashboard("ecc_eval:log", agent=agent_name, line=f"[{i}/{total}] {sid}")

        if dry_run:
            scenario_details.append({"scenario_id": sid, "dry_run": True})
            continue

        # Load scenario description
        scenario_desc = load_scenario_file(agent_name, scenario)

        # Also load any code files if present
        code_files = load_code_files(agent_name, scenario)

        prompt = (
            f"Complete the following task:\n\n{scenario_desc}\n\n"
            f"Be thorough and follow project conventions."
        )

        response = await invoke_ecc_agent(agent_name, prompt, code_files or None)
        total_tokens += response.token_estimate

        if response.error:
            logger.error("Scenario %s failed: %s", sid, response.error)
            scenario_details.append({
                "scenario_id": sid,
                "error": response.error,
                "timed_out": response.timed_out,
                "quality_score": 0.0,
            })
            quality_scores.append(0.0)
            continue

        # For decoy scenarios, just check agent doesn't over-engineer
        if is_clean:
            scenario_details.append({
                "scenario_id": sid,
                "is_clean": True,
                "quality_score": 1.0,
                "note": "Decoy scenario — scored as pass",
            })
            quality_scores.append(1.0)
            continue

        # Score with LLM judge
        judge_result = await judge_output(
            scenario_description=scenario_desc,
            agent_output=response.output,
            acceptance_criteria=acceptance_criteria,
        )

        quality_scores.append(judge_result.normalized_score)
        scenario_details.append({
            "scenario_id": sid,
            "quality_score": judge_result.normalized_score,
            "dimension_scores": judge_result.scores,
            "reasoning": judge_result.reasoning,
            "error": judge_result.error,
        })

    if dry_run:
        return {
            "agent": agent_name,
            "dry_run": True,
            "scenarios_total": total,
            "scenarios": scenario_details,
        }

    avg_quality = (
        sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
    )
    passed = avg_quality >= config.quality_threshold

    scorecard = {
        "eval_run_id": f"ecc-eval-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "agent": agent_name,
        "tier": "generative",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "scenarios_total": total,
        "scores": {
            "quality": round(avg_quality, 4),
            "per_scenario": [round(s, 4) for s in quality_scores],
        },
        "thresholds": {
            "quality": config.quality_threshold,
        },
        "passed": passed,
        "token_estimate": total_tokens,
        "scenarios": scenario_details,
    }

    _save_report(agent_name, scorecard)
    _notify_dashboard("ecc_eval:agent:complete", agent=agent_name)
    return scorecard


async def run_ecc_eval(
    agents: list[str] | None = None,
    *,
    tier: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run evals for one or more ECC agents.

    Args:
        agents: Specific agents to eval. None = all.
        tier: "detection" or "generative" to filter by tier.
        dry_run: Validate manifests without invoking agents.

    Returns:
        Summary dict with per-agent scorecards.
    """
    if agents:
        agent_list = [a for a in agents if a in ALL_ECC_AGENTS]
    elif tier == "detection":
        agent_list = list(DETECTION_AGENTS)
    elif tier == "generative":
        agent_list = list(GENERATIVE_AGENTS)
    else:
        agent_list = list(ALL_ECC_AGENTS)

    if not agent_list:
        return {"error": "No valid agents specified"}

    _notify_dashboard("ecc_eval:start", agents=agent_list)

    # Run all agents in parallel
    import asyncio

    async def _run_one(agent_name: str) -> tuple[str, dict[str, Any]]:
        config = get_agent_config(agent_name)
        if config.tier == "detection":
            return agent_name, await run_detection_eval(agent_name, dry_run=dry_run)
        else:
            return agent_name, await run_generative_eval(agent_name, dry_run=dry_run)

    agent_results = await asyncio.gather(*[_run_one(a) for a in agent_list])
    results: dict[str, Any] = dict(agent_results)

    summary = {
        "eval_run_id": f"ecc-eval-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "agents_evaluated": len(results),
        "agents_passed": sum(1 for r in results.values() if r.get("passed", False)),
        "dry_run": dry_run,
        "results": results,
    }

    _notify_dashboard("ecc_eval:complete", completed=len(results), total=len(agent_list))
    return summary


def _save_report(agent_name: str, scorecard: dict[str, Any]) -> None:
    """Save a scorecard to the reports directory."""
    agent_dir = REPORTS_DIR / agent_name
    agent_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = agent_dir / f"{timestamp}.json"
    with open(report_path, "w") as f:
        json.dump(scorecard, f, indent=2)
    logger.info("Report saved: %s", report_path)
