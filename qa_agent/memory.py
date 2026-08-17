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
        safe_name = route.strip("/").replace("/", "_") or "root"
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

        filepath = self.memory_dir / "failures.md"
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

        filepath = self.memory_dir / "failures.md"
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
        """Parse all failure patterns from the failures.md file."""
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
        """Record a Human Review verdict to human_decisions.md."""
        if not self._enabled("triage"):
            return

        filepath = self.memory_dir / "human_decisions.md"
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

        filepath = self.memory_dir / "human_decisions.md"
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
    # Prompt injection helpers
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_days(date_str: str, days: int) -> str:
    """Add days to a YYYY-MM-DD date string."""
    from datetime import timedelta
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return (dt + timedelta(days=days)).strftime("%Y-%m-%d")
