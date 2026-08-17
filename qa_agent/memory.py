"""Agent memory — markdown-backed persistent store for cross-run learning.

Git-tracked markdown files that agents read/write so past experience
informs future decisions. Separate from metrics (SQLite) which handles
aggregation queries.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"


# ---------------------------------------------------------------------------
# Error normalization + locator extraction
# ---------------------------------------------------------------------------

def normalize_error(error: str) -> str:
    """Strip volatile parts from an error message for pattern matching.

    Removes line numbers, file paths, timestamps, IPs, and specific timeout
    values so the same underlying error matches across runs.
    """
    s = error
    s = re.sub(r"line \d+", "line N", s)
    s = re.sub(r"column \d+", "column N", s)
    s = re.sub(r"/[\w./\-]+\.(ts|js|py)", "FILE", s)
    s = re.sub(r"Timeout \d+ms", "Timeout Nms", s)
    s = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?", "DATETIME", s)
    s = re.sub(r"\d+\.\d+\.\d+\.\d+", "IP", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_locator_from_error(error: str) -> str | None:
    """Extract the locator string from a Playwright timeout/not-found error.

    Looks for getByRole(...), getByTestId(...), getByText(...), etc.
    Returns the matched locator string or None.
    """
    patterns = [
        r"getByRole\([^)]+\)",
        r"getByTestId\([^)]+\)",
        r"getByText\([^)]+\)",
        r"getByLabel\([^)]+\)",
        r"getByPlaceholder\([^)]+\)",
        r"getByAltText\([^)]+\)",
        r"locator\([^)]+\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, error)
        if match:
            return match.group(0)
    return None


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------

class MemoryStore:
    """Unified read/write interface for agent memory (markdown-backed).

    All reads parse markdown on the fly. All writes append or update
    markdown files. Designed for small volumes (hundreds of entries).
    """

    def __init__(self, memory_dir: str | Path | None = None) -> None:
        self.memory_dir = Path(memory_dir or _DEFAULT_MEMORY_DIR)
        self.locators_dir = self.memory_dir / "locators"
        self.locators_dir.mkdir(parents=True, exist_ok=True)

    def _enabled(self, node: str | None = None) -> bool:
        """Check if memory is enabled (globally and per-node)."""
        if os.getenv("MEMORY_ENABLED", "true").lower() != "true":
            return False
        if node:
            env_key = f"{node.upper()}_MEMORY"
            if os.getenv(env_key, "true").lower() != "true":
                return False
        return True

    # -------------------------------------------------------------------
    # Locator History
    # -------------------------------------------------------------------

    def _locator_file(self, route: str) -> Path:
        """Get the markdown file path for a route's locator history."""
        safe_name = (route.strip("/").replace("/", "_") or "root").upper()
        return self.locators_dir / f"{safe_name}.md"

    def record_locator_change(
        self,
        route: str,
        element: str,
        old_locator: str,
        new_locator: str,
        reason: str = "",
        success: bool = True,
    ) -> None:
        """Append a locator change entry to the route's history file."""
        if not self._enabled("healer"):
            return

        filepath = self._locator_file(route)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        success_str = "yes" if success else "no"
        entry = f"- {now}: `{old_locator}` → `{new_locator}` | reason: {reason} | success: {success_str}\n"

        # Read existing content or start fresh
        if filepath.exists():
            content = filepath.read_text()
        else:
            content = f"# Locator History: {route}\n\n"

        # Find or create the element section
        section_header = f"## {element}"
        if section_header in content:
            # Append under existing section
            idx = content.index(section_header)
            # Find the end of this section (next ## or EOF)
            next_section = content.find("\n## ", idx + len(section_header))
            if next_section == -1:
                content = content.rstrip() + "\n" + entry
            else:
                content = content[:next_section] + entry + content[next_section:]
        else:
            # Add new section
            content = content.rstrip() + f"\n\n{section_header}\n{entry}"

        filepath.write_text(content)
        logger.info("Memory: recorded locator change for %s → %s", route, element)

    def get_locator_history(self, route: str, element_name: str | None = None) -> list[dict[str, Any]]:
        """Read locator history for a route, optionally filtered by element."""
        if not self._enabled("healer"):
            return []

        filepath = self._locator_file(route)
        if not filepath.exists():
            return []

        content = filepath.read_text()
        entries = []
        current_element = ""

        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("## "):
                current_element = line[3:].strip()
            elif line.startswith("- ") and "→" in line:
                if element_name and current_element != element_name:
                    continue
                entry = self._parse_locator_entry(line, current_element)
                if entry:
                    entries.append(entry)

        return entries

    def get_known_fix(self, route: str, element: str, old_locator: str) -> str | None:
        """Look up a known fix for a specific locator drift.

        Returns the new locator if a successful fix exists, None otherwise.
        Only returns fixes where success=yes.
        """
        if not self._enabled("healer"):
            return None

        history = self.get_locator_history(route, element)
        for entry in reversed(history):  # most recent first
            if entry.get("old_locator") == old_locator and entry.get("success"):
                return entry.get("new_locator")
        return None

    def mark_fix_failed(self, route: str, element: str, old_locator: str) -> None:
        """Mark a previously successful fix as failed (stale).

        Rewrites the entry with success: no so it won't be reused.
        """
        if not self._enabled("healer"):
            return

        filepath = self._locator_file(route)
        if not filepath.exists():
            return

        content = filepath.read_text()
        # Find the entry with this old_locator and success: yes, change to success: no
        old_pattern = f"`{old_locator}` →"
        if old_pattern in content:
            content = content.replace(
                f"{old_pattern}",
                f"{old_pattern}",  # keep the locator
            )
            # Replace the last "success: yes" on lines containing this locator
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if old_pattern.replace("`", "`") in line and "success: yes" in line:
                    lines[i] = line.replace("success: yes", "success: no")
            content = "\n".join(lines)
            filepath.write_text(content)
            logger.info("Memory: marked fix as failed for %s → %s", route, element)

    @staticmethod
    def _parse_locator_entry(line: str, element: str) -> dict[str, Any] | None:
        """Parse a locator history line into a dict."""
        # Format: - 2026-07-18: `old` → `new` | reason: text | success: yes
        match = re.match(
            r"- (\d{4}-\d{2}-\d{2}): `([^`]+)` → `([^`]+)` \| reason: (.*?) \| success: (yes|no)",
            line,
        )
        if not match:
            return None
        return {
            "date": match.group(1),
            "element": element,
            "old_locator": match.group(2),
            "new_locator": match.group(3),
            "reason": match.group(4).strip(),
            "success": match.group(5) == "yes",
        }

    # -------------------------------------------------------------------
    # Failure Patterns
    # -------------------------------------------------------------------

    def record_failure(
        self,
        error_signature: str,
        failure_class: str,
        resolution: str,
        route: str = "",
    ) -> None:
        """Record or update a failure pattern."""
        if not self._enabled():
            return

        filepath = self.memory_dir / "FAILURES.md"
        normalized = normalize_error(error_signature)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        existing = self.find_similar_failure(normalized)
        if existing:
            # Update occurrences in place
            self._increment_failure_occurrence(filepath, existing["id"], now)
            return

        # Generate a new ID
        content = filepath.read_text() if filepath.exists() else "# Failure Patterns\n"
        pattern_ids = re.findall(r"## FP-(\d+)", content)
        next_id = max((int(x) for x in pattern_ids), default=0) + 1
        fp_id = f"FP-{next_id:03d}"

        stale_date = _add_days(now, 90)
        entry = (
            f"\n## {fp_id}: {normalized[:80]}\n"
            f"- **Signature:** `{normalized}`\n"
            f"- **Class:** {failure_class}\n"
            f"- **Resolution:** {resolution}\n"
            f"- **Routes:** {route or 'unknown'}\n"
            f"- **Occurrences:** 1\n"
            f"- **Last seen:** {now}\n"
            f"- **Stale after:** {stale_date}\n"
        )

        content = content.rstrip() + "\n" + entry
        filepath.write_text(content)
        logger.info("Memory: recorded failure pattern %s", fp_id)

    def find_similar_failure(self, error_signature: str) -> dict[str, Any] | None:
        """Find a failure pattern matching the given error signature.

        Uses normalized substring matching.
        """
        if not self._enabled():
            return None

        filepath = self.memory_dir / "FAILURES.md"
        if not filepath.exists():
            return None

        normalized = normalize_error(error_signature)
        content = filepath.read_text()
        patterns = self._parse_failure_patterns(content)

        for pattern in patterns:
            stored_sig = pattern.get("signature", "")
            # Substring match in either direction
            if stored_sig in normalized or normalized in stored_sig:
                return pattern

        return None

    def _parse_failure_patterns(self, content: str) -> list[dict[str, Any]]:
        """Parse all failure patterns from the FAILURES.md file."""
        patterns = []
        current: dict[str, Any] = {}

        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("## FP-"):
                if current:
                    patterns.append(current)
                fp_id = line.split(":")[0].replace("## ", "")
                current = {"id": fp_id}
            elif line.startswith("- **Signature:**"):
                sig = re.search(r"`([^`]+)`", line)
                current["signature"] = sig.group(1) if sig else ""
            elif line.startswith("- **Class:**"):
                current["failure_class"] = line.split(":", 1)[1].strip().lstrip("*").rstrip("*").strip()
            elif line.startswith("- **Resolution:**"):
                current["resolution"] = line.split(":", 1)[1].strip().lstrip("*").rstrip("*").strip()
            elif line.startswith("- **Routes:**"):
                current["routes"] = line.split(":", 1)[1].strip().lstrip("*").rstrip("*").strip()
            elif line.startswith("- **Occurrences:**"):
                try:
                    current["occurrences"] = int(line.split(":", 1)[1].strip().lstrip("*").rstrip("*").strip())
                except ValueError:
                    current["occurrences"] = 1
            elif line.startswith("- **Last seen:**"):
                current["last_seen"] = line.split(":", 1)[1].strip().lstrip("*").rstrip("*").strip()

        if current and "id" in current:
            patterns.append(current)

        return patterns

    def _increment_failure_occurrence(self, filepath: Path, fp_id: str, date: str) -> None:
        """Increment the occurrence count and update last_seen for a failure pattern."""
        content = filepath.read_text()
        lines = content.split("\n")

        in_target = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"## {fp_id}"):
                in_target = True
            elif line.strip().startswith("## FP-") and in_target:
                break
            elif in_target and "**Occurrences:**" in line:
                count_match = re.search(r"\d+", line)
                if count_match:
                    new_count = int(count_match.group()) + 1
                    lines[i] = f"- **Occurrences:** {new_count}"
            elif in_target and "**Last seen:**" in line:
                lines[i] = f"- **Last seen:** {date}"

        filepath.write_text("\n".join(lines))

    # -------------------------------------------------------------------
    # Human Decisions
    # -------------------------------------------------------------------

    def record_human_decision(
        self,
        triage_guess: str,
        confidence: float,
        verdict: str,
        error_summary: str = "",
        reasoning: str = "",
        route: str = "",
    ) -> None:
        """Record a Human Review verdict to HUMAN_DECISIONS.md."""
        if not self._enabled("triage"):
            return

        filepath = self.memory_dir / "HUMAN_DECISIONS.md"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if not filepath.exists():
            filepath.write_text(
                "# Human Review Decisions\n\n"
                "| Date | Route | Error (summary) | Triage guess | Confidence | Human verdict | Reasoning |\n"
                "|------|-------|----------------|--------------|------------|---------------|----------|\n"
            )

        # Sanitize fields for markdown table (no pipes or newlines)
        error_clean = error_summary.replace("|", "/").replace("\n", " ")[:100]
        reasoning_clean = reasoning.replace("|", "/").replace("\n", " ")[:100]

        row = f"| {now} | {route} | {error_clean} | {triage_guess} | {confidence:.2f} | {verdict} | {reasoning_clean} |\n"
        with open(filepath, "a") as f:
            f.write(row)

        logger.info("Memory: recorded human decision — %s → %s", triage_guess, verdict)

    def get_triage_calibration(self, n: int = 10) -> list[dict[str, Any]]:
        """Read the last N human decisions for Triage calibration.

        Returns most recent first.
        """
        if not self._enabled("triage"):
            return []

        filepath = self.memory_dir / "HUMAN_DECISIONS.md"
        if not filepath.exists():
            return []

        content = filepath.read_text()
        entries = []

        for line in content.split("\n"):
            line = line.strip()
            if not line.startswith("|") or line.startswith("| Date") or line.startswith("|---"):
                continue

            # Split on | and drop the first/last empty strings from leading/trailing |
            parts = [p.strip() for p in line.split("|")]
            # A row like "| a | b | c |" splits to ['', 'a', 'b', 'c', '']
            if len(parts) >= 2:
                parts = parts[1:-1]  # drop empty first/last

            if len(parts) >= 6:
                conf_str = parts[4].strip()
                try:
                    conf = float(conf_str)
                except ValueError:
                    conf = 0.0
                entries.append({
                    "date": parts[0],
                    "route": parts[1],
                    "error_summary": parts[2],
                    "triage_guess": parts[3],
                    "confidence": conf,
                    "human_verdict": parts[5],
                    "reasoning": parts[6] if len(parts) > 6 else "",
                })

        # Return last N, most recent first
        return list(reversed(entries[-n:]))

    def build_triage_calibration_context(self, max_tokens: int = 500) -> str:
        """Build calibration context for injection into the Triage prompt.

        Includes recent human corrections as few-shot examples.
        """
        if not self._enabled("triage"):
            return ""

        decisions = self.get_triage_calibration(n=10)
        if not decisions:
            return ""

        # Map triage_guess to human verdict space for comparison
        # locator_drift → heal, app_defect → defect, unknown → neither
        def _is_agreement(d: dict) -> bool:
            guess = d["triage_guess"]
            verdict = d["human_verdict"]
            return (guess == "locator_drift" and verdict == "heal") or \
                   (guess == "app_defect" and verdict == "defect")

        corrections = [d for d in decisions if not _is_agreement(d)]
        confirmations = [d for d in decisions if _is_agreement(d)]

        lines = ["## Memory: Recent Human Review Decisions"]
        lines.append("Learn from these — adjust your confidence accordingly.\n")

        if corrections:
            lines.append("**Corrections (you were wrong):**")
            for d in corrections[:5]:
                lines.append(
                    f"- Error: \"{d['error_summary']}\" → You said: {d['triage_guess']} ({d['confidence']:.2f})"
                    f" → Human corrected to: {d['human_verdict']}."
                    + (f" Why: {d['reasoning']}" if d['reasoning'] else "")
                )

        if confirmations:
            lines.append("\n**Confirmations (you were right):**")
            for d in confirmations[:3]:
                lines.append(
                    f"- Error: \"{d['error_summary']}\" → You said: {d['triage_guess']} ({d['confidence']:.2f})"
                    f" → Human confirmed."
                )

        result = "\n".join(lines)

        char_limit = max_tokens * 4
        if len(result) > char_limit:
            result = result[:char_limit].rsplit("\n", 1)[0]

        return result

    # -------------------------------------------------------------------
    # App Structure
    # -------------------------------------------------------------------

    def update_route(
        self,
        route: str,
        testids: list[str] | None = None,
        components: list[str] | None = None,
    ) -> None:
        """Write or update a route entry in APP_STRUCTURE.md."""
        if not self._enabled("generator"):
            return

        filepath = self.memory_dir / "APP_STRUCTURE.md"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if not filepath.exists():
            filepath.write_text("# App Structure\n")

        content = filepath.read_text()
        section_header = f"## {route}"

        testids_str = ", ".join(testids) if testids else "none discovered"
        components_str = ", ".join(components) if components else "none discovered"

        new_section = (
            f"\n{section_header}\n"
            f"- **Last seen:** {now}\n"
            f"- **Known testids:** {testids_str}\n"
            f"- **Components:** {components_str}\n"
        )

        if section_header in content:
            # Replace existing section
            idx = content.index(section_header)
            next_section = content.find("\n## ", idx + len(section_header))

            # Preserve change_count if it exists
            old_section = content[idx:next_section] if next_section != -1 else content[idx:]
            change_count = self._extract_change_count(old_section)
            first_seen = self._extract_first_seen(old_section) or now

            weeks = max(1, (datetime.strptime(now, "%Y-%m-%d") - datetime.strptime(first_seen, "%Y-%m-%d")).days / 7)
            change_freq = round(change_count / weeks, 1)

            new_section = (
                f"{section_header}\n"
                f"- **First seen:** {first_seen}\n"
                f"- **Last seen:** {now}\n"
                f"- **Changes:** {change_count}\n"
                f"- **Change frequency:** {change_freq}/week\n"
                f"- **Known testids:** {testids_str}\n"
                f"- **Components:** {components_str}\n"
            )

            if next_section != -1:
                content = content[:idx] + new_section + content[next_section:]
            else:
                content = content[:idx] + new_section
        else:
            # New route — append
            new_section = (
                f"\n{section_header}\n"
                f"- **First seen:** {now}\n"
                f"- **Last seen:** {now}\n"
                f"- **Changes:** 0\n"
                f"- **Change frequency:** 0.0/week\n"
                f"- **Known testids:** {testids_str}\n"
                f"- **Components:** {components_str}\n"
            )
            content = content.rstrip() + "\n" + new_section

        filepath.write_text(content)
        logger.info("Memory: updated route %s", route)

    def increment_route_changes(self, route: str) -> None:
        """Increment the change count for a route (called on locator drift or test failure)."""
        if not self._enabled():
            return

        filepath = self.memory_dir / "APP_STRUCTURE.md"
        if not filepath.exists():
            return

        content = filepath.read_text()
        section_header = f"## {route}"
        if section_header not in content:
            return

        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "**Changes:**" in line and self._in_route_section(lines, i, route):
                count_match = re.search(r"\d+", line)
                if count_match:
                    new_count = int(count_match.group()) + 1
                    lines[i] = f"- **Changes:** {new_count}"

                    # Recalculate frequency
                    first_seen = self._find_field_in_section(lines, i, "First seen")
                    if first_seen:
                        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        weeks = max(1, (datetime.strptime(now, "%Y-%m-%d") - datetime.strptime(first_seen, "%Y-%m-%d")).days / 7)
                        freq = round(new_count / weeks, 1)
                        for j, l2 in enumerate(lines):
                            if "**Change frequency:**" in l2 and self._in_route_section(lines, j, route):
                                lines[j] = f"- **Change frequency:** {freq}/week"
                                break
                break

        filepath.write_text("\n".join(lines))

    def get_route_info(self, route: str) -> dict[str, Any] | None:
        """Read info for a specific route from APP_STRUCTURE.md."""
        if not self._enabled():
            return None

        filepath = self.memory_dir / "APP_STRUCTURE.md"
        if not filepath.exists():
            return None

        content = filepath.read_text()
        section_header = f"## {route}"
        if section_header not in content:
            return None

        idx = content.index(section_header)
        next_section = content.find("\n## ", idx + len(section_header))
        section = content[idx:next_section] if next_section != -1 else content[idx:]

        return self._parse_route_section(route, section)

    def get_volatile_routes(self, threshold: float = 1.0) -> list[dict[str, Any]]:
        """Return routes with change frequency above the threshold."""
        if not self._enabled():
            return []

        filepath = self.memory_dir / "APP_STRUCTURE.md"
        if not filepath.exists():
            return []

        content = filepath.read_text()
        routes = []

        for match in re.finditer(r"## (/\S*)", content):
            route = match.group(1)
            info = self.get_route_info(route)
            if info and info.get("change_frequency", 0) >= threshold:
                routes.append(info)

        return sorted(routes, key=lambda r: r.get("change_frequency", 0), reverse=True)

    def get_all_routes(self) -> list[dict[str, Any]]:
        """Return all known routes."""
        if not self._enabled():
            return []

        filepath = self.memory_dir / "APP_STRUCTURE.md"
        if not filepath.exists():
            return []

        content = filepath.read_text()
        routes = []
        for match in re.finditer(r"## (/\S*)", content):
            route = match.group(1)
            info = self.get_route_info(route)
            if info:
                routes.append(info)
        return routes

    @staticmethod
    def _parse_route_section(route: str, section: str) -> dict[str, Any]:
        """Parse a route section into a dict."""
        info: dict[str, Any] = {"route": route}
        for line in section.split("\n"):
            if "**First seen:**" in line:
                info["first_seen"] = line.split(":**")[1].strip().rstrip("*").strip()
            elif "**Last seen:**" in line:
                info["last_seen"] = line.split(":**")[1].strip().rstrip("*").strip()
            elif "**Changes:**" in line:
                m = re.search(r"\d+", line)
                info["changes"] = int(m.group()) if m else 0
            elif "**Change frequency:**" in line:
                m = re.search(r"[\d.]+", line)
                info["change_frequency"] = float(m.group()) if m else 0.0
            elif "**Known testids:**" in line:
                raw = line.split(":**")[1].strip().rstrip("*").strip()
                info["testids"] = [t.strip() for t in raw.split(",")] if raw != "none discovered" else []
            elif "**Components:**" in line:
                raw = line.split(":**")[1].strip().rstrip("*").strip()
                info["components"] = [c.strip() for c in raw.split(",")] if raw != "none discovered" else []
        return info

    @staticmethod
    def _extract_change_count(section: str) -> int:
        m = re.search(r"\*\*Changes:\*\*\s*(\d+)", section)
        return int(m.group(1)) if m else 0

    @staticmethod
    def _extract_first_seen(section: str) -> str | None:
        m = re.search(r"\*\*First seen:\*\*\s*([\d-]+)", section)
        return m.group(1) if m else None

    @staticmethod
    def _in_route_section(lines: list[str], line_idx: int, route: str) -> bool:
        """Check if line_idx is within the section for the given route."""
        for i in range(line_idx, -1, -1):
            if lines[i].strip().startswith("## "):
                return route in lines[i]
        return False

    @staticmethod
    def _find_field_in_section(lines: list[str], line_idx: int, field: str) -> str | None:
        """Find a field value in the same route section as line_idx."""
        for i in range(line_idx, -1, -1):
            if lines[i].strip().startswith("## "):
                break
            if f"**{field}:**" in lines[i]:
                m = re.search(r":\*\*\s*([\d-]+)", lines[i])
                return m.group(1) if m else None
        return None

    # -------------------------------------------------------------------
    # Test Stability
    # -------------------------------------------------------------------

    def record_test_result(
        self,
        test_id: str,
        route: str,
        passed: bool,
        failure_class: str | None = None,
    ) -> None:
        """Record a test result in TEST_STABILITY.md, updating existing rows in place."""
        if not self._enabled("planner"):
            return

        filepath = self.memory_dir / "TEST_STABILITY.md"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if not filepath.exists():
            filepath.write_text(
                "# Test Stability\n\n"
                "| Test ID | Route | Runs | Passes | Fails | Flakiness | Last run | Last failure |\n"
                "|---------|-------|------|--------|-------|-----------|----------|-------------|\n"
            )

        content = filepath.read_text()

        # Check if test_id already exists
        if f"| {test_id} |" in content:
            # Update existing row
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith(f"| {test_id} |"):
                    row = self._parse_stability_row(line)
                    row["runs"] += 1
                    if passed:
                        row["passes"] += 1
                    else:
                        row["fails"] += 1
                        row["last_failure"] = failure_class or "unknown"
                    row["flakiness"] = round(row["fails"] / row["runs"], 2) if row["runs"] > 0 else 0.0
                    row["last_run"] = now
                    lines[i] = self._format_stability_row(row)
                    break
            filepath.write_text("\n".join(lines))
        else:
            # Append new row
            runs = 1
            passes = 1 if passed else 0
            fails = 0 if passed else 1
            flakiness = 0.0 if passed else 1.0
            last_failure = "—" if passed else (failure_class or "unknown")
            row = f"| {test_id} | {route} | {runs} | {passes} | {fails} | {flakiness:.2f} | {now} | {last_failure} |\n"
            with open(filepath, "a") as f:
                f.write(row)

        logger.debug("Memory: recorded test result for %s (passed=%s)", test_id, passed)

    def get_flaky_tests(self, threshold: float = 0.2) -> list[dict[str, Any]]:
        """Return tests with flakiness score above the threshold."""
        if not self._enabled("planner"):
            return []

        filepath = self.memory_dir / "TEST_STABILITY.md"
        if not filepath.exists():
            return []

        content = filepath.read_text()
        flaky = []

        for line in content.split("\n"):
            if line.startswith("| ") and not line.startswith("| Test ID") and not line.startswith("|---"):
                row = self._parse_stability_row(line)
                if row and row.get("flakiness", 0) >= threshold:
                    flaky.append(row)

        return sorted(flaky, key=lambda r: r.get("flakiness", 0), reverse=True)

    def get_test_history(self, test_id: str) -> dict[str, Any] | None:
        """Get stability data for a specific test."""
        if not self._enabled("planner"):
            return None

        filepath = self.memory_dir / "TEST_STABILITY.md"
        if not filepath.exists():
            return None

        content = filepath.read_text()
        for line in content.split("\n"):
            if line.startswith(f"| {test_id} |"):
                return self._parse_stability_row(line)
        return None

    @staticmethod
    def _parse_stability_row(line: str) -> dict[str, Any]:
        """Parse a TEST_STABILITY.md table row into a dict."""
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 2:
            parts = parts[1:-1]
        if len(parts) < 8:
            return {}
        try:
            return {
                "test_id": parts[0],
                "route": parts[1],
                "runs": int(parts[2]),
                "passes": int(parts[3]),
                "fails": int(parts[4]),
                "flakiness": float(parts[5]),
                "last_run": parts[6],
                "last_failure": parts[7],
            }
        except (ValueError, IndexError):
            return {}

    @staticmethod
    def _format_stability_row(row: dict[str, Any]) -> str:
        """Format a stability dict back into a markdown table row."""
        return (
            f"| {row['test_id']} | {row['route']} | {row['runs']} | {row['passes']} "
            f"| {row['fails']} | {row['flakiness']:.2f} | {row['last_run']} | {row['last_failure']} |"
        )

    # -------------------------------------------------------------------
    # Prompt context builders
    # -------------------------------------------------------------------

    def build_planner_memory_context(self, max_tokens: int = 500) -> str:
        """Build memory context for the Planner: volatile routes + flaky tests."""
        if not self._enabled("planner"):
            return ""

        parts = []

        volatile = self.get_volatile_routes(threshold=1.0)
        if volatile:
            parts.append("## Memory: Volatile Routes (change >1x/week)")
            for r in volatile[:5]:
                parts.append(f"- **{r['route']}** — {r.get('change_frequency', 0)}/week, {r.get('changes', 0)} changes")
            parts.append("Prioritize these routes with @smoke tags.\n")

        flaky = self.get_flaky_tests(threshold=0.2)
        if flaky:
            parts.append("## Memory: Flaky Tests (>20% failure rate)")
            for t in flaky[:5]:
                parts.append(f"- **{t['test_id']}** ({t['route']}) — {t['flakiness']:.0%} flaky, last failure: {t['last_failure']}")
            parts.append("Flag these tests in the plan.\n")

        if not parts:
            return ""

        result = "\n".join(parts)
        char_limit = max_tokens * 4
        if len(result) > char_limit:
            result = result[:char_limit].rsplit("\n", 1)[0]
        return result

    def build_generator_memory_context(self, route: str, max_tokens: int = 500) -> str:
        """Build memory context for the Generator: known testids + locator history for a route."""
        if not self._enabled("generator"):
            return ""

        parts = []

        route_info = self.get_route_info(route)
        if route_info:
            testids = route_info.get("testids", [])
            if testids:
                parts.append(f"## Memory: Known testids for {route}")
                parts.append(f"Previously discovered: {', '.join(testids)}")
                parts.append("Prefer these testids when generating locators.\n")

        history = self.get_locator_history(route)
        if history:
            drifted_locators = [e for e in history if e["success"]]
            if drifted_locators:
                parts.append(f"## Memory: Locator drift history for {route}")
                parts.append("These locators have drifted before — avoid using the old form:")
                for e in drifted_locators[-5:]:
                    parts.append(f"- `{e['old_locator']}` drifted → prefer `{e['new_locator']}`")
                parts.append("")

        if not parts:
            return ""

        result = "\n".join(parts)
        char_limit = max_tokens * 4
        if len(result) > char_limit:
            result = result[:char_limit].rsplit("\n", 1)[0]
        return result

    # -------------------------------------------------------------------
    # Legacy prompt context (Healer — from M1)
    # -------------------------------------------------------------------

    def build_healer_memory_context(self, route: str, element: str | None = None, max_tokens: int = 500) -> str:
        """Build a memory context string for injection into the Healer prompt.

        Returns a formatted section capped at approximately max_tokens.
        """
        if not self._enabled("healer"):
            return ""

        history = self.get_locator_history(route, element)
        if not history:
            return ""

        lines = [f"## Memory: Locator History for {route}"]
        if element:
            lines[0] += f" → {element}"

        lines.append(f"This element has changed {len(history)} time(s):")

        for entry in history[-10:]:  # last 10 entries max
            success_mark = "" if entry["success"] else " [FAILED]"
            lines.append(
                f"  {entry['date']}: `{entry['old_locator']}` → `{entry['new_locator']}`{success_mark}"
            )

        # Check for patterns
        successful = [e for e in history if e["success"]]
        if successful:
            last = successful[-1]
            if "getByTestId" in last["new_locator"]:
                lines.append("\nPattern: testid locators have been stable. Prefer getByTestId.")
            elif "getByRole" in last["new_locator"]:
                lines.append("\nPattern: role-based locators used. Check if testid is available.")

        result = "\n".join(lines)

        # Rough token cap (1 token ≈ 4 chars)
        char_limit = max_tokens * 4
        if len(result) > char_limit:
            result = result[:char_limit].rsplit("\n", 1)[0]

        return result


    # -------------------------------------------------------------------
    # Maintenance
    # -------------------------------------------------------------------

    def prune_stale(self, max_age_days: int = 90) -> int:
        """Remove memory entries older than max_age_days. Returns count pruned."""
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
        total_pruned = 0

        # 1. Prune locator history files
        for filepath in self.locators_dir.glob("*.md"):
            if filepath.name == ".gitkeep":
                continue
            content = filepath.read_text()
            lines = content.split("\n")
            new_lines = []
            pruned = 0
            for line in lines:
                date_match = re.match(r"- (\d{4}-\d{2}-\d{2}):", line.strip())
                if date_match and date_match.group(1) < cutoff:
                    pruned += 1
                    continue
                new_lines.append(line)
            if pruned:
                filepath.write_text("\n".join(new_lines))
                total_pruned += pruned

        # 2. Prune failure patterns
        filepath = self.memory_dir / "FAILURES.md"
        if filepath.exists():
            content = filepath.read_text()
            sections = re.split(r"(?=\n## FP-)", content)
            kept = [sections[0]]  # header
            for section in sections[1:]:
                stale_match = re.search(r"\*\*Stale after:\*\*\s*([\d-]+)", section)
                if stale_match and stale_match.group(1) < cutoff:
                    total_pruned += 1
                    continue
                # Also prune by last_seen
                seen_match = re.search(r"\*\*Last seen:\*\*\s*([\d-]+)", section)
                if seen_match and seen_match.group(1) < cutoff:
                    total_pruned += 1
                    continue
                kept.append(section)
            filepath.write_text("".join(kept))

        # 3. Prune human decisions
        filepath = self.memory_dir / "HUMAN_DECISIONS.md"
        if filepath.exists():
            content = filepath.read_text()
            lines = content.split("\n")
            new_lines = []
            for line in lines:
                # Data rows start with "| 2026-..."
                date_match = re.match(r"\| (\d{4}-\d{2}-\d{2}) \|", line.strip())
                if date_match and date_match.group(1) < cutoff:
                    total_pruned += 1
                    continue
                new_lines.append(line)
            filepath.write_text("\n".join(new_lines))

        if total_pruned:
            logger.info("Memory: pruned %d stale entries (older than %d days)", total_pruned, max_age_days)

        return total_pruned

    def dedup_failure_patterns(self) -> int:
        """Merge duplicate failure patterns (same normalized signature). Returns count merged."""
        filepath = self.memory_dir / "FAILURES.md"
        if not filepath.exists():
            return 0

        patterns = self._parse_failure_patterns(filepath.read_text())
        if not patterns:
            return 0

        # Group by normalized signature
        seen: dict[str, dict[str, Any]] = {}
        merged = 0

        for p in patterns:
            sig = p.get("signature", "")
            if sig in seen:
                # Merge: sum occurrences, keep latest date
                seen[sig]["occurrences"] = seen[sig].get("occurrences", 1) + p.get("occurrences", 1)
                if p.get("last_seen", "") > seen[sig].get("last_seen", ""):
                    seen[sig]["last_seen"] = p["last_seen"]
                merged += 1
            else:
                seen[sig] = p

        if merged == 0:
            return 0

        # Rewrite the file
        content = "# Failure Patterns\n"
        for i, (sig, p) in enumerate(seen.items(), 1):
            stale_date = _add_days(p.get("last_seen", "2026-01-01"), 90)
            content += (
                f"\n## FP-{i:03d}: {sig[:80]}\n"
                f"- **Signature:** `{sig}`\n"
                f"- **Class:** {p.get('failure_class', 'unknown')}\n"
                f"- **Resolution:** {p.get('resolution', 'unknown')}\n"
                f"- **Routes:** {p.get('routes', 'unknown')}\n"
                f"- **Occurrences:** {p.get('occurrences', 1)}\n"
                f"- **Last seen:** {p.get('last_seen', 'unknown')}\n"
                f"- **Stale after:** {stale_date}\n"
            )
        filepath.write_text(content)
        logger.info("Memory: merged %d duplicate failure patterns", merged)
        return merged

    def stats(self) -> dict[str, Any]:
        """Return memory statistics: entry counts per file, total size, oldest/newest."""
        result: dict[str, Any] = {"files": {}, "total_entries": 0, "total_size_bytes": 0}

        # Locator files
        locator_entries = 0
        for filepath in self.locators_dir.glob("*.md"):
            if filepath.name == ".gitkeep":
                continue
            content = filepath.read_text()
            count = content.count("\n- ")
            locator_entries += count
            result["total_size_bytes"] += filepath.stat().st_size
        result["files"]["locators"] = locator_entries

        # Failures
        filepath = self.memory_dir / "FAILURES.md"
        if filepath.exists():
            content = filepath.read_text()
            count = len(re.findall(r"## FP-", content))
            result["files"]["failures"] = count
            result["total_size_bytes"] += filepath.stat().st_size
        else:
            result["files"]["failures"] = 0

        # Human decisions
        filepath = self.memory_dir / "HUMAN_DECISIONS.md"
        if filepath.exists():
            content = filepath.read_text()
            count = len([l for l in content.split("\n") if re.match(r"\| \d{4}-", l.strip())])
            result["files"]["human_decisions"] = count
            result["total_size_bytes"] += filepath.stat().st_size
        else:
            result["files"]["human_decisions"] = 0

        # App structure
        filepath = self.memory_dir / "APP_STRUCTURE.md"
        if filepath.exists():
            content = filepath.read_text()
            count = len(re.findall(r"## /", content))
            result["files"]["app_routes"] = count
            result["total_size_bytes"] += filepath.stat().st_size
        else:
            result["files"]["app_routes"] = 0

        # Test stability
        filepath = self.memory_dir / "TEST_STABILITY.md"
        if filepath.exists():
            content = filepath.read_text()
            count = len([l for l in content.split("\n") if re.match(r"\| \S+.*\|.*\|.*\|", l.strip()) and not l.strip().startswith("| Test ID") and not l.strip().startswith("|---")])
            result["files"]["test_stability"] = count
            result["total_size_bytes"] += filepath.stat().st_size
        else:
            result["files"]["test_stability"] = 0

        result["total_entries"] = sum(result["files"].values())
        result["total_size_kb"] = round(result["total_size_bytes"] / 1024, 1)

        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_days(date_str: str, days: int) -> str:
    """Add days to a YYYY-MM-DD date string."""
    from datetime import timedelta
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return (dt + timedelta(days=days)).strftime("%Y-%m-%d")
