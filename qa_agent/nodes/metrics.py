"""Metrics — markdown-backed run history, Triage audit, and escape tracking.

Stores every run + Triage call to git-tracked markdown files. Computes:
  - Escape rate: bugs that slipped past a green run
  - Triage precision: was the classification correct?
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from qa_agent.state import QAState

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / "memory"


class MetricsDB:
    """Markdown-backed metrics store for run history and Triage audit.

    Drop-in replacement for the former SQLite MetricsDB — same API,
    markdown storage instead of database.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        # db_path is now treated as the memory directory for backward compat
        if db_path and Path(db_path).suffix == ".db":
            # Old-style path — use parent directory / "memory" or default
            self.memory_dir = Path(db_path).parent
        else:
            self.memory_dir = Path(db_path) if db_path else _DEFAULT_MEMORY_DIR
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._init_files()

    def _init_files(self) -> None:
        """Create markdown files if they don't exist."""
        runs = self.memory_dir / "RUN_HISTORY.md"
        if not runs.exists():
            runs.write_text(
                "# Run History\n\n"
                "| ID | Timestamp | Goal | Route | Passed | Failed cases | Failure class | Confidence | Attempts | Fingerprint | Outcome |\n"
                "|----|-----------|------|-------|--------|-------------|---------------|------------|----------|-------------|--------|\n"
            )

        triage = self.memory_dir / "TRIAGE_CALLS.md"
        if not triage.exists():
            triage.write_text(
                "# Triage Calls\n\n"
                "| ID | Timestamp | Run ID | Failure class | Confidence | Human override | Was correct |\n"
                "|----|-----------|--------|---------------|------------|----------------|-------------|\n"
            )

        escapes = self.memory_dir / "ESCAPES.md"
        if not escapes.exists():
            escapes.write_text(
                "# Escapes\n\n"
                "| ID | Timestamp | Run ID | Bug ticket | Route |\n"
                "|----|-----------|--------|------------|-------|\n"
            )

    def _append_row_with_id(self, filepath: Path, row_template: str) -> int:
        """Atomically compute next ID and append row under lock. Returns the ID.

        row_template should contain '{id}' which will be replaced with the actual ID.
        """
        try:
            import fcntl
            with open(filepath, "r+") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                content = f.read()
                ids = re.findall(r"^\| (\d+) \|", content, re.M)
                next_id = max((int(i) for i in ids), default=0) + 1
                row = row_template.replace("{id}", str(next_id))
                f.write(row)
                f.flush()
            return next_id
        except ImportError:
            content = filepath.read_text() if filepath.exists() else ""
            ids = re.findall(r"^\| (\d+) \|", content, re.M)
            next_id = max((int(i) for i in ids), default=0) + 1
            row = row_template.replace("{id}", str(next_id))
            with open(filepath, "a") as f:
                f.write(row)
            return next_id

    def record_run(
        self,
        goal: str,
        route: str,
        passed: bool,
        failed_cases: list[str],
        failure_class: Optional[str],
        confidence: float,
        attempts: int,
        fingerprint: Optional[str],
        outcome: str,
    ) -> int:
        """Record a completed run. Returns the run ID."""
        filepath = self.memory_dir / "RUN_HISTORY.md"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        passed_str = "yes" if passed else "no"
        failed_str = ", ".join(failed_cases).replace("|", "/") if failed_cases else "—"
        goal_clean = goal[:50].replace("|", "/")

        row_template = (
            f"| {{id}} | {now} | {goal_clean} | {route} | {passed_str} "
            f"| {failed_str} | {failure_class or '—'} | {confidence:.2f} "
            f"| {attempts} | {fingerprint or '—'} | {outcome} |\n"
        )
        return self._append_row_with_id(filepath, row_template)

    def record_triage_call(
        self,
        run_id: int,
        failure_class: str,
        confidence: float,
        human_override: Optional[str] = None,
    ) -> int:
        """Record a Triage classification for later audit."""
        filepath = self.memory_dir / "TRIAGE_CALLS.md"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

        row_template = (
            f"| {{id}} | {now} | {run_id} | {failure_class} "
            f"| {confidence:.2f} | {human_override or '—'} | — |\n"
        )
        return self._append_row_with_id(filepath, row_template)

    def record_escape(self, run_id: int, bug_ticket: str, route: str) -> None:
        """Record a bug that escaped a green run."""
        filepath = self.memory_dir / "ESCAPES.md"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

        row_template = f"| {{id}} | {now} | {run_id} | {bug_ticket} | {route} |\n"
        self._append_row_with_id(filepath, row_template)

    def mark_triage_correctness(self, triage_id: int, was_correct: bool) -> None:
        """Mark whether a Triage call was correct (from human audit)."""
        filepath = self.memory_dir / "TRIAGE_CALLS.md"
        if not filepath.exists():
            return

        correct_str = "yes" if was_correct else "no"
        target = f"| {triage_id} |"

        try:
            import fcntl
            with open(filepath, "r+") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                content = f.read()
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith(target):
                        parts = line.rsplit("| — |", 1)
                        if len(parts) == 2:
                            lines[i] = parts[0] + f"| {correct_str} |"
                        break
                f.seek(0)
                f.write("\n".join(lines))
                f.truncate()
                f.flush()
        except ImportError:
            content = filepath.read_text()
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith(target):
                    parts = line.rsplit("| — |", 1)
                    if len(parts) == 2:
                        lines[i] = parts[0] + f"| {correct_str} |"
                    break
            filepath.write_text("\n".join(lines))

    def _parse_runs(self, since: str | None = None) -> list[dict[str, Any]]:
        """Parse all runs from RUN_HISTORY.md, optionally filtered by timestamp."""
        filepath = self.memory_dir / "RUN_HISTORY.md"
        if not filepath.exists():
            return []

        content = filepath.read_text()
        runs = []

        for line in content.split("\n"):
            if not re.match(r"^\| \d+ \|", line):
                continue
            parts = [p.strip() for p in line.split("|")][1:-1]
            if len(parts) < 11:
                continue
            try:
                timestamp = parts[1]
                if since and timestamp < since:
                    continue
                runs.append({
                    "id": int(parts[0]),
                    "timestamp": timestamp,
                    "goal": parts[2],
                    "route": parts[3],
                    "passed": parts[4] == "yes",
                    "failed_cases": parts[5],
                    "failure_class": parts[6] if parts[6] != "—" else None,
                    "confidence": float(parts[7]),
                    "attempts": int(parts[8]),
                    "fingerprint": parts[9] if parts[9] != "—" else None,
                    "outcome": parts[10],
                })
            except (ValueError, IndexError):
                continue

        return runs

    def _parse_triage_calls(self) -> list[dict[str, Any]]:
        """Parse all triage calls from TRIAGE_CALLS.md."""
        filepath = self.memory_dir / "TRIAGE_CALLS.md"
        if not filepath.exists():
            return []

        content = filepath.read_text()
        calls = []

        for line in content.split("\n"):
            if not re.match(r"^\| \d+ \|", line):
                continue
            parts = [p.strip() for p in line.split("|")][1:-1]
            if len(parts) < 7:
                continue
            try:
                was_correct_str = parts[6]
                was_correct = True if was_correct_str == "yes" else (False if was_correct_str == "no" else None)
                calls.append({
                    "id": int(parts[0]),
                    "timestamp": parts[1],
                    "run_id": int(parts[2]),
                    "failure_class": parts[3],
                    "confidence": float(parts[4]),
                    "human_override": parts[5] if parts[5] != "—" else None,
                    "was_correct": was_correct,
                })
            except (ValueError, IndexError):
                continue

        return calls

    def compute_escape_rate(self) -> dict[str, Any]:
        """Compute escape rate: green runs that later had a bug filed."""
        runs = self._parse_runs()
        total_green = sum(1 for r in runs if r["passed"])

        filepath = self.memory_dir / "ESCAPES.md"
        escapes = 0
        if filepath.exists():
            content = filepath.read_text()
            escapes = len(re.findall(r"^\| \d+ \|", content, re.M))

        rate = escapes / total_green if total_green > 0 else 0.0
        return {
            "total_green_runs": total_green,
            "escapes": escapes,
            "escape_rate": round(rate, 4),
        }

    def compute_triage_accuracy(self) -> dict[str, Any]:
        """Compute Triage accuracy from audited calls."""
        calls = self._parse_triage_calls()
        audited = [c for c in calls if c["was_correct"] is not None]
        correct = sum(1 for c in audited if c["was_correct"])
        total = len(audited)

        accuracy = correct / total if total > 0 else 0.0
        return {
            "total_audited": total,
            "correct": correct,
            "accuracy": round(accuracy, 4),
        }

    def get_dashboard(self) -> dict[str, Any]:
        """Return the full metrics dashboard."""
        return {
            "escape_rate": self.compute_escape_rate(),
            "triage_accuracy": self.compute_triage_accuracy(),
        }

    def get_recent_runs(self, n: int = 30) -> list[dict[str, Any]]:
        """Return the last N runs."""
        runs = self._parse_runs()
        return runs[-n:]

    def get_run_count(self, since: str | None = None) -> tuple[int, int]:
        """Return (total_runs, passed_runs) optionally filtered by timestamp."""
        runs = self._parse_runs(since=since)
        total = len(runs)
        passed = sum(1 for r in runs if r["passed"])
        return total, passed


# ---------------------------------------------------------------------------
# Graph node
# ---------------------------------------------------------------------------

async def metrics(state: QAState) -> dict:
    """Record the run outcome in the metrics store.

    Called on every graph completion (pass or fail).
    """
    db = MetricsDB()

    passed = state.run_results.passed if state.run_results else False
    failed_cases = state.run_results.failed_cases if state.run_results else []
    route = state.plan[0].route if state.plan else "/"

    # Determine outcome
    if passed:
        outcome = "pass"
    elif state.failure_class == "app_defect":
        outcome = "defect_filed"
    elif state.attempts > 0:
        outcome = "healed"
    else:
        outcome = "failed"

    run_id = db.record_run(
        goal=state.goal,
        route=route,
        passed=passed,
        failed_cases=failed_cases,
        failure_class=state.failure_class,
        confidence=state.confidence,
        attempts=state.attempts,
        fingerprint=None,
        outcome=outcome,
    )

    # Record Triage call if there was one
    if state.failure_class:
        db.record_triage_call(
            run_id=run_id,
            failure_class=state.failure_class,
            confidence=state.confidence,
        )

    logger.info("Metrics: recorded run #%d (outcome=%s)", run_id, outcome)
    return {}
