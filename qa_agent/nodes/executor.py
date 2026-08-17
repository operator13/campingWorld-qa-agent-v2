"""Step 4 · Executor — runs the generated tests and captures results.

Writes page objects and test files to disk, runs `npx playwright test`,
and parses the output into a RunResult.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from qa_agent.config import EnvConfig
from qa_agent.memory import MemoryStore
from qa_agent.schemas.models import RunResult
from qa_agent.state import QAState

logger = logging.getLogger(__name__)

# Project root for writing test files
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


async def executor(state: QAState) -> dict:
    """Write test files to disk and run them via Playwright."""
    logger.info("Executor: running %d test file(s)", len(state.test_code))

    # 1. Write page objects to disk
    po_dir = _PROJECT_ROOT / "page_objects"
    po_dir.mkdir(exist_ok=True)
    for route, source in state.page_objects.items():
        filename = _route_to_filename(route) + ".ts"
        filepath = po_dir / filename
        filepath.write_text(source)
        logger.info("  Wrote page object: %s", filepath)

    # 2. Write test files to disk
    test_dir = _PROJECT_ROOT / "tests_generated"
    test_dir.mkdir(exist_ok=True)
    for path, source in state.test_code.items():
        filepath = test_dir / Path(path).name
        filepath.write_text(source)
        logger.info("  Wrote test file: %s", filepath)

    # 3. Ensure playwright.config exists
    _ensure_playwright_config()

    # 4. Run the tests
    run_result, dom_snapshot = await _run_playwright_tests()

    logger.info("Executor: passed=%s, failed=%d case(s)",
                run_result.passed, len(run_result.failed_cases))

    # 5. Update memory — record route testids and per-test results
    memory = MemoryStore()
    for route in state.page_objects:
        # Discover testids from the page object source
        testids = _extract_testids(state.page_objects[route])
        memory.update_route(route, testids=testids)

    # Record per-test results for stability tracking
    # Note: failure_class left as None — Triage determines the actual class later
    for tc in state.plan:
        test_passed = tc.id not in run_result.failed_cases
        memory.record_test_result(tc.id, tc.route, test_passed)

    # If this is a re-run after healing and it passed, verify the fix in memory
    if run_result.passed and state.attempts > 0:
        # The healer recorded fixes as unverified — now mark them as verified
        for route in state.page_objects:
            history = memory.get_locator_history(route)
            for entry in history:
                if not entry.get("success"):
                    # Mark the most recent unverified fix as successful
                    memory.record_locator_change(
                        route, entry["element"],
                        entry["old_locator"], entry["new_locator"],
                        entry["reason"] + " (verified by re-run)", success=True,
                    )
                    break  # only the most recent unverified per route

    # Increment route change count on failure (locator drift signal)
    if not run_result.passed:
        for tc_id in run_result.failed_cases:
            for tc in state.plan:
                if tc.id == tc_id:
                    memory.increment_route_changes(tc.route)

    return {
        "run_results": run_result,
        "dom_snapshot": dom_snapshot,
        "error": None if run_result.passed else _extract_error(run_result.logs),
    }


async def _run_playwright_tests() -> tuple[RunResult, str | None]:
    """Execute `npx playwright test` and return results."""
    test_dir = _PROJECT_ROOT / "tests_generated"
    cfg = EnvConfig.from_env()

    env = {**os.environ}
    if cfg.app_base_url:
        env["BASE_URL"] = cfg.app_base_url

    cmd = [
        "npx", "playwright", "test",
        str(test_dir),
        "--reporter=json",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_PROJECT_ROOT),
            env=env,
        )
        stdout, stderr = await proc.communicate()
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        logs = stdout_str + "\n" + stderr_str

        passed = proc.returncode == 0
        failed_cases = _parse_failed_cases(stdout_str)

        # Collect screenshots
        screenshots = _collect_screenshots()

        return RunResult(
            passed=passed,
            failed_cases=failed_cases,
            logs=logs,
            screenshots=screenshots,
        ), None  # dom_snapshot captured separately if needed

    except FileNotFoundError:
        logger.error("Executor: npx/playwright not found — is Node.js installed?")
        return RunResult(
            passed=False,
            failed_cases=[],
            logs="ERROR: npx or playwright not found. Install Node.js and run: npm init playwright@latest",
            screenshots=[],
        ), None


def _parse_failed_cases(output: str) -> list[str]:
    """Parse failed test names from Playwright JSON output."""
    import json as json_mod

    try:
        data = json_mod.loads(output)
        failed = []
        for suite in data.get("suites", []):
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    if test.get("status") != "expected":
                        failed.append(spec.get("title", "unknown"))
        return failed
    except (json_mod.JSONDecodeError, KeyError):
        # Fallback: look for "FAIL" lines
        return [
            line.strip()
            for line in output.split("\n")
            if "FAIL" in line or "✗" in line or "×" in line
        ]


def _collect_screenshots() -> list[str]:
    """Collect screenshot paths from test-results/."""
    results_dir = _PROJECT_ROOT / "test-results"
    if not results_dir.exists():
        return []
    return [str(p) for p in results_dir.rglob("*.png")]


def _extract_error(logs: str) -> str:
    """Extract the most relevant error message from logs."""
    lines = logs.split("\n")
    error_lines = [l for l in lines if "Error" in l or "error" in l or "FAIL" in l]
    return "\n".join(error_lines[:10]) if error_lines else "Test run failed (see logs)"


def _extract_testids(source: str) -> list[str]:
    """Extract data-testid values from page object source code."""
    import re
    return re.findall(r"getByTestId\(['\"]([^'\"]+)['\"]\)", source)


def _route_to_filename(route: str) -> str:
    """Convert a route like '/checkout' to a filename like 'CheckoutPage'."""
    parts = route.strip("/").split("/")
    name = "".join(p.capitalize() for p in parts if p) or "Home"
    return f"{name}Page"


def _ensure_playwright_config() -> None:
    """Write a basic playwright.config.ts if one doesn't exist."""
    config_path = _PROJECT_ROOT / "playwright.config.ts"
    if config_path.exists():
        return

    cfg = EnvConfig.from_env()
    config_path.write_text(f"""\
import {{ defineConfig, devices }} from '@playwright/test';

export default defineConfig({{
  testDir: './tests_generated',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'json',
  use: {{
    baseURL: process.env.BASE_URL || '{cfg.app_base_url}',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  }},
  projects: [
    {{ name: 'chromium', use: {{ ...devices['Desktop Chrome'] }} }},
    {{ name: 'mobile-chrome', use: {{ ...devices['Pixel 7'] }} }},
    {{ name: 'mobile-safari', use: {{ ...devices['iPhone 15'] }} }},
  ],
}});
""")
    logger.info("Wrote default playwright.config.ts")
