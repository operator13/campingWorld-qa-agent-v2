"""Weekly review — periodic self-grading with stats, trends, and prescriptions.

Reads metrics DB + memory to produce a structured review that grades the
system's performance and prescribes concrete adjustments. Appends to
memory/WEEKLY_REVIEW.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qa_agent.memory import MemoryStore
from qa_agent.nodes.metrics import MetricsDB

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"

# ---------------------------------------------------------------------------
# Grading rubric
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS = [
    # (min_score, grade) — checked top-down, first match wins
    (90, "A"),
    (80, "B+"),
    (70, "B"),
    (60, "B-"),
    (50, "C+"),
    (40, "C"),
    (30, "C-"),
    (20, "D"),
    (0, "F"),
]


def _compute_grade_score(stats: dict[str, Any]) -> int:
    """Compute a 0-100 composite score from review stats.

    Weights:
      - Pass rate:       30 points
      - Escape rate:     25 points (inverted — lower is better)
      - Triage accuracy: 25 points
      - Healer hit rate: 20 points
    """
    pass_rate = stats.get("pass_rate", 0)
    escape_rate = stats.get("escape_rate", 0)
    triage_accuracy = stats.get("triage_accuracy", 0)
    healer_hit_rate = stats.get("healer_cache_hit_rate", 0)

    score = 0
    score += min(30, int(pass_rate * 30))
    score += min(25, int((1 - escape_rate) * 25))
    score += min(25, int(triage_accuracy * 25))
    score += min(20, int(healer_hit_rate * 20))

    return score


def _score_to_grade(score: int) -> str:
    """Map a 0-100 score to a letter grade."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def _trend_arrow(current: float, previous: float | None) -> str:
    """Return a trend indicator: up, down, or flat."""
    if previous is None:
        return "—"
    diff = current - previous
    if abs(diff) < 0.02:
        return "—"
    return "↑" if diff > 0 else "↓"


# ---------------------------------------------------------------------------
# Stats gathering
# ---------------------------------------------------------------------------

def gather_review_stats(
    db: MetricsDB | None = None,
    memory: MemoryStore | None = None,
) -> dict[str, Any]:
    """Gather all stats needed for a weekly review."""
    if db is None:
        db = MetricsDB()
    if memory is None:
        memory = MemoryStore()

    escape = db.compute_escape_rate()
    accuracy = db.compute_triage_accuracy()

    # Count runs this week (last 7 days)
    from datetime import timedelta
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    total_runs, passed_runs = db.get_run_count(since=week_ago)

    pass_rate = passed_runs / total_runs if total_runs > 0 else 0.0

    # Healer cache hit rate: actual tracked data
    healer_hit_rate = memory.get_healer_cache_hit_rate()

    # Flaky tests
    flaky = memory.get_flaky_tests(threshold=0.2)

    # Volatile routes
    volatile = memory.get_volatile_routes(threshold=1.0)

    # Human decisions count
    decisions = memory.get_triage_calibration(n=100)

    return {
        "total_runs": total_runs,
        "passed_runs": passed_runs,
        "failed_runs": total_runs - passed_runs,
        "pass_rate": round(pass_rate, 2),
        "escape_rate": escape["escape_rate"],
        "escapes": escape["escapes"],
        "triage_accuracy": accuracy["accuracy"],
        "triage_audited": accuracy["total_audited"],
        "healer_cache_hit_rate": round(healer_hit_rate, 2),
        "flaky_tests": len(flaky),
        "volatile_routes": len(volatile),
        "human_decisions": len(decisions),
        "locator_entries": memory.stats()["files"].get("locators", 0),
    }


# ---------------------------------------------------------------------------
# Prescription generation
# ---------------------------------------------------------------------------

def generate_prescriptions(stats: dict[str, Any], memory: MemoryStore | None = None) -> list[str]:
    """Generate concrete prescriptions based on stats."""
    if memory is None:
        memory = MemoryStore()

    prescriptions = []

    # Escape rate
    if stats["escape_rate"] > 0.10:
        prescriptions.append(
            f"**Reduce escape rate** ({stats['escape_rate']:.0%}) — "
            f"{stats['escapes']} bugs slipped through green runs. "
            f"Review uncovered routes and add targeted tests."
        )

    # Triage accuracy
    if stats["triage_audited"] >= 5 and stats["triage_accuracy"] < 0.70:
        prescriptions.append(
            f"**Improve Triage accuracy** ({stats['triage_accuracy']:.0%}) — "
            f"consider raising CONF_SURE to send more cases to human review."
        )
    elif stats["triage_audited"] >= 5 and stats["triage_accuracy"] > 0.90:
        prescriptions.append(
            f"**Triage is well-calibrated** ({stats['triage_accuracy']:.0%}) — "
            f"consider lowering CONF_SURE to reduce human review load."
        )

    # Pass rate
    if stats["pass_rate"] < 0.70:
        prescriptions.append(
            f"**Pass rate is low** ({stats['pass_rate']:.0%}) — "
            f"investigate recurring failures. Check flaky tests and volatile routes."
        )

    # Flaky tests
    if stats["flaky_tests"] > 0:
        flaky = memory.get_flaky_tests(threshold=0.2)
        flaky_ids = [t["test_id"] for t in flaky[:3]]
        prescriptions.append(
            f"**{stats['flaky_tests']} flaky test(s)** — "
            f"investigate: {', '.join(flaky_ids)}. Consider quarantining or fixing."
        )

    # Volatile routes
    if stats["volatile_routes"] > 0:
        volatile = memory.get_volatile_routes(threshold=1.0)
        route_names = [r["route"] for r in volatile[:3]]
        prescriptions.append(
            f"**{stats['volatile_routes']} volatile route(s)** — "
            f"{', '.join(route_names)} change frequently. Notify dev team or stabilize locators."
        )

    # Healer effectiveness
    if stats["healer_cache_hit_rate"] < 0.20 and stats["locator_entries"] > 5:
        prescriptions.append(
            f"**Healer cache hit rate is low** ({stats['healer_cache_hit_rate']:.0%}) — "
            f"locators are changing in new ways. Review if testid conventions have shifted."
        )

    if not prescriptions:
        prescriptions.append("**System is healthy** — no action items this week.")

    return prescriptions


# ---------------------------------------------------------------------------
# Review generation
# ---------------------------------------------------------------------------

def generate_weekly_review(
    db: MetricsDB | None = None,
    memory: MemoryStore | None = None,
    previous_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a complete weekly review.

    Returns a dict with stats, grade, prescriptions, and formatted markdown.
    """
    if memory is None:
        memory = MemoryStore()

    stats = gather_review_stats(db=db, memory=memory)
    score = _compute_grade_score(stats)
    grade = _score_to_grade(score)
    prescriptions = generate_prescriptions(stats, memory=memory)

    # Build trends (compare to previous if available)
    trends = {}
    if previous_stats:
        trends["pass_rate"] = _trend_arrow(stats["pass_rate"], previous_stats.get("pass_rate"))
        trends["escape_rate"] = _trend_arrow(stats["escape_rate"], previous_stats.get("escape_rate"))
        trends["triage_accuracy"] = _trend_arrow(stats["triage_accuracy"], previous_stats.get("triage_accuracy"))
        trends["healer_cache_hit_rate"] = _trend_arrow(
            stats["healer_cache_hit_rate"], previous_stats.get("healer_cache_hit_rate")
        )

    # Format as markdown
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    markdown = _format_review_markdown(now, stats, trends, grade, score, prescriptions)

    return {
        "date": now,
        "stats": stats,
        "score": score,
        "grade": grade,
        "prescriptions": prescriptions,
        "trends": trends,
        "markdown": markdown,
    }


def write_weekly_review(
    review: dict[str, Any],
    memory_dir: str | Path | None = None,
) -> None:
    """Append a weekly review to WEEKLY_REVIEW.md."""
    filepath = Path(memory_dir or _DEFAULT_MEMORY_DIR) / "WEEKLY_REVIEW.md"

    if not filepath.exists():
        filepath.write_text("# Weekly Reviews\n")

    with open(filepath, "a") as f:
        f.write("\n" + review["markdown"])

    logger.info("Weekly review written for %s (grade: %s)", review["date"], review["grade"])


def get_previous_stats(memory_dir: str | Path | None = None) -> dict[str, Any] | None:
    """Parse the most recent review from WEEKLY_REVIEW.md to get previous stats."""
    filepath = Path(memory_dir or _DEFAULT_MEMORY_DIR) / "WEEKLY_REVIEW.md"
    if not filepath.exists():
        return None

    content = filepath.read_text()
    # Find the last stats table
    import re
    # Look for the last "| Total runs |" line
    matches = list(re.finditer(r"\| Total runs \| (\d+)", content))
    if not matches:
        return None

    # Parse stats from the last table
    last_match = matches[-1]
    # Get the section around this match
    start = max(0, last_match.start() - 200)
    section = content[start:last_match.end() + 500]

    stats: dict[str, Any] = {}
    for line in section.split("\n"):
        if "| Pass rate |" in line:
            m = re.search(r"([\d.]+)%", line)
            if m:
                stats["pass_rate"] = float(m.group(1)) / 100
        elif "| Escape rate |" in line:
            m = re.search(r"([\d.]+)%", line)
            if m:
                stats["escape_rate"] = float(m.group(1)) / 100
        elif "| Triage accuracy |" in line:
            m = re.search(r"([\d.]+)%", line)
            if m:
                stats["triage_accuracy"] = float(m.group(1)) / 100
        elif "| Healer cache hit |" in line:
            m = re.search(r"([\d.]+)%", line)
            if m:
                stats["healer_cache_hit_rate"] = float(m.group(1)) / 100

    return stats if stats else None


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------

def _format_review_markdown(
    date: str,
    stats: dict[str, Any],
    trends: dict[str, str],
    grade: str,
    score: int,
    prescriptions: list[str],
) -> str:
    """Format a review as markdown."""
    t = trends

    lines = [
        f"## Week of {date}\n",
        "### Stats",
        "| Metric | Value | Trend |",
        "|--------|-------|-------|",
        f"| Total runs | {stats['total_runs']} | — |",
        f"| Pass rate | {stats['pass_rate']:.0%} | {t.get('pass_rate', '—')} |",
        f"| Escape rate | {stats['escape_rate']:.0%} | {t.get('escape_rate', '—')} |",
        f"| Triage accuracy | {stats['triage_accuracy']:.0%} | {t.get('triage_accuracy', '—')} |",
        f"| Healer cache hit | {stats['healer_cache_hit_rate']:.0%} | {t.get('healer_cache_hit_rate', '—')} |",
        f"| Flaky tests | {stats['flaky_tests']} | — |",
        f"| Volatile routes | {stats['volatile_routes']} | — |",
        f"| Human decisions | {stats['human_decisions']} | — |",
        "",
        f"### Grade: {grade} ({score}/100)",
        "",
        "### Prescriptions",
    ]

    for i, p in enumerate(prescriptions, 1):
        lines.append(f"{i}. {p}")

    lines.append("")
    return "\n".join(lines)
