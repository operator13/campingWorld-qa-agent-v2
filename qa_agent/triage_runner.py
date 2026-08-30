"""Triage Runner — connects Playwright test failures to the triage → healer self-healing loop.

Parses Playwright JSON results, feeds failures to triage for classification,
auto-heals locator drift via the healer, and re-runs fixed tests.

Usage:
    python3 -m qa_agent.triage_runner results.json
    qa-agent triage --results results.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from qa_agent.config import CONF_SURE
from qa_agent.nodes.healer import healer
from qa_agent.nodes.triage import triage
from qa_agent.schemas.models import RunResult, TestCase
from qa_agent.state import QAState

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PAGE_OBJECTS_DIR = _PROJECT_ROOT / "page_objects"
_TESTS_DIR = _PROJECT_ROOT / "tests_generated"

# Spec file → POM file → route mapping
_SPEC_TO_POM: dict[str, tuple[str, str]] = {
    "homepage.spec.ts": ("HomepagePage.ts", "/"),
    "nav.spec.ts": ("NavPage.ts", "/nav"),
    "search.spec.ts": ("SearchPage.ts", "/search"),
    "product.spec.ts": ("ProductPage.ts", "/product"),
    "cart.spec.ts": ("CartPage.ts", "/cart"),
    "checkout.spec.ts": ("CheckoutPage.ts", "/checkout"),
    "sign-in.spec.ts": ("SignInPage.ts", "/sign-in"),
    "register.spec.ts": ("RegisterPage.ts", "/register"),
    "store-locator.spec.ts": ("StoreLocatorPage.ts", "/store-locator"),
    "rvs-for-sale.spec.ts": ("RvsForSalePage.ts", "/rvs-for-sale"),
    "rvs-for-sale-detail.spec.ts": ("RvsForSaleDetailPage.ts", "/rvs-for-sale/detail"),
    "good-sam.spec.ts": ("GoodSamPage.ts", "/good-sam"),
    "footer.spec.ts": ("FooterPage.ts", "/footer"),
    "rv-parts.spec.ts": ("RvPartsPage.ts", "/rv-parts"),
}


def parse_failures(results_json_path: Path) -> list[dict[str, Any]]:
    """Parse Playwright JSON results and extract failed test details."""
    with open(results_json_path) as f:
        data = json.load(f)

    failures = []
    for suite in data.get("suites", []):
        _extract_failures(suite, failures)

    logger.info("Parsed %d failure(s) from %s", len(failures), results_json_path.name)
    return failures


def _extract_failures(suite: dict, failures: list[dict], spec_file: str | None = None) -> None:
    """Recursively extract failures from a suite."""
    # Top-level suite title is the spec file
    title = suite.get("title", "")
    if title.endswith(".spec.ts"):
        spec_file = title

    for spec in suite.get("specs", []):
        if spec.get("ok", True):
            continue

        for test in spec.get("tests", []):
            if test.get("status") == "expected":
                continue

            for result in test.get("results", []):
                if result.get("status") == "passed":
                    continue

                for error in result.get("errors", []):
                    error_msg = error.get("message", "")
                    # Strip ANSI codes
                    error_msg = re.sub(r"\x1b\[[0-9;]*m", "", error_msg)

                    file_name = spec.get("file", spec_file or "unknown")
                    pom_file, route = _SPEC_TO_POM.get(file_name, (None, None))

                    failures.append({
                        "spec_file": file_name,
                        "test_title": spec.get("title", "unknown"),
                        "line": spec.get("line", 0),
                        "error": error_msg,
                        "pom_file": pom_file,
                        "route": route,
                    })
                    break  # One error per test is enough
                break
        # Don't duplicate — one failure entry per spec


    for child in suite.get("suites", []):
        _extract_failures(child, failures, spec_file)


async def run_triage_and_heal(failures: list[dict[str, Any]]) -> dict[str, Any]:
    """Triage each failure and heal locator drift.

    Returns summary: {triaged, healed, app_defects, unknown, healed_files, details}
    """
    total = len(failures)
    healed_count = 0
    app_defect_count = 0
    unknown_count = 0
    healed_files: list[str] = []
    healed_specs: set[str] = set()
    details: list[dict[str, Any]] = []

    for i, failure in enumerate(failures, 1):
        spec = failure["spec_file"]
        title = failure["test_title"]
        error = failure["error"]
        pom_file = failure["pom_file"]
        route = failure["route"]

        print(f"\n  [{i}/{total}] {spec}:{failure['line']} \"{title}\"")

        # Build triage state
        state = QAState(
            goal=f"triage:{spec}:{title}",
            error=error,
            run_results=RunResult(
                passed=False,
                failed_cases=[title],
                logs=error,
            ),
            attempts=0,
        )

        # Call triage
        try:
            result = await triage(state)
            failure_class = result.get("failure_class", "unknown")
            confidence = result.get("confidence", 0.0)
        except Exception as e:
            logger.error("Triage failed for %s: %s", title, e)
            failure_class = "error"
            confidence = 0.0

        print(f"        Triage: {failure_class} (confidence: {confidence:.2f})")

        detail = {
            "spec_file": spec,
            "test_title": title,
            "failure_class": failure_class,
            "confidence": confidence,
            "healed": False,
        }

        # Heal if locator drift or test flake with high confidence
        if failure_class == "locator_drift" and confidence >= CONF_SURE and pom_file and route:
            pom_path = _PAGE_OBJECTS_DIR / pom_file
            if pom_path.exists():
                pom_source = pom_path.read_text()

                # Backup original
                backup_path = pom_path.with_suffix(".ts.bak")
                if not backup_path.exists():
                    shutil.copy2(pom_path, backup_path)

                # Build healer state
                heal_state = QAState(
                    goal=f"heal:{spec}:{title}",
                    error=error,
                    failure_class="locator_drift",
                    page_objects={route: pom_source},
                    plan=[TestCase(
                        id=f"tc-{spec}",
                        title=title,
                        feature=spec.replace(".spec.ts", ""),
                        route=route,
                        steps=["(from failed test)"],
                        expected=["(test should pass)"],
                    )],
                    run_results=RunResult(passed=False, failed_cases=[title], logs=error),
                    attempts=0,
                )

                try:
                    heal_result = await healer(heal_state)
                    patched = heal_result.get("page_objects", {})
                    if route in patched and patched[route] != pom_source:
                        pom_path.write_text(patched[route])
                        healed_count += 1
                        healed_files.append(pom_file)
                        healed_specs.add(spec)
                        detail["healed"] = True
                        print(f"        Healing: {pom_file} -> fixed (locator)")
                    else:
                        print(f"        Healing: no changes produced")
                except Exception as e:
                    logger.error("Healer failed for %s: %s", pom_file, e)
                    print(f"        Healing: FAILED ({e})")
            else:
                print(f"        Skipped: POM file {pom_file} not found")
        elif failure_class == "test_flake" and confidence >= CONF_SURE and route:
            # Timing fix — patch the spec file, not the POM
            spec_path = _TESTS_DIR / spec
            if spec_path.exists():
                spec_source = spec_path.read_text()

                # Backup original
                backup_path = spec_path.with_suffix(".ts.bak")
                if not backup_path.exists():
                    shutil.copy2(spec_path, backup_path)

                # Build healer state with spec file source
                pom_source = ""
                if pom_file:
                    pom_path = _PAGE_OBJECTS_DIR / pom_file
                    if pom_path.exists():
                        pom_source = pom_path.read_text()

                heal_state = QAState(
                    goal=f"heal:{spec}:{title}",
                    error=error,
                    failure_class="test_flake",
                    test_code={spec: spec_source},
                    page_objects={route: pom_source} if pom_source else {},
                    plan=[TestCase(
                        id=f"tc-{spec}",
                        title=title,
                        feature=spec.replace(".spec.ts", ""),
                        route=route,
                        steps=["(from failed test)"],
                        expected=["(test should pass)"],
                    )],
                    run_results=RunResult(passed=False, failed_cases=[title], logs=error),
                    attempts=0,
                )

                try:
                    heal_result = await healer(heal_state)
                    patched_specs = heal_result.get("test_code", {})
                    if spec in patched_specs and patched_specs[spec] != spec_source:
                        spec_path.write_text(patched_specs[spec])
                        healed_count += 1
                        healed_files.append(spec)
                        healed_specs.add(spec)
                        detail["healed"] = True
                        print(f"        Healing: {spec} -> fixed (timing)")
                    else:
                        print(f"        Healing: no timing changes produced")
                except Exception as e:
                    logger.error("Healer timing fix failed for %s: %s", spec, e)
                    print(f"        Healing: FAILED ({e})")
            else:
                print(f"        Skipped: spec file {spec} not found")
        elif failure_class == "app_defect":
            app_defect_count += 1
            print(f"        Skipped: app defect — not a locator issue")
        else:
            unknown_count += 1
            reason = "low confidence — needs human review" if failure_class in ("locator_drift", "test_flake") else f"classified as {failure_class}"
            print(f"        Skipped: {reason}")

        details.append(detail)

    return {
        "triaged": total,
        "healed": healed_count,
        "app_defects": app_defect_count,
        "unknown": unknown_count,
        "healed_files": healed_files,
        "healed_specs": list(healed_specs),
        "details": details,
    }


def rerun_healed_specs(specs: list[str], output_dir: Path | None = None) -> int:
    """Re-run only the healed spec files."""
    if not specs:
        return 0

    spec_paths = [str(_TESTS_DIR / s) for s in specs]
    cmd = ["npx", "playwright", "test", "--retries=0", "--workers=1"] + spec_paths

    print(f"\n=== Re-running {len(specs)} healed spec(s) ===\n")

    result = subprocess.run(
        cmd,
        cwd=str(_PROJECT_ROOT),
        capture_output=False,
        timeout=300,
    )

    return result.returncode


async def run_self_healing(results_json_path: Path) -> dict[str, Any]:
    """Full self-healing flow: parse → triage → heal → re-run → save report."""
    from datetime import datetime, timezone

    print("\n=== Self-Healing: Triaging failures ===")

    failures = parse_failures(results_json_path)
    if not failures:
        print("  No failures to triage.")
        return {"triaged": 0, "healed": 0}

    summary = await run_triage_and_heal(failures)

    print(f"\n  Summary: {summary['triaged']} triaged, {summary['healed']} healed, "
          f"{summary['app_defects']} app defect(s), {summary['unknown']} unknown")

    # Re-run healed specs
    if summary["healed_specs"]:
        rerun_code = rerun_healed_specs(summary["healed_specs"])
        summary["rerun_passed"] = rerun_code == 0

        # Git commit healed files
        if summary["healed_files"]:
            _git_commit_healed(summary["healed_files"])

    # Save triage report alongside health reports
    timestamp = datetime.now(tz=timezone.utc).strftime("%m_%d_%Y_%H-%M-%S")
    summary["timestamp"] = datetime.now(tz=timezone.utc).isoformat()
    _save_triage_report(summary, timestamp)

    return summary


def _save_triage_report(summary: dict[str, Any], timestamp: str) -> None:
    """Save triage report as JSON and markdown to health-reports/."""
    reports_dir = _PROJECT_ROOT / "health-reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = reports_dir / f"{timestamp}-triage.json"
    json_path.write_text(json.dumps(summary, indent=2, default=str))

    # Markdown
    md_path = reports_dir / f"{timestamp}-triage.md"
    md_path.write_text(_format_triage_markdown(summary))

    # Git commit the report
    try:
        subprocess.run(
            ["git", "add", str(json_path), str(md_path)],
            cwd=str(_PROJECT_ROOT), capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "commit", "-m",
             f"Triage report: {summary['triaged']} triaged, {summary['healed']} healed"],
            cwd=str(_PROJECT_ROOT), capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "push"],
            cwd=str(_PROJECT_ROOT), capture_output=True, timeout=30,
        )
        logger.info("Triage report pushed to GitHub")
    except Exception as e:
        logger.warning("Triage report git push failed: %s", e)

    # Notify dashboard
    _notify_dashboard_health(timestamp)

    print(f"\n  Triage report saved: health-reports/{timestamp}-triage.json")
    print(f"  Triage report saved: health-reports/{timestamp}-triage.md")


def _notify_dashboard_health(run_id: str) -> None:
    """Notify the dashboard server that a health/triage report was saved."""
    import urllib.request
    try:
        data = json.dumps({"run_id": run_id}).encode()
        req = urllib.request.Request(
            "http://localhost:8080/api/health/notify",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass  # Dashboard may not be running


def _format_triage_markdown(summary: dict[str, Any]) -> str:
    """Format triage summary as human-readable markdown."""
    lines = [
        "# Triage Report",
        "",
        f"**Timestamp:** {summary.get('timestamp', 'unknown')}",
        f"**Triaged:** {summary['triaged']}",
        f"**Healed:** {summary['healed']}",
        f"**App Defects:** {summary.get('app_defects', 0)}",
        f"**Unknown:** {summary.get('unknown', 0)}",
        "",
    ]

    if summary.get("healed_files"):
        lines.append("## Healed Files")
        lines.append("")
        for f in summary["healed_files"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if summary.get("rerun_passed") is not None:
        status = "PASSED" if summary["rerun_passed"] else "FAILED"
        lines.append(f"## Re-run Result: {status}")
        lines.append("")

    details = summary.get("details", [])
    if details:
        lines.append("## Failure Details")
        lines.append("")
        for d in details:
            healed_tag = " (HEALED)" if d.get("healed") else ""
            lines.append(f"### {d['spec_file']} — \"{d['test_title']}\"{healed_tag}")
            lines.append("")
            lines.append(f"- **Classification:** {d['failure_class']}")
            lines.append(f"- **Confidence:** {d['confidence']:.2f}")
            if d["failure_class"] == "locator_drift" and d.get("healed"):
                lines.append(f"- **Action:** Auto-healed by healer agent (locator fix)")
            elif d["failure_class"] == "test_flake" and d.get("healed"):
                lines.append(f"- **Action:** Auto-healed by healer agent (timing fix)")
            elif d["failure_class"] == "app_defect":
                lines.append(f"- **Action:** Skipped — app defect, not a locator issue")
            elif d["failure_class"] in ("locator_drift", "test_flake") and not d.get("healed"):
                lines.append(f"- **Action:** Skipped — confidence below threshold ({d['confidence']:.2f} < 0.75)")
            else:
                lines.append(f"- **Action:** Skipped — needs human review")
            lines.append("")

    return "\n".join(lines)


def _git_commit_healed(healed_files: list[str]) -> None:
    """Commit healed POM and spec files to git."""
    try:
        for f in healed_files:
            if f.endswith(".spec.ts"):
                path = f"tests_generated/{f}"
            else:
                path = f"page_objects/{f}"
            subprocess.run(
                ["git", "add", path],
                cwd=str(_PROJECT_ROOT),
                capture_output=True,
                timeout=10,
            )
        subprocess.run(
            ["git", "commit", "-m",
             f"Self-healed {len(healed_files)} file(s): {', '.join(healed_files)}\n\n"
             f"Auto-fixed by triage → healer pipeline."],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            timeout=10,
        )
        result = subprocess.run(
            ["git", "push"],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            print("\n  Healed files committed and pushed to GitHub")
        else:
            logger.warning("Git push failed: %s", result.stderr.decode()[:200])
    except Exception as e:
        logger.warning("Auto-commit of healed files failed: %s", e)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python -m qa_agent.triage_runner <results.json>")
        sys.exit(1)

    results_path = Path(sys.argv[1])
    if not results_path.exists():
        print(f"[ERROR] File not found: {results_path}")
        sys.exit(1)

    summary = asyncio.run(run_self_healing(results_path))
    sys.exit(0 if summary.get("healed", 0) > 0 else 1)
