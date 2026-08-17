"""Metrics · Escape-rate Audit — persists runs and measures Triage accuracy.

Stores every run + Triage call to a SQLite DB. Computes:
  - Escape rate: bugs that slipped past a green run
  - Triage precision: was the classification correct?
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from qa_agent.state import QAState

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "metrics.db"


class MetricsDB:
    """SQLite-backed metrics store for run history and Triage audit."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path or _DEFAULT_DB_PATH)
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    route TEXT,
                    passed INTEGER NOT NULL,
                    failed_cases TEXT,
                    failure_class TEXT,
                    confidence REAL,
                    attempts INTEGER DEFAULT 0,
                    fingerprint TEXT,
                    outcome TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS triage_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    run_id INTEGER,
                    failure_class TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    human_override TEXT,
                    was_correct INTEGER,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );

                CREATE TABLE IF NOT EXISTS escapes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    run_id INTEGER NOT NULL,
                    bug_ticket TEXT NOT NULL,
                    route TEXT,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );
            """)

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
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO runs
                   (timestamp, goal, route, passed, failed_cases, failure_class,
                    confidence, attempts, fingerprint, outcome)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    now, goal, route, int(passed),
                    json.dumps(failed_cases), failure_class,
                    confidence, attempts, fingerprint, outcome,
                ),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def record_triage_call(
        self,
        run_id: int,
        failure_class: str,
        confidence: float,
        human_override: Optional[str] = None,
    ) -> int:
        """Record a Triage classification for later audit."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO triage_calls
                   (timestamp, run_id, failure_class, confidence, human_override)
                   VALUES (?, ?, ?, ?, ?)""",
                (now, run_id, failure_class, confidence, human_override),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def record_escape(self, run_id: int, bug_ticket: str, route: str) -> None:
        """Record a bug that escaped a green run."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO escapes (timestamp, run_id, bug_ticket, route) VALUES (?, ?, ?, ?)",
                (now, run_id, bug_ticket, route),
            )

    def mark_triage_correctness(self, triage_id: int, was_correct: bool) -> None:
        """Mark whether a Triage call was correct (from human audit)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE triage_calls SET was_correct = ? WHERE id = ?",
                (int(was_correct), triage_id),
            )

    def compute_escape_rate(self, window_days: int = 30) -> dict[str, Any]:
        """Compute escape rate: green runs that later had a bug filed.

        Returns {"total_green_runs": N, "escapes": M, "escape_rate": float}
        """
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE passed = 1"
            ).fetchone()[0]
            escapes = conn.execute(
                "SELECT COUNT(*) FROM escapes"
            ).fetchone()[0]

        rate = escapes / total if total > 0 else 0.0
        return {
            "total_green_runs": total,
            "escapes": escapes,
            "escape_rate": round(rate, 4),
        }

    def compute_triage_accuracy(self) -> dict[str, Any]:
        """Compute Triage accuracy from audited calls.

        Returns {"total_audited": N, "correct": M, "accuracy": float}
        """
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM triage_calls WHERE was_correct IS NOT NULL"
            ).fetchone()[0]
            correct = conn.execute(
                "SELECT COUNT(*) FROM triage_calls WHERE was_correct = 1"
            ).fetchone()[0]

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


# ---------------------------------------------------------------------------
# Graph node
# ---------------------------------------------------------------------------

async def metrics(state: QAState) -> dict:
    """Record the run outcome in the metrics DB.

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
