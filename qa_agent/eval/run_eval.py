"""Evaluation harness — scores plan/tests/triage against golden fixtures.

Metrics:
  - AC coverage: does every acceptance criterion map to at least one test case?
  - Locator quality: role/testid preferred over brittle CSS selectors
  - Triage accuracy: did Triage classify seeded failures correctly?
  - Assertion integrity: did Healer avoid modifying assertions?
  - Diff minimality: did Healer restrict changes to locator-related lines?

Can be run standalone: python -m qa_agent.eval.run_eval
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from qa_agent.nodes.healer import validate_healer_diff, AssertionGuardError

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

# Thresholds — a run must meet all of these to pass
THRESHOLDS = {
    "ac_coverage": 0.80,       # 80% of ACs covered by at least one test
    "locator_quality": 0.70,   # 70% of locators use role/testid (not CSS)
    "triage_accuracy": 0.75,   # 75% of seeded failures classified correctly
}


# ---------------------------------------------------------------------------
# AC Coverage
# ---------------------------------------------------------------------------

def score_ac_coverage(
    acceptance_criteria: list[str],
    test_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Score: what fraction of ACs are covered by at least one test case?

    A test case "covers" an AC if any of its steps or expected values
    contain keywords from the AC (fuzzy substring match).
    """
    if not acceptance_criteria:
        return {"score": 1.0, "covered": 0, "total": 0, "uncovered": []}

    covered = []
    uncovered = []

    for ac in acceptance_criteria:
        ac_lower = ac.lower()
        # Extract key phrases (3+ char words)
        keywords = [w for w in re.findall(r"\w+", ac_lower) if len(w) >= 3]

        found = False
        for tc in test_cases:
            tc_text = " ".join([
                tc.get("title", ""),
                " ".join(tc.get("steps", [])),
                " ".join(tc.get("expected", [])),
            ]).lower()

            # AC is covered if at least half of its keywords appear in the test
            matches = sum(1 for kw in keywords if kw in tc_text)
            if keywords and matches / len(keywords) >= 0.4:
                found = True
                break

        if found:
            covered.append(ac)
        else:
            uncovered.append(ac)

    score = len(covered) / len(acceptance_criteria)
    return {
        "score": round(score, 4),
        "covered": len(covered),
        "total": len(acceptance_criteria),
        "uncovered": uncovered,
    }


# ---------------------------------------------------------------------------
# Locator Quality
# ---------------------------------------------------------------------------

_GOOD_LOCATOR_PATTERNS = [
    re.compile(r"getByRole\s*\("),
    re.compile(r"getByTestId\s*\("),
    re.compile(r"getByText\s*\("),
    re.compile(r"getByLabel\s*\("),
    re.compile(r"getByPlaceholder\s*\("),
    re.compile(r"getByAltText\s*\("),
]

_BRITTLE_LOCATOR_PATTERNS = [
    re.compile(r"locator\s*\(\s*['\"][\.\#]"),       # CSS selectors: .class, #id
    re.compile(r"locator\s*\(\s*['\"]div\b"),         # tag selectors
    re.compile(r"locator\s*\(\s*['\"]span\b"),
    re.compile(r"\$\s*\(\s*['\"]"),                   # jQuery-style
]


def score_locator_quality(page_objects: dict[str, str]) -> dict[str, Any]:
    """Score: what fraction of locators use resilient strategies?"""
    if not page_objects:
        return {"score": 1.0, "good": 0, "brittle": 0, "total": 0}

    good_count = 0
    brittle_count = 0

    for source in page_objects.values():
        for line in source.split("\n"):
            is_good = any(p.search(line) for p in _GOOD_LOCATOR_PATTERNS)
            is_brittle = any(p.search(line) for p in _BRITTLE_LOCATOR_PATTERNS)

            if is_good:
                good_count += 1
            elif is_brittle:
                brittle_count += 1

    total = good_count + brittle_count
    score = good_count / total if total > 0 else 1.0

    return {
        "score": round(score, 4),
        "good": good_count,
        "brittle": brittle_count,
        "total": total,
    }


# ---------------------------------------------------------------------------
# POM Validity
# ---------------------------------------------------------------------------

def score_pom_validity(page_objects: dict[str, str]) -> dict[str, Any]:
    """Score: what fraction of page objects are structurally valid TypeScript POMs?

    Checks each POM source for:
    - Has a class declaration
    - Has constructor(page: Page)
    - Has a navigate() method
    - Has an export statement
    - Uses Locator type
    """
    if not page_objects:
        return {"score": 1.0, "valid": 0, "total": 0, "invalid": []}

    _class_re = re.compile(r"\bclass\s+\w+")
    _constructor_re = re.compile(r"\bconstructor\s*\(\s*page\s*:\s*Page\b")
    _navigate_re = re.compile(r"\bnavigate\s*\(")
    _export_re = re.compile(r"\bexport\b")
    _locator_re = re.compile(r"\bLocator\b")

    checks = [
        ("class_declaration", _class_re),
        ("constructor_page", _constructor_re),
        ("navigate_method", _navigate_re),
        ("export_statement", _export_re),
        ("locator_type", _locator_re),
    ]

    valid = 0
    invalid: list[dict[str, Any]] = []

    for route, source in page_objects.items():
        failed = [name for name, pattern in checks if not pattern.search(source)]
        if not failed:
            valid += 1
        else:
            invalid.append({"route": route, "failed_checks": failed})

    total = len(page_objects)
    score = valid / total if total > 0 else 1.0
    return {
        "score": round(score, 4),
        "valid": valid,
        "total": total,
        "invalid": invalid,
    }


# ---------------------------------------------------------------------------
# Test Validity
# ---------------------------------------------------------------------------

def score_test_validity(test_code: dict[str, str]) -> dict[str, Any]:
    """Score: what fraction of test spec files are structurally valid?

    Checks each spec file for:
    - Has test.describe( or describe( block
    - Has test( blocks
    - Has beforeEach(
    - Has at least 1 expect( assertion
    """
    if not test_code:
        return {"score": 1.0, "valid": 0, "total": 0, "invalid": []}

    _describe_re = re.compile(r"\btest\.describe\s*\(|\bdescribe\s*\(")
    _test_block_re = re.compile(r"\btest\s*\(")
    _before_each_re = re.compile(r"\bbeforeEach\s*\(")
    _expect_re = re.compile(r"\bexpect\s*\(")

    checks = [
        ("describe_block", _describe_re),
        ("test_block", _test_block_re),
        ("before_each", _before_each_re),
        ("expect_assertion", _expect_re),
    ]

    valid = 0
    invalid: list[dict[str, Any]] = []

    for filename, source in test_code.items():
        failed = [name for name, pattern in checks if not pattern.search(source)]
        if not failed:
            valid += 1
        else:
            invalid.append({"file": filename, "failed_checks": failed})

    total = len(test_code)
    score = valid / total if total > 0 else 1.0
    return {
        "score": round(score, 4),
        "valid": valid,
        "total": total,
        "invalid": invalid,
    }


# ---------------------------------------------------------------------------
# Triage Accuracy
# ---------------------------------------------------------------------------

def score_triage_accuracy(
    triage_results: list[dict[str, Any]],
    expected: list[dict[str, Any]],
) -> dict[str, Any]:
    """Score: how many seeded failures did Triage classify correctly?"""
    if not expected:
        return {"score": 1.0, "correct": 0, "total": 0, "misses": []}

    correct = 0
    misses = []

    for i, exp in enumerate(expected):
        if i >= len(triage_results):
            misses.append({"scenario": exp["scenario"], "reason": "no result"})
            continue

        result = triage_results[i]
        class_match = result.get("failure_class") == exp["expected_class"]
        conf_ok = result.get("confidence", 0) >= exp.get("expected_confidence_min", 0)

        if class_match and conf_ok:
            correct += 1
        else:
            miss = {
                "scenario": exp["scenario"],
                "expected_class": exp["expected_class"],
                "got_class": result.get("failure_class"),
                "expected_conf_min": exp.get("expected_confidence_min"),
                "got_conf": result.get("confidence"),
            }
            # Pass through diagnostic context if available
            if result.get("error"):
                miss["error"] = result["error"]
            if result.get("confidence_breakdown"):
                miss["confidence_breakdown"] = result["confidence_breakdown"]
            # Determine root cause
            if miss["got_class"] != miss["expected_class"]:
                miss["root_cause"] = "misclassification"
            else:
                miss["root_cause"] = "confidence_underrun"
            misses.append(miss)

    score = correct / len(expected)
    return {
        "score": round(score, 4),
        "correct": correct,
        "total": len(expected),
        "misses": misses,
    }


# ---------------------------------------------------------------------------
# Full evaluation
# ---------------------------------------------------------------------------

def run_full_eval(
    acceptance_criteria: list[str],
    test_cases: list[dict[str, Any]],
    page_objects: dict[str, str],
    triage_results: list[dict[str, Any]],
    triage_expected: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run all evaluation metrics and return a report."""
    ac = score_ac_coverage(acceptance_criteria, test_cases)
    locator = score_locator_quality(page_objects)
    triage = score_triage_accuracy(triage_results, triage_expected)

    all_pass = (
        ac["score"] >= THRESHOLDS["ac_coverage"]
        and locator["score"] >= THRESHOLDS["locator_quality"]
        and triage["score"] >= THRESHOLDS["triage_accuracy"]
    )

    return {
        "passed": all_pass,
        "thresholds": THRESHOLDS,
        "ac_coverage": ac,
        "locator_quality": locator,
        "triage_accuracy": triage,
    }


# ---------------------------------------------------------------------------
# Healer: Assertion Integrity
# ---------------------------------------------------------------------------

def score_assertion_integrity(
    old_sources: dict[str, str],
    new_sources: dict[str, str],
) -> dict[str, Any]:
    """Score: what fraction of routes have no assertion modifications?

    For each route present in new_sources, call validate_healer_diff(old, new).
    If AssertionGuardError is raised, that route is a violation.
    Score = routes without violations / total routes scored.
    """
    routes = list(new_sources.keys())
    if not routes:
        return {"score": 1.0, "clean": 0, "violations": 0, "total": 0, "violation_routes": []}

    violation_routes: list[str] = []
    for route in routes:
        old = old_sources.get(route, "")
        new = new_sources[route]
        try:
            validate_healer_diff(old, new)
        except AssertionGuardError:
            violation_routes.append(route)

    clean = len(routes) - len(violation_routes)
    score = clean / len(routes)
    return {
        "score": round(score, 4),
        "clean": clean,
        "violations": len(violation_routes),
        "total": len(routes),
        "violation_routes": violation_routes,
    }


# ---------------------------------------------------------------------------
# Healer: Diff Minimality
# ---------------------------------------------------------------------------

_LOCATOR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"getByRole\s*\("),
    re.compile(r"getByTestId\s*\("),
    re.compile(r"getByText\s*\("),
    re.compile(r"getByLabel\s*\("),
    re.compile(r"getByPlaceholder\s*\("),
    re.compile(r"getByAltText\s*\("),
    re.compile(r"\blocator\s*\("),
    re.compile(r"\.waitFor\s*\("),
    re.compile(r"\.scrollIntoViewIfNeeded\s*\("),
    re.compile(r"\btimeout\b"),
]


def _is_locator_line(line: str) -> bool:
    """Return True if the line contains a locator or wait pattern."""
    return any(p.search(line) for p in _LOCATOR_PATTERNS)


def score_diff_minimality(
    old_sources: dict[str, str],
    new_sources: dict[str, str],
) -> dict[str, Any]:
    """Score: what fraction of changed lines are locator-related?

    Compare old vs new line by line for each route. Count lines that
    differ (present in one but not the other). Of those changed lines,
    count how many contain a locator pattern.

    Score = locator-related changed lines / total changed lines.
    Returns 1.0 if there are no changes at all.
    """
    total_changed = 0
    locator_changed = 0

    for route, new_src in new_sources.items():
        old_src = old_sources.get(route, "")
        old_lines = set(old_src.splitlines())
        new_lines = set(new_src.splitlines())

        # Lines added or removed
        changed = old_lines.symmetric_difference(new_lines)
        for line in changed:
            stripped = line.strip()
            if not stripped:
                continue
            total_changed += 1
            if _is_locator_line(stripped):
                locator_changed += 1

    if total_changed == 0:
        return {"score": 1.0, "locator_changes": 0, "non_locator_changes": 0, "total_changes": 0}

    score = locator_changed / total_changed
    return {
        "score": round(score, 4),
        "locator_changes": locator_changed,
        "non_locator_changes": total_changed - locator_changed,
        "total_changes": total_changed,
    }


def main() -> None:
    """Run eval against golden fixtures (standalone entry point)."""
    # Load golden data
    intake = json.loads((GOLDEN_DIR / "sample_intake.json").read_text())
    expected_plan = json.loads((GOLDEN_DIR / "expected_plan.json").read_text())
    triage_expected = json.loads((GOLDEN_DIR / "expected_triage.json").read_text())

    # For standalone: score the golden plan against the golden ACs
    ac_result = score_ac_coverage(intake["acceptance_criteria"], expected_plan)

    # Locator quality on sample page objects
    sample_po = {
        "/checkout": (
            "this.submitBtn = page.getByRole('button', { name: 'Submit' });\n"
            "this.emailInput = page.getByTestId('checkout-email');\n"
        )
    }
    locator_result = score_locator_quality(sample_po)

    print("=== QA Agent Eval ===")
    print(f"\nAC Coverage:     {ac_result['score']:.0%} "
          f"(threshold: {THRESHOLDS['ac_coverage']:.0%}) "
          f"{'PASS' if ac_result['score'] >= THRESHOLDS['ac_coverage'] else 'FAIL'}")
    print(f"Locator Quality: {locator_result['score']:.0%} "
          f"(threshold: {THRESHOLDS['locator_quality']:.0%}) "
          f"{'PASS' if locator_result['score'] >= THRESHOLDS['locator_quality'] else 'FAIL'}")

    if ac_result["uncovered"]:
        print(f"\nUncovered ACs:")
        for ac in ac_result["uncovered"]:
            print(f"  - {ac}")

    passed = (
        ac_result["score"] >= THRESHOLDS["ac_coverage"]
        and locator_result["score"] >= THRESHOLDS["locator_quality"]
    )
    print(f"\nOverall: {'PASS' if passed else 'FAIL'}")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
