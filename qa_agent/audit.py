"""Per-agent audit trail — automatic logging of inputs, outputs, timing, and errors.

Phase AT1: Core decorator + dual-format logging (markdown + JSON).
No token tracking yet (Phase AT2).

Usage in graph.py:
    from qa_agent.audit import audit_node
    graph.add_node("triage", audit_node("triage")(triage))
"""

from __future__ import annotations

import functools
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
_AUDIT_TRAIL_PATH = _MEMORY_DIR / "AUDIT_TRAIL.md"
_AUDIT_RUNS_DIR = _MEMORY_DIR / "audit_runs"

# Max chars for truncated fields in markdown summary
_SUMMARY_MAX = 200


class AuditStore:
    """Manages audit trail storage: markdown for humans, JSON for the Eval Agent."""

    # Class-level run state — shared across all decorated nodes in a single run
    _current_run_id: str | None = None
    _current_run_entries: list[dict[str, Any]] = []
    _run_start_time: float | None = None

    def __init__(self) -> None:
        _AUDIT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self._init_markdown()

    def _init_markdown(self) -> None:
        """Create AUDIT_TRAIL.md with header if it doesn't exist."""
        if not _AUDIT_TRAIL_PATH.exists():
            _AUDIT_TRAIL_PATH.write_text("# Audit Trail\n\n")

    @classmethod
    def start_run(cls, run_id: str) -> None:
        """Begin a new run — call once at the start of a graph invocation."""
        cls._current_run_id = run_id
        cls._current_run_entries = []
        cls._run_start_time = time.monotonic()
        logger.info("Audit: starting run %s", run_id)

    @classmethod
    def get_run_id(cls) -> str:
        """Get current run ID, generating one if needed."""
        if cls._current_run_id is None:
            cls._current_run_id = f"run-{int(time.time())}"
            cls._current_run_entries = []
            cls._run_start_time = time.monotonic()
        return cls._current_run_id

    @classmethod
    def end_run(cls) -> None:
        """Finalize the current run — write the complete JSON file."""
        if cls._current_run_id is None:
            return

        run_id = cls._current_run_id
        total_duration = (
            int((time.monotonic() - cls._run_start_time) * 1000)
            if cls._run_start_time
            else 0
        )

        run_data = {
            "run_id": run_id,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "total_duration_ms": total_duration,
            "total_input_tokens": None,  # Phase AT2
            "total_output_tokens": None,  # Phase AT2
            "estimated_cost_usd": None,  # Phase AT2
            "outcome": _derive_outcome(cls._current_run_entries),
            "nodes": cls._current_run_entries,
        }

        json_path = _AUDIT_RUNS_DIR / f"{run_id}.json"
        try:
            json_path.write_text(json.dumps(run_data, indent=2, default=str))
            logger.info("Audit: run %s written to %s", run_id, json_path.name)
        except Exception as e:
            logger.warning("Audit: failed to write JSON for run %s: %s", run_id, e)

        # Append run summary to markdown
        _append_run_summary_md(run_id, total_duration, cls._current_run_entries)

        # Reset
        cls._current_run_id = None
        cls._current_run_entries = []
        cls._run_start_time = None

    def record_node(self, entry: dict[str, Any]) -> None:
        """Record a single node execution entry."""
        AuditStore._current_run_entries.append(entry)

        # Also append to markdown immediately (so partial runs are visible)
        _append_node_entry_md(AuditStore.get_run_id(), entry)


def audit_node(node_name: str):
    """Decorator that wraps a graph node with audit trail logging.

    Captures timing, input state summary, output, and errors.
    Zero changes to node logic — transparent to LangGraph.

    Usage:
        graph.add_node("triage", audit_node("triage")(triage))
    """

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(state, **kwargs):
            store = AuditStore()
            run_id = AuditStore.get_run_id()
            timestamp = datetime.now(tz=timezone.utc).isoformat()
            start = time.monotonic()

            # Capture input summary
            input_summary = _summarize_state(state)

            try:
                result = await fn(state, **kwargs)
                elapsed_ms = int((time.monotonic() - start) * 1000)

                entry = {
                    "node": node_name,
                    "timestamp": timestamp,
                    "duration_ms": elapsed_ms,
                    "model": None,  # Phase AT2
                    "prompt_version": None,  # Phase AT3
                    "input_tokens": None,  # Phase AT2
                    "output_tokens": None,  # Phase AT2
                    "cost_usd": None,  # Phase AT2
                    "cache_hit": None,
                    "errors": [],
                    "input_state": input_summary,
                    "parsed_output": _safe_serialize(result),
                    "raw_prompt": None,  # Phase AT2
                    "raw_llm_response": None,  # Phase AT2
                    "memory_context": None,  # Phase AT3
                    "routing_decision": None,  # Phase AT3
                }

                store.record_node(entry)
                return result

            except Exception as exc:
                elapsed_ms = int((time.monotonic() - start) * 1000)

                entry = {
                    "node": node_name,
                    "timestamp": timestamp,
                    "duration_ms": elapsed_ms,
                    "model": None,
                    "prompt_version": None,
                    "input_tokens": None,
                    "output_tokens": None,
                    "cost_usd": None,
                    "cache_hit": None,
                    "errors": [str(exc)],
                    "input_state": input_summary,
                    "parsed_output": None,
                    "raw_prompt": None,
                    "raw_llm_response": None,
                    "memory_context": None,
                    "routing_decision": None,
                }

                store.record_node(entry)
                raise

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# State summarization
# ---------------------------------------------------------------------------

def _summarize_state(state: Any) -> dict[str, Any]:
    """Extract key fields from QAState into a serializable summary."""
    summary: dict[str, Any] = {}

    for field in ("goal", "failure_class", "confidence", "attempts", "app_url"):
        val = getattr(state, field, None)
        if val is not None and val != "" and val != 0:
            summary[field] = val

    # Truncate long fields
    error = getattr(state, "error", None)
    if error:
        summary["error"] = error[:500]

    # Plan summary
    plan = getattr(state, "plan", None)
    if plan:
        summary["plan_count"] = len(plan)
        if plan:
            summary["plan_first_route"] = getattr(plan[0], "route", None)

    # Run results summary
    run_results = getattr(state, "run_results", None)
    if run_results:
        summary["passed"] = run_results.passed
        if run_results.failed_cases:
            summary["failed_cases"] = run_results.failed_cases[:5]

    # Page objects / test code counts
    page_objects = getattr(state, "page_objects", None)
    if page_objects:
        summary["page_object_count"] = len(page_objects)

    test_code = getattr(state, "test_code", None)
    if test_code:
        summary["test_file_count"] = len(test_code)

    # ACs
    acs = getattr(state, "acceptance_criteria", None)
    if acs:
        summary["ac_count"] = len(acs)

    return summary


def _safe_serialize(obj: Any) -> Any:
    """Convert an object to a JSON-safe representation."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe_serialize(item) for item in obj]
    if isinstance(obj, (str, int, float, bool)):
        return obj
    # Pydantic models
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return str(obj)


def _truncate(text: str, max_len: int = _SUMMARY_MAX) -> str:
    """Truncate text for markdown summaries."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

def _append_node_entry_md(run_id: str, entry: dict[str, Any]) -> None:
    """Append a single node's audit entry to AUDIT_TRAIL.md."""
    node = entry["node"]
    duration = entry["duration_ms"]
    ts = entry["timestamp"][:19].replace("T", " ")
    errors = entry.get("errors", [])

    lines = [f"\n### {node} ({ts} — {duration}ms)\n"]

    # Input summary
    input_state = entry.get("input_state", {})
    if input_state:
        summary_parts = []
        for k, v in input_state.items():
            summary_parts.append(f"{k}={_truncate(str(v), 80)}")
        lines.append(f"- **Input:** {', '.join(summary_parts)}")

    # Output summary
    output = entry.get("parsed_output")
    if output:
        output_str = json.dumps(output, default=str)
        lines.append(f"- **Output:** {_truncate(output_str)}")

    # Errors
    if errors:
        for err in errors:
            lines.append(f"- **Error:** {_truncate(err)}")
    else:
        lines.append("- **Errors:** none")

    lines.append("")

    text = "\n".join(lines)

    try:
        _append_locked(_AUDIT_TRAIL_PATH, text)
    except Exception as e:
        logger.warning("Audit: failed to append markdown for %s: %s", node, e)


def _append_run_summary_md(
    run_id: str, total_duration_ms: int, entries: list[dict[str, Any]]
) -> None:
    """Append a run summary block to AUDIT_TRAIL.md."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    outcome = _derive_outcome(entries)
    node_names = [e["node"] for e in entries]
    error_count = sum(1 for e in entries if e.get("errors"))

    lines = [
        f"\n## Run {run_id} — {now}\n",
        f"- **Duration:** {total_duration_ms}ms",
        f"- **Nodes:** {', '.join(node_names)}",
        f"- **Outcome:** {outcome}",
        f"- **Errors:** {error_count}",
        "\n---\n",
    ]

    text = "\n".join(lines)

    try:
        _append_locked(_AUDIT_TRAIL_PATH, text)
    except Exception as e:
        logger.warning("Audit: failed to append run summary: %s", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_outcome(entries: list[dict[str, Any]]) -> str:
    """Derive the run outcome from node entries."""
    if not entries:
        return "unknown"

    # Check for errors
    if any(e.get("errors") for e in entries):
        return "error"

    # Check the last meaningful output
    for entry in reversed(entries):
        output = entry.get("parsed_output", {})
        if isinstance(output, dict):
            if output.get("failure_class"):
                fc = output["failure_class"]
                if fc == "locator_drift":
                    return "healed" if "healer" in [e["node"] for e in entries] else "drift"
                if fc == "app_defect":
                    return "defect"
                return fc
            if "passed" in str(output):
                return "passed"

    # If metrics was the last node and no failure_class, it passed
    if entries[-1]["node"] == "metrics":
        return "passed"

    return "completed"


def _append_locked(filepath: Path, text: str) -> None:
    """Append text to a file with fcntl locking (Unix) or plain append (Windows)."""
    try:
        import fcntl

        with open(filepath, "a") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(text)
            f.flush()
    except ImportError:
        with open(filepath, "a") as f:
            f.write(text)
