"""Site Health Score — computes per-domain and overall health from Playwright test results.

Parses Playwright JSON reporter output, groups by domain (spec file),
applies critical path weighting, and produces a health scorecard.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TEST_RESULTS_DIR = Path(__file__).resolve().parent.parent / "test-results"

# Critical path domains get higher weight — failures here impact revenue
DOMAIN_WEIGHTS: dict[str, float] = {
    "Cart": 2.0,
    "Checkout": 2.0,
    "Checkout Flow": 2.0,
    "Sign In": 1.5,
    "Search": 1.5,
    "Search Functionality": 1.5,
    "Product Detail Page": 1.5,
    "RV Detail Page": 1.5,
    "Footer & Legal Pages": 0.5,
}

CRITICAL_DOMAINS = {"Cart", "Checkout", "Checkout Flow", "Sign In"}

# Status thresholds
_HEALTHY_THRESHOLD = 0.95
_DEGRADED_THRESHOLD = 0.80


def parse_playwright_json(json_path: Path) -> list[dict[str, Any]]:
    """Parse Playwright JSON reporter output into per-domain results.

    Returns list of:
        {"name": "Homepage", "passed": 13, "failed": 0, "skipped": 0, "total": 13, "duration_ms": 5000}
    """
    with open(json_path) as f:
        data = json.load(f)

    domains: dict[str, dict[str, int]] = {}

    for suite in data.get("suites", []):
        domain_name = suite.get("title", "Unknown")
        # Clean up domain name — remove file extension if present
        if domain_name.endswith(".spec.ts"):
            domain_name = domain_name.replace(".spec.ts", "").replace("-", " ").title()

        if domain_name not in domains:
            domains[domain_name] = {"passed": 0, "failed": 0, "skipped": 0, "duration_ms": 0}

        # Walk nested suites (some specs have nested describe blocks)
        _count_specs(suite, domains, domain_name)

    results = []
    for name, counts in sorted(domains.items()):
        total = counts["passed"] + counts["failed"] + counts["skipped"]
        results.append({
            "name": name,
            "passed": counts["passed"],
            "failed": counts["failed"],
            "skipped": counts["skipped"],
            "total": total,
            "duration_ms": counts["duration_ms"],
        })

    return results


def _count_specs(suite: dict, domains: dict, domain_name: str) -> None:
    """Recursively count pass/fail/skip in a suite and its children."""
    for spec in suite.get("specs", []):
        for test in spec.get("tests", []):
            status = test.get("status", "unexpected")
            duration = test.get("results", [{}])[0].get("duration", 0) if test.get("results") else 0
            domains[domain_name]["duration_ms"] += duration

            if status == "expected":
                domains[domain_name]["passed"] += 1
            elif status == "skipped":
                domains[domain_name]["skipped"] += 1
            else:
                domains[domain_name]["failed"] += 1

    # Recurse into nested suites
    for child in suite.get("suites", []):
        _count_specs(child, domains, domain_name)


def compute_domain_scores(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute health score and status for each domain."""
    scored = []
    for r in results:
        total = r["total"]
        if total == 0:
            score = 1.0
        else:
            score = r["passed"] / total

        if score >= _HEALTHY_THRESHOLD:
            status = "HEALTHY"
        elif score >= _DEGRADED_THRESHOLD:
            status = "DEGRADED"
        else:
            status = "CRITICAL"

        weight = DOMAIN_WEIGHTS.get(r["name"], 1.0)
        is_critical = r["name"] in CRITICAL_DOMAINS

        scored.append({
            **r,
            "score": round(score, 4),
            "status": status,
            "weight": weight,
            "is_critical": is_critical,
        })

    return scored


def compute_site_health(
    domain_scores: list[dict[str, Any]],
    previous_score: float | None = None,
) -> dict[str, Any]:
    """Compute overall weighted site health score."""
    if not domain_scores:
        return {
            "overall_score": 0.0,
            "overall_status": "CRITICAL",
            "total_passed": 0,
            "total_failed": 0,
            "total_tests": 0,
            "trend": None,
        }

    # Weighted score: sum(domain_score * weight * test_count) / sum(weight * test_count)
    weighted_sum = 0.0
    weight_total = 0.0
    total_passed = 0
    total_failed = 0
    total_skipped = 0

    for d in domain_scores:
        w = d["weight"] * d["total"]
        weighted_sum += d["score"] * w
        weight_total += w
        total_passed += d["passed"]
        total_failed += d["failed"]
        total_skipped += d.get("skipped", 0)

    overall_score = round(weighted_sum / weight_total, 4) if weight_total > 0 else 0.0

    if overall_score >= _HEALTHY_THRESHOLD:
        overall_status = "HEALTHY"
    elif overall_score >= _DEGRADED_THRESHOLD:
        overall_status = "DEGRADED"
    else:
        overall_status = "CRITICAL"

    # Trend vs previous
    trend = None
    if previous_score is not None:
        delta = overall_score - previous_score
        if abs(delta) < 0.01:
            trend_status = "stable"
        elif delta > 0:
            trend_status = "improving"
        else:
            trend_status = "declining"
        trend = {
            "delta": round(delta, 4),
            "status": trend_status,
            "previous_score": round(previous_score, 4),
        }

    total_tests = total_passed + total_failed + total_skipped

    return {
        "overall_score": overall_score,
        "overall_status": overall_status,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_skipped": total_skipped,
        "total_tests": total_tests,
        "trend": trend,
    }


def build_health_report(
    domain_scores: list[dict[str, Any]],
    site_health: dict[str, Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build the full health report."""
    return {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "run_id": run_id,
        **site_health,
        "domains": domain_scores,
        "critical_domains": [d["name"] for d in domain_scores if d.get("is_critical")],
    }


def save_health_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    """Save health report as JSON and markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "health.json"
    json_path.write_text(json.dumps(report, indent=2, default=str))

    md_path = output_dir / "health.md"
    md_path.write_text(format_health_markdown(report))

    return json_path, md_path


def format_health_markdown(report: dict[str, Any]) -> str:
    """Format health report as human-readable markdown."""
    lines = ["# CampingWorld Site Health Report", ""]

    score = report["overall_score"]
    status = report["overall_status"]
    lines.append(f"**Overall Health: {score * 100:.1f}% {status}**")
    lines.append("")

    # Progress bar
    filled = int(score * 20)
    bar = "\u25b0" * filled + "\u25b1" * (20 - filled)
    lines.append(f"  {bar} {score * 100:.1f}%")
    lines.append("")

    # Summary
    lines.append(f"- Passed: {report['total_passed']}")
    lines.append(f"- Failed: {report['total_failed']}")
    lines.append(f"- Total: {report['total_tests']}")
    lines.append("")

    # Trend
    trend = report.get("trend")
    if trend:
        lines.append(f"**Trend:** {trend['status'].upper()} ({trend['delta']:+.1%} vs previous)")
        lines.append("")

    # Domain breakdown
    lines.append("## Domain Breakdown")
    lines.append("")
    lines.append("| Domain | Passed | Failed | Total | Score | Status | Weight |")
    lines.append("|--------|--------|--------|-------|-------|--------|--------|")

    for d in report.get("domains", []):
        critical = " *" if d.get("is_critical") else ""
        lines.append(
            f"| {d['name']}{critical} | {d['passed']} | {d['failed']} | "
            f"{d['total']} | {d['score'] * 100:.1f}% | {d['status']} | {d['weight']}x |"
        )
    lines.append("")
    lines.append("\\* = critical purchase path (weighted 1.5-2x)")
    lines.append("")
    lines.append(f"**Run:** {report.get('run_id', 'unknown')}")
    lines.append(f"**Timestamp:** {report.get('timestamp', 'unknown')}")

    return "\n".join(lines)


def print_health(report: dict[str, Any]) -> None:
    """Print health report to console."""
    score = report["overall_score"]
    status = report["overall_status"]

    print(f"\n=== CampingWorld Site Health ===\n")

    filled = int(score * 20)
    bar = "\u25b0" * filled + "\u25b1" * (20 - filled)
    print(f"Overall Health: {score * 100:.1f}% {status}")
    print(f"  {bar} {score * 100:.1f}%\n")

    print("Domain Breakdown:")
    for d in report.get("domains", []):
        name = d["name"]
        p, f, t = d["passed"], d["failed"], d["total"]
        s = d["score"]
        st = d["status"]
        critical = "  *" if d.get("is_critical") else ""
        flag = " !!!" if st == "CRITICAL" else (" !" if st == "DEGRADED" else "")
        print(f"  {name:<25} {p:>3}/{t:<3}  {s * 100:>5.1f}%  {st}{critical}{flag}")

    trend = report.get("trend")
    if trend:
        print(f"\nTrend: {trend['status'].upper()} ({trend['delta']:+.1%} vs previous)")

    print(f"\nRun: {report.get('run_id', 'unknown')}")
    print(f"Total: {report['total_passed']} passed, {report['total_failed']} failed, "
          f"{report['total_tests']} total")


def load_previous_health(results_dir: Path | None = None) -> float | None:
    """Load the overall_score from the most recent previous health report."""
    base = results_dir or _TEST_RESULTS_DIR
    if not base.exists():
        return None

    runs = sorted(base.iterdir(), reverse=True)
    for run_dir in runs:
        health_json = run_dir / "health.json"
        if health_json.exists():
            try:
                data = json.loads(health_json.read_text())
                return data.get("overall_score")
            except (json.JSONDecodeError, OSError):
                continue
    return None


def compute_health_from_json(json_path: Path, output_dir: Path | None = None) -> dict[str, Any]:
    """End-to-end: parse results, compute scores, save report."""
    results = parse_playwright_json(json_path)
    domain_scores = compute_domain_scores(results)

    previous = load_previous_health()
    site_health = compute_site_health(domain_scores, previous)

    run_id = json_path.parent.name if json_path.parent != Path(".") else None
    report = build_health_report(domain_scores, site_health, run_id)

    if output_dir:
        save_health_report(report, output_dir)

    return report


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m qa_agent.health <results.json> [--output <dir>]")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    output_dir = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        output_dir = Path(sys.argv[idx + 1])

    report = compute_health_from_json(json_path, output_dir)
    print_health(report)
