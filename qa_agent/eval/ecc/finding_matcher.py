"""Match extracted findings against planted issue manifests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from qa_agent.eval.ecc.config import (
    CATEGORY_OVERLAP_THRESHOLD,
    LINE_PROXIMITY_THRESHOLD,
)
from qa_agent.eval.ecc.finding_extractor import Finding


@dataclass(frozen=True)
class FindingMatch:
    """Result of matching a finding against a planted issue."""

    planted_issue_id: str
    agent_finding: Finding
    file_match: bool
    line_proximity: int
    category_overlap: float
    matched: bool


@dataclass(frozen=True)
class MatchResult:
    """Aggregate match results for a single scenario."""

    scenario_id: str
    planted_count: int
    found_count: int
    false_positive_count: int
    matches: list[FindingMatch]
    unmatched_findings: list[Finding]
    missed_issues: list[str]


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/").lower()


def _keyword_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9_]+", text.lower()))


def _category_overlap(planted_category: str, finding_desc: str) -> float:
    planted_keywords = _keyword_set(planted_category)
    finding_keywords = _keyword_set(finding_desc)
    if not planted_keywords:
        return 0.0
    return len(planted_keywords & finding_keywords) / len(planted_keywords)


def match_findings(
    findings: list[Finding],
    planted_issues: list[dict[str, Any]],
    scenario_id: str,
) -> MatchResult:
    """Match extracted findings against planted issues for a scenario."""
    matched_issue_ids: set[str] = set()
    matched_finding_indices: set[int] = set()
    all_matches: list[FindingMatch] = []

    for issue in planted_issues:
        issue_id = issue["issue_id"]
        issue_file = issue.get("file", "")
        issue_line_range = issue.get("line_range", [0, 0])
        issue_category = issue.get("category", "")
        issue_desc = issue.get("description", "")
        combined_category = f"{issue_category} {issue_desc}"

        for i, finding in enumerate(findings):
            if i in matched_finding_indices:
                continue

            file_match = False
            if finding.file and issue_file:
                norm_finding = _normalize_path(finding.file)
                norm_issue = _normalize_path(issue_file)
                file_match = (
                    norm_finding == norm_issue
                    or norm_finding.endswith(norm_issue)
                    or norm_issue.endswith(norm_finding)
                )

            line_proximity = 999
            if finding.line is not None and issue_line_range:
                line_start = issue_line_range[0]
                line_end = issue_line_range[1] if len(issue_line_range) > 1 else line_start
                if line_start <= finding.line <= line_end:
                    line_proximity = 0
                else:
                    line_proximity = min(
                        abs(finding.line - line_start),
                        abs(finding.line - line_end),
                    )

            overlap = _category_overlap(
                combined_category,
                f"{finding.description} {finding.raw_text}",
            )

            matched = False
            if file_match and line_proximity <= LINE_PROXIMITY_THRESHOLD:
                matched = True
            elif file_match and overlap >= CATEGORY_OVERLAP_THRESHOLD:
                matched = True
            elif overlap >= CATEGORY_OVERLAP_THRESHOLD and line_proximity <= LINE_PROXIMITY_THRESHOLD:
                matched = True
            elif not issue_file and overlap >= CATEGORY_OVERLAP_THRESHOLD:
                matched = True

            match = FindingMatch(
                planted_issue_id=issue_id,
                agent_finding=finding,
                file_match=file_match,
                line_proximity=line_proximity,
                category_overlap=overlap,
                matched=matched,
            )
            all_matches.append(match)

            if matched:
                matched_issue_ids.add(issue_id)
                matched_finding_indices.add(i)
                break

    unmatched = [f for i, f in enumerate(findings) if i not in matched_finding_indices]
    all_issue_ids = {issue["issue_id"] for issue in planted_issues}
    missed = sorted(all_issue_ids - matched_issue_ids)

    return MatchResult(
        scenario_id=scenario_id,
        planted_count=len(planted_issues),
        found_count=len(matched_issue_ids),
        false_positive_count=len(unmatched),
        matches=[m for m in all_matches if m.matched],
        unmatched_findings=unmatched,
        missed_issues=missed,
    )


def compute_detection_scores(
    results: list[MatchResult],
    clean_scenario_count: int = 0,
    clean_false_positives: int = 0,
) -> dict[str, float]:
    """Compute aggregate detection scores from multiple scenario results."""
    total_planted = sum(r.planted_count for r in results)
    total_found = sum(r.found_count for r in results)
    total_fp = sum(r.false_positive_count for r in results)

    recall = total_found / total_planted if total_planted > 0 else 0.0
    precision = (
        total_found / (total_found + total_fp)
        if (total_found + total_fp) > 0
        else 0.0
    )
    fp_rate = (
        clean_false_positives / clean_scenario_count
        if clean_scenario_count > 0
        else 0.0
    )

    return {
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "false_positive_rate": round(fp_rate, 4),
        "total_planted": total_planted,
        "total_found": total_found,
        "total_false_positives": total_fp,
    }
