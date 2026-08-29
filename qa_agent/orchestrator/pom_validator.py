"""POM Validator — ensures generated Page Objects follow project conventions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of validating a POM file."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False


# CSS selector patterns that should NEVER appear in POMs
CSS_SELECTOR_PATTERNS = [
    r'page\.locator\(["\'][\.\#\[]',       # page.locator('.class'), page.locator('#id'), page.locator('[attr]')
    r'page\.locator\(["\']div',             # page.locator('div...')
    r'page\.locator\(["\']span',            # page.locator('span...')
    r'page\.locator\(["\']button',          # page.locator('button...')
    r'page\.locator\(["\']input',           # page.locator('input...')
    r'page\.\$\(',                          # page.$()
    r'page\.\$\$\(',                        # page.$$()
    r'querySelector',                        # querySelector
]

# Assertion patterns that should NOT appear in page objects (they belong in tests)
ASSERTION_PATTERNS = [
    r'\bexpect\s*\(',
    r'\.toBeVisible\(',
    r'\.toHaveText\(',
    r'\.toHaveURL\(',
    r'\.toContainText\(',
    r'\.toBeEnabled\(',
    r'\.toBeDisabled\(',
    r'\.toHaveCount\(',
]

# Resilient locator patterns we WANT to see
RESILIENT_LOCATORS = [
    "getByRole",
    "getByTestId",
    "getByText",
    "getByLabel",
    "getByPlaceholder",
]


def validate_pom(source: str) -> ValidationResult:
    """Validate a generated POM file against project conventions.

    Checks:
    1. Has `export class` statement
    2. Constructor accepts `page: Page` parameter
    3. Uses resilient locators (getByRole, getByTestId, etc.)
    4. Does NOT use CSS selectors (page.locator('.class'), page.$())
    5. Has a `navigate()` method
    6. Imports from `@playwright/test`
    7. No test assertions (expect()) in page object code

    Returns:
        ValidationResult with valid=True if all checks pass.
    """
    result = ValidationResult()

    # 1. Has export class
    if not re.search(r"export\s+class\s+\w+", source):
        result.add_error("Missing 'export class' statement")

    # 2. Constructor with page: Page
    if "page: Page" not in source:
        result.add_error("Constructor must accept 'page: Page' parameter")

    # 3. Uses at least one resilient locator
    has_resilient = any(loc in source for loc in RESILIENT_LOCATORS)
    if not has_resilient:
        result.add_error(
            f"Must use at least one resilient locator: {', '.join(RESILIENT_LOCATORS)}"
        )

    # 4. No CSS selectors
    for pattern in CSS_SELECTOR_PATTERNS:
        match = re.search(pattern, source)
        if match:
            result.add_error(f"CSS selector detected: '{match.group()}' — use getByRole/getByTestId instead")

    # 5. Has navigate() method
    if not re.search(r"async\s+navigate\s*\(", source):
        result.add_error("Missing 'async navigate()' method")

    # 6. Imports from @playwright/test
    if "@playwright/test" not in source:
        result.add_error("Missing import from '@playwright/test'")

    # 7. No assertions in page object
    for pattern in ASSERTION_PATTERNS:
        match = re.search(pattern, source)
        if match:
            result.add_error(f"Assertion detected in page object: '{match.group()}' — assertions belong in test files")

    return result
