"""Recommendations engine — analyzes eval scorecards and generates actionable advice.

Pure Python pattern matching. No LLM calls. Deterministic.
"""

from __future__ import annotations

from typing import Any


def generate_recommendations(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze a scorecard and return prioritized recommendations.

    Returns list of:
        {"priority": "high|medium|low", "finding": "...", "action": "...", "category": "..."}
    """
    recs: list[dict[str, Any]] = []
    accuracy = scorecard.get("triage_accuracy", {})
    misses = accuracy.get("misses", [])
    score = accuracy.get("score", 0.0)
    threshold = scorecard.get("thresholds", {}).get("triage_accuracy", 0.75)
    by_category = scorecard.get("by_category", {})
    regression = scorecard.get("regression_vs_previous") or {}

    # --- Analyze miss patterns ---
    confidence_underruns = _find_confidence_underruns(misses)
    misclassifications = _find_misclassifications(misses)

    # --- Rule: Confidence underrun by category ---
    for cat, items in confidence_underruns.items():
        cat_total = by_category.get(cat, {}).get("total", 0)
        if cat_total > 0 and len(items) / cat_total >= 0.5:
            avg_got = sum(m["got_conf"] for m in items) / len(items)
            avg_expected = sum(m["expected_conf_min"] for m in items) / len(items)
            recs.append({
                "priority": "high",
                "category": cat,
                "finding": (
                    f"{len(items)}/{cat_total} {cat} scenarios classify correctly "
                    f"but confidence averages {avg_got:.2f} (needs >={avg_expected:.2f}). "
                    f"The confidence rubric is capping scores too low."
                ),
                "action": (
                    f"Option 1: Tune the confidence rubric in qa_agent/confidence.py "
                    f"to produce higher scores for {cat} patterns. "
                    f"Option 2: Lower expected_confidence_min in golden data to ~{avg_got:.2f}."
                ),
            })

    # --- Rule: Misclassification ---
    if misclassifications:
        confused_pairs: dict[str, list[str]] = {}
        for m in misclassifications:
            key = f"{m['expected_class']} -> {m['got_class']}"
            confused_pairs.setdefault(key, []).append(m["scenario"])

        for pair, scenarios in confused_pairs.items():
            expected, got = pair.split(" -> ")
            recs.append({
                "priority": "high",
                "category": expected,
                "finding": (
                    f"{len(scenarios)} scenario(s) expected '{expected}' but triage returned '{got}': "
                    f"{', '.join(scenarios)}."
                ),
                "action": (
                    f"Add clearer '{expected}' vs '{got}' disambiguation examples "
                    f"to the triage prompt in qa_agent/prompts/TRIAGE.md."
                ),
            })

    # --- Rule: Score below threshold ---
    if score < threshold:
        gap = threshold - score
        recs.append({
            "priority": "high",
            "category": "overall",
            "finding": (
                f"Overall accuracy {score:.1%} is below threshold {threshold:.1%} "
                f"(gap: {gap:.1%}). {len(misses)} of {accuracy.get('total', 0)} scenarios missed."
            ),
            "action": "Address the confidence and classification issues above to close the gap.",
        })

    # --- Rule: Category at 0% ---
    for cat, data in by_category.items():
        if data.get("total", 0) > 0 and data.get("score", 0) == 0:
            recs.append({
                "priority": "high",
                "category": cat,
                "finding": f"Category '{cat}' has 0% accuracy ({data['total']} scenarios, all missed).",
                "action": f"Systematic issue — review triage behavior for {cat} error patterns.",
            })

    # --- Rule: Major regression ---
    if regression.get("severity") == "major":
        recs.append({
            "priority": "high",
            "category": "regression",
            "finding": (
                f"Major regression detected: score dropped {abs(regression.get('delta', 0)):.1%} "
                f"from {regression.get('previous_score', 0):.1%} to {regression.get('current_score', 0):.1%}."
            ),
            "action": "Investigate recent prompt, model, or memory changes that may have caused the drop.",
        })

    # --- Rule: Minor regression ---
    if regression.get("severity") == "minor":
        recs.append({
            "priority": "medium",
            "category": "regression",
            "finding": (
                f"Minor regression: score dropped {abs(regression.get('delta', 0)):.1%}. "
                f"May be LLM variance."
            ),
            "action": "Monitor over the next 2-3 runs before taking action.",
        })

    # --- Rule: New failures ---
    new_failures = regression.get("new_failures", [])
    if new_failures:
        recs.append({
            "priority": "medium",
            "category": "regression",
            "finding": f"{len(new_failures)} new failure(s) not seen in previous run: {', '.join(new_failures)}.",
            "action": "Investigate these specific scenarios — they were passing before.",
        })

    # --- Rule: Recovered scenarios (positive) ---
    recovered = regression.get("recovered", [])
    if recovered:
        recs.append({
            "priority": "low",
            "category": "improvement",
            "finding": f"{len(recovered)} scenario(s) recovered since previous run: {', '.join(recovered)}.",
            "action": "No action needed — this is positive progress.",
        })

    # --- Rule: All passing ---
    if score >= threshold and not misses:
        recs.append({
            "priority": "low",
            "category": "overall",
            "finding": "All scenarios pass. Triage accuracy is above threshold.",
            "action": "No action needed. Consider adding more challenging golden scenarios.",
        })

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: priority_order.get(r["priority"], 9))

    return recs


def format_report_markdown(scorecard: dict[str, Any]) -> str:
    """Generate a human-readable markdown report from a scorecard."""
    lines = [f"# Eval Report: {scorecard.get('agent', 'unknown')}", ""]

    # Summary
    accuracy = scorecard.get("triage_accuracy", {})
    threshold = scorecard.get("thresholds", {}).get("triage_accuracy", 0.75)
    passed = scorecard.get("passed")
    status = "BASELINE" if passed is None else ("PASS" if passed else "FAIL")
    mode = " (baseline)" if scorecard.get("baseline_mode") else ""

    lines.append(f"**Run:** {scorecard.get('eval_run_id', 'unknown')}{mode}")
    lines.append(f"**Timestamp:** {scorecard.get('timestamp', 'unknown')}")
    lines.append(f"**Result:** {status}")
    lines.append("")
    lines.append(f"## Accuracy: {accuracy.get('score', 0) * 100:.1f}% (threshold: {threshold * 100:.1f}%)")
    lines.append("")
    lines.append(f"- Correct: {accuracy.get('correct', 0)}/{accuracy.get('total', 0)}")
    lines.append(f"- Misses: {len(accuracy.get('misses', []))}")
    lines.append("")

    # Category breakdown
    by_category = scorecard.get("by_category", {})
    if by_category:
        lines.append("## By Category")
        lines.append("")
        lines.append("| Category | Score | Correct | Total |")
        lines.append("|----------|-------|---------|-------|")
        for cat, data in sorted(by_category.items()):
            lines.append(f"| {cat} | {data['score'] * 100:.1f}% | {data['correct']} | {data['total']} |")
        lines.append("")

    # Regression
    reg = scorecard.get("regression_vs_previous")
    if reg:
        delta_str = f"{reg.get('delta', 0):+.1%}"
        lines.append(f"## Regression: {reg.get('status', 'unknown').upper()} ({delta_str})")
        lines.append("")
        if reg.get("new_failures"):
            lines.append(f"- New failures: {', '.join(reg['new_failures'])}")
        if reg.get("recovered"):
            lines.append(f"- Recovered: {', '.join(reg['recovered'])}")
        lines.append("")

    # Recommendations
    recs = scorecard.get("recommendations", [])
    if recs:
        lines.append("## Recommendations")
        lines.append("")
        for r in recs:
            priority = r["priority"].upper()
            lines.append(f"### [{priority}] {r.get('category', 'general')}")
            lines.append("")
            lines.append(f"**Finding:** {r['finding']}")
            lines.append("")
            lines.append(f"**Action:** {r['action']}")
            lines.append("")

    # Misses detail
    misses = accuracy.get("misses", [])
    if misses:
        lines.append("## Misses Detail")
        lines.append("")
        for m in misses:
            scenario = m.get("scenario", "unknown")
            root_cause = m.get("root_cause", "unknown")
            expected = m.get("expected_class", "?")
            got = m.get("got_class", "?")
            expected_conf = m.get("expected_conf_min", "?")
            got_conf = m.get("got_conf", "?")

            lines.append(f"### {scenario}")
            lines.append("")
            lines.append(f"- **Root cause:** {root_cause}")
            lines.append(f"- **Expected class:** {expected} | **Got:** {got}")
            lines.append(f"- **Expected confidence:** >={expected_conf} | **Got:** {got_conf}")

            # Error message
            error = m.get("error")
            if error:
                truncated = error[:300] + "..." if len(error) > 300 else error
                lines.append(f"- **Error message:**")
                lines.append(f"  ```")
                lines.append(f"  {truncated}")
                lines.append(f"  ```")

            # Confidence breakdown
            breakdown = m.get("confidence_breakdown")
            if breakdown:
                lines.append(f"- **Confidence breakdown:**")
                lines.append(f"  - C1 (error type): {breakdown.get('c1_error_type', '?')}")
                lines.append(f"  - C2 (DOM evidence): {breakdown.get('c2_dom_evidence', '?')}")
                lines.append(f"  - C3 (history match): {breakdown.get('c3_history_match', '?')}")
                lines.append(f"  - C4 (human calibration): {breakdown.get('c4_human_calibration', '?')}")
                lines.append(f"  - C5 (consistency): {breakdown.get('c5_consistency', '?')}")
                lines.append(f"  - Raw score: {breakdown.get('raw_score', '?')}")
                guards = breakdown.get("guards_applied", [])
                if guards:
                    lines.append(f"  - Guards applied: {', '.join(guards)}")
                lines.append(f"  - Final score: {breakdown.get('final_score', '?')}")

            lines.append("")

    return "\n".join(lines)


def _find_confidence_underruns(misses: list[dict]) -> dict[str, list[dict]]:
    """Group misses where class is correct but confidence is below threshold."""
    by_cat: dict[str, list[dict]] = {}
    for m in misses:
        if m.get("got_class") == m.get("expected_class"):
            cat = m.get("expected_class", "unknown")
            by_cat.setdefault(cat, []).append(m)
    return by_cat


def _find_misclassifications(misses: list[dict]) -> list[dict]:
    """Find misses where the class itself is wrong."""
    return [m for m in misses if m.get("got_class") != m.get("expected_class")]
