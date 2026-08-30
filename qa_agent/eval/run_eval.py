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

            # AC is covered if at least 60% of its keywords appear in the test
            matches = sum(1 for kw in keywords if kw in tc_text)
            if keywords and matches / len(keywords) >= 0.6:
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
# Import Correctness
# ---------------------------------------------------------------------------

_IMPORT_RE = re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]")


def score_import_correctness(
    page_objects: dict[str, str],
    test_code: dict[str, str],
) -> dict[str, Any]:
    """Score: what fraction of test-file import statements are semantically correct?

    For each ``import { X } from '../page_objects/Y'`` (or ``../page-objects/Y``)
    in a test file:

    - Flags imports that use a hyphen path (``page-objects``) instead of
      underscore (``page_objects``).
    - Flags imports with an empty filename, e.g. ``'../page_objects/'``.
    - Flags imports whose class name ``X`` does not appear as a class
      declaration in any POM source provided in ``page_objects``.

    Imports that do not reference ``page_objects`` or ``page-objects`` are
    ignored (e.g. ``@playwright/test`` imports).

    Returns::

        {
            "score": float,       # correct / total (1.0 when total == 0)
            "correct": int,
            "total": int,
            "errors": [{"file": str, "import": str, "issue": str}, ...]
        }
    """
    if not test_code:
        return {"score": 1.0, "correct": 0, "total": 0, "errors": []}

    # Build a set of class names declared in the provided page objects
    _class_name_re = re.compile(r"\bclass\s+(\w+)")
    pom_class_names: set[str] = set()
    for source in page_objects.values():
        for match in _class_name_re.finditer(source):
            pom_class_names.add(match.group(1))

    total = 0
    correct = 0
    errors: list[dict[str, Any]] = []

    for filename, source in test_code.items():
        for m in _IMPORT_RE.finditer(source):
            imported_names_raw = m.group(1)
            import_path = m.group(2)

            # Only evaluate imports that reference page_objects or page-objects
            if "page_objects" not in import_path and "page-objects" not in import_path:
                continue

            # Normalise the imported class names (strip whitespace, type keyword)
            imported_names = [
                n.strip().lstrip("type").strip()
                for n in imported_names_raw.split(",")
                if n.strip()
            ]

            for class_name in imported_names:
                if not class_name:
                    continue

                import_repr = f"import {{ {class_name} }} from '{import_path}'"
                total += 1

                # Check 1: hyphen path
                if "page-objects" in import_path:
                    errors.append({
                        "file": filename,
                        "import": import_repr,
                        "issue": "hyphen path 'page-objects' should be 'page_objects'",
                    })
                    continue

                # Check 2: empty filename (path ends with '/')
                path_after_prefix = import_path.split("page_objects")[-1]
                if not path_after_prefix.lstrip("/"):
                    errors.append({
                        "file": filename,
                        "import": import_repr,
                        "issue": "empty filename in import path",
                    })
                    continue

                # Check 3: class name not found in any POM
                if class_name not in pom_class_names:
                    errors.append({
                        "file": filename,
                        "import": import_repr,
                        "issue": f"class '{class_name}' not found in provided page_objects",
                    })
                    continue

                correct += 1

    score = correct / total if total > 0 else 1.0
    return {
        "score": round(score, 4),
        "correct": correct,
        "total": total,
        "errors": errors,
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


# ---------------------------------------------------------------------------
# Plan Quality
# ---------------------------------------------------------------------------

def score_plan_quality(
    test_cases: list[dict],
    acceptance_criteria: list[str],
) -> dict[str, Any]:
    """Score overall quality of a generated test plan across three dimensions.

    Dimensions:
      - Step completeness: each test case should have >=2 steps and >=1 expected.
      - Deduplication: no two test cases should have >80% word overlap in titles.
      - Edge case coverage: at least 20% of test cases should mention error/negative scenarios.

    Returns a dict with an overall score (average of 3 sub-scores) and per-dimension details.
    """
    if not test_cases:
        return {
            "score": 0.0,
            "step_completeness": {"score": 0.0, "incomplete": []},
            "deduplication": {"score": 1.0, "duplicates": []},
            "edge_case_coverage": {"score": 0.0, "edge_case_count": 0, "total": 0},
        }

    total = len(test_cases)

    # --- Step completeness ---
    incomplete_ids: list[str] = []
    for tc in test_cases:
        steps = tc.get("steps", [])
        expected = tc.get("expected", [])
        if len(steps) < 2 or len(expected) < 1:
            incomplete_ids.append(tc.get("id", "unknown"))
    complete_count = total - len(incomplete_ids)
    step_completeness_score = complete_count / total

    # --- Deduplication ---
    _EDGE_KEYWORDS = {"invalid", "empty", "wrong", "error", "fail", "denied", "unauthorized"}
    _EDGE_TAGS = {"@error", "@negative", "@edge"}

    titles = [tc.get("title", "") for tc in test_cases]
    title_word_sets = [set(t.lower().split()) for t in titles]

    duplicate_pairs: list[list[str]] = []
    seen_duplicates: set[tuple[int, int]] = set()

    for i in range(total):
        for j in range(i + 1, total):
            set_i = title_word_sets[i]
            set_j = title_word_sets[j]
            union = set_i | set_j
            if not union:
                continue
            intersection = set_i & set_j
            jaccard = len(intersection) / len(union)
            if jaccard > 0.80:
                pair_key = (i, j)
                if pair_key not in seen_duplicates:
                    seen_duplicates.add(pair_key)
                    duplicate_pairs.append([titles[i], titles[j]])

    # Count unique titles (first occurrence of each duplicate cluster counts)
    duplicate_title_indices: set[int] = set()
    for i in range(total):
        for j in range(i + 1, total):
            set_i = title_word_sets[i]
            set_j = title_word_sets[j]
            union = set_i | set_j
            if not union:
                continue
            if len(set_i & set_j) / len(union) > 0.80:
                duplicate_title_indices.add(j)  # mark later duplicate

    unique_count = total - len(duplicate_title_indices)
    deduplication_score = unique_count / total

    # --- Edge case coverage ---
    edge_case_count = 0
    for tc in test_cases:
        steps_text = " ".join(tc.get("steps", [])).lower()
        expected_text = " ".join(tc.get("expected", [])).lower()
        combined_text = steps_text + " " + expected_text
        tags = {t.lower() for t in tc.get("tags", [])}

        has_edge_keyword = any(kw in combined_text for kw in _EDGE_KEYWORDS)
        has_edge_tag = bool(tags & _EDGE_TAGS)

        if has_edge_keyword or has_edge_tag:
            edge_case_count += 1

    edge_case_score = min(edge_case_count / (total * 0.20), 1.0)

    overall_score = round((step_completeness_score + deduplication_score + edge_case_score) / 3, 4)

    return {
        "score": overall_score,
        "step_completeness": {
            "score": round(step_completeness_score, 4),
            "incomplete": incomplete_ids,
        },
        "deduplication": {
            "score": round(deduplication_score, 4),
            "duplicates": duplicate_pairs,
        },
        "edge_case_coverage": {
            "score": round(edge_case_score, 4),
            "edge_case_count": edge_case_count,
            "total": total,
        },
    }


# ---------------------------------------------------------------------------
# Healer: Fix Correctness
# ---------------------------------------------------------------------------

def score_fix_correctness(
    scenarios: list[dict],
    healed_sources: dict[str, str],
) -> dict[str, Any]:
    """Score: what fraction of scenarios have the expected fix in the healed source?

    For each scenario that has ``expected_fix_contains``, check that the healed
    source for that scenario's route contains the expected string.

    Returns:
        {
            "score": float,
            "correct": int,
            "total": int,
            "misses": [{"scenario": str, "expected": str, "found": bool}],
        }
    """
    eligible = [s for s in scenarios if s.get("expected_fix_contains")]
    if not eligible:
        return {"score": 1.0, "correct": 0, "total": 0, "misses": []}

    misses: list[dict[str, Any]] = []
    correct = 0

    for s in eligible:
        route = s["route"]
        expected = s["expected_fix_contains"]
        healed = healed_sources.get(route, "")
        found = expected in healed
        if found:
            correct += 1
        else:
            misses.append({"scenario": s["scenario"], "expected": expected, "found": False})

    score = correct / len(eligible)
    return {
        "score": round(score, 4),
        "correct": correct,
        "total": len(eligible),
        "misses": misses,
    }


# ---------------------------------------------------------------------------
# Healer: Old Locator Removed
# ---------------------------------------------------------------------------

# Patterns for extracting the broken locator from an error message.
# Matches expressions like:
#   getByRole('button', { name: 'Submit' })
#   getByTestId('add-to-cart-btn')
#   getByLabel('Email address')
#   getByPlaceholder('Search products...')
#   getByAltText('Product thumbnail')
#   getByText('some text')
_BROKEN_LOCATOR_RE = re.compile(
    r"(getBy(?:Role|TestId|Label|Text|Placeholder|AltText)\s*\([^)]*\))"
)


def score_old_locator_removed(
    scenarios: list[dict],
    healed_sources: dict[str, str],
) -> dict[str, Any]:
    """Score: what fraction of scenarios no longer contain the old broken locator?

    Extracts the broken locator expression from each scenario's ``error`` field
    and checks that it does NOT appear verbatim in the healed source.

    Returns:
        {
            "score": float,
            "removed": int,
            "still_present": int,
            "total": int,
            "failures": [{"scenario": str, "old_locator": str}],
        }
    """
    if not scenarios:
        return {"score": 1.0, "removed": 0, "still_present": 0, "total": 0, "failures": []}

    failures: list[dict[str, Any]] = []
    removed = 0
    scored = 0

    for s in scenarios:
        error_text = s.get("error", "")
        match = _BROKEN_LOCATOR_RE.search(error_text)
        if not match:
            # Cannot determine old locator — skip this scenario
            continue

        old_locator = match.group(1)
        route = s["route"]
        healed = healed_sources.get(route, "")
        scored += 1

        if old_locator not in healed:
            removed += 1
        else:
            failures.append({"scenario": s["scenario"], "old_locator": old_locator})

    if scored == 0:
        return {"score": 1.0, "removed": 0, "still_present": 0, "total": 0, "failures": []}

    score = removed / scored
    return {
        "score": round(score, 4),
        "removed": removed,
        "still_present": scored - removed,
        "total": scored,
        "failures": failures,
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
