"""Test Validator — ensures generated test specs follow project conventions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of validating a test spec file."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False


# Inline selector patterns that should NOT appear in test files
INLINE_SELECTOR_PATTERNS = [
    r'page\.locator\(["\'][\.\#\[]',       # page.locator('.class'), page.locator('#id')
    r'page\.locator\(["\']div',             # page.locator('div...')
    r'page\.locator\(["\']span',            # page.locator('span...')
    r'page\.\$\(',                          # page.$()
    r'page\.\$\$\(',                        # page.$$()
    r'querySelector',                        # querySelector
]

# Hard wait patterns that should NOT appear
HARD_WAIT_PATTERNS = [
    r'page\.waitForTimeout\(',
    r'await\s+new\s+Promise.*setTimeout',
    r'sleep\(',
]


def validate_test(source: str, pom_class_name: str | None = None) -> ValidationResult:
    """Validate a generated test spec against project conventions.

    Checks:
    1. Imports from @playwright/test (test, expect)
    2. Imports the Page Object class
    3. Uses test.describe() for grouping
    4. Has test.beforeEach() for setup
    5. Has at least one test() block
    6. No inline selectors (all locators come from POM)
    7. No hard waits (waitForTimeout, setTimeout)
    8. Uses web-first assertions (expect().toBeVisible, etc.)

    Args:
        source: TypeScript test spec source code.
        pom_class_name: Expected POM class name to import (optional).

    Returns:
        ValidationResult with valid=True if all checks pass.
    """
    result = ValidationResult()

    # 1. Imports from @playwright/test
    if "@playwright/test" not in source:
        result.add_error("Missing import from '@playwright/test'")

    # 2. Imports the POM
    if not re.search(r"import\s+.*from\s+['\"]\.\.\/page_objects\/", source):
        result.add_error("Missing Page Object import from '../page_objects/'")

    # Specific POM class check if provided
    if pom_class_name and pom_class_name not in source:
        result.add_error(f"Missing import of POM class '{pom_class_name}'")

    # 3. Uses test.describe()
    if not re.search(r"test\.describe\s*\(", source):
        result.add_error("Missing 'test.describe()' block for grouping")

    # 4. Has test.beforeEach()
    if not re.search(r"test\.beforeEach\s*\(", source):
        result.add_error("Missing 'test.beforeEach()' for navigation setup")

    # 5. Has at least one test() block
    test_blocks = re.findall(r"(?<!\.)test\s*\(", source)
    # Filter out test.describe and test.beforeEach
    actual_tests = [t for t in re.findall(r"\btest\s*\(['\"]", source)]
    if len(actual_tests) < 1:
        result.add_error("Must have at least one test() block")

    # 6. No inline selectors
    for pattern in INLINE_SELECTOR_PATTERNS:
        match = re.search(pattern, source)
        if match:
            result.add_error(
                f"Inline selector detected: '{match.group()}' — use Page Object locators instead"
            )

    # 7. No hard waits
    for pattern in HARD_WAIT_PATTERNS:
        match = re.search(pattern, source)
        if match:
            result.add_error(
                f"Hard wait detected: '{match.group()}' — use web-first assertions instead"
            )

    # 8. Uses web-first assertions (expect)
    if "expect(" not in source:
        result.add_error("No web-first assertions found — use expect() with toBeVisible, toHaveText, etc.")

    return result
