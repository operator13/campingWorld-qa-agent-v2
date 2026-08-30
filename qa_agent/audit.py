"""Per-agent audit trail — automatic logging of inputs, outputs, timing, tokens, and errors.

Phase AT1: Core decorator + dual-format logging (markdown + JSON).
Phase AT2: Token tracking + cost estimation.
Phase AT3: Prompt versioning + memory context + routing decisions.

Usage in graph.py:
    from qa_agent.audit import audit_node
    graph.add_node("triage", audit_node("triage")(triage))

Usage in nodes (after model.ainvoke):
    from qa_agent.audit import AuditStore
    AuditStore.record_llm_call(response, model=get_model("triage"))
    AuditStore.record_prompt_data(prompt=messages[-1].content, response=response.content)
    AuditStore.record_prompt_version(SYSTEM_PROMPT, "TRIAGE.md")
    AuditStore.record_memory_context(files_read=["FAILURES.md"], similar_failures=1)
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
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

    # Token tracking (Phase AT2) — accumulates LLM call data per node
    _current_node_llm_calls: list[dict[str, Any]] = []
    _run_total_input_tokens: int = 0
    _run_total_output_tokens: int = 0
    _run_total_cost: float = 0.0

    # Prompt/memory/routing context (Phase AT3)
    _current_prompt_version: str | None = None
    _current_memory_context: dict[str, Any] | None = None
    _current_prompt_data: dict[str, str | None] = {}
    _current_routing_decision: dict[str, str] | None = None
    _current_cache_hit: bool | None = None

    def __init__(self) -> None:
        _AUDIT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self._init_markdown()

    def _init_markdown(self) -> None:
        """Create AUDIT_TRAIL.md with header if it doesn't exist."""
        if not _AUDIT_TRAIL_PATH.exists():
            _AUDIT_TRAIL_PATH.write_text("# Audit Trail\n\n")

    @classmethod
    def record_prompt_version(cls, prompt_text: str, prompt_name: str) -> None:
        """Record the prompt version hash for the current node."""
        short_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:12]
        cls._current_prompt_version = f"{prompt_name}@sha256:{short_hash}"

    @classmethod
    def record_memory_context(
        cls,
        files_read: list[str] | None = None,
        similar_failures: int = 0,
        calibration_examples: int = 0,
        context_tokens: int = 0,
    ) -> None:
        """Record what memory was injected into the current node."""
        cls._current_memory_context = {
            "files_read": files_read or [],
            "similar_failures_found": similar_failures,
            "calibration_examples": calibration_examples,
            "context_tokens": context_tokens,
        }

    @classmethod
    def record_prompt_data(
        cls, raw_prompt: str | None = None, raw_response: str | None = None
    ) -> None:
        """Record raw prompt and response text for the current node.

        Per pre-mortem Risk 2: raw data only stored when AUDIT_RAW=true
        or the run ends in failure.
        """
        cls._current_prompt_data = {
            "raw_prompt": raw_prompt,
            "raw_response": raw_response,
        }

    @classmethod
    def record_routing_decision(cls, next_node: str, reason: str) -> None:
        """Record a routing decision (called from graph routers)."""
        cls._current_routing_decision = {
            "next_node": next_node,
            "reason": reason,
        }

    @classmethod
    def record_cache_hit(cls, hit: bool) -> None:
        """Record whether the current node used a cached result."""
        cls._current_cache_hit = hit

    @classmethod
    def _consume_at3_context(cls) -> dict[str, Any]:
        """Consume all AT3 staged data for the current node entry."""
        include_raw = os.getenv("AUDIT_RAW", "").lower() in ("true", "1", "yes")

        result = {
            "prompt_version": cls._current_prompt_version,
            "memory_context": cls._current_memory_context,
            "raw_prompt": cls._current_prompt_data.get("raw_prompt") if include_raw else None,
            "raw_llm_response": cls._current_prompt_data.get("raw_response") if include_raw else None,
            "routing_decision": cls._current_routing_decision,
            "cache_hit": cls._current_cache_hit,
        }

        # Reset for next node
        cls._current_prompt_version = None
        cls._current_memory_context = None
        cls._current_prompt_data = {}
        cls._current_routing_decision = None
        cls._current_cache_hit = None

        return result

    @classmethod
    def record_llm_call(cls, response: Any, model: str | None = None) -> None:
        """Called by nodes after model.ainvoke() to capture token data.

        Usage:
            response = await model.ainvoke(messages)
            AuditStore.record_llm_call(response, model=get_model("triage"))
        """
        usage = getattr(response, "usage_metadata", None) or {}
        meta = getattr(response, "response_metadata", None) or {}

        input_tokens = usage.get("input_tokens", 0) if isinstance(usage, dict) else 0
        output_tokens = usage.get("output_tokens", 0) if isinstance(usage, dict) else 0

        cls._current_node_llm_calls.append({
            "model": model or meta.get("model", None),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        })

    @classmethod
    def _consume_llm_calls(cls) -> dict[str, Any]:
        """Consume accumulated LLM calls for the current node and return token summary."""
        from qa_agent.config import estimate_cost

        calls = cls._current_node_llm_calls
        cls._current_node_llm_calls = []

        if not calls:
            return {"model": None, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

        total_in = sum(c["input_tokens"] for c in calls)
        total_out = sum(c["output_tokens"] for c in calls)
        model = calls[0]["model"]  # Use the model from the first call
        cost = estimate_cost(model or "claude-sonnet-4-6", total_in, total_out)

        # Accumulate run-level totals
        cls._run_total_input_tokens += total_in
        cls._run_total_output_tokens += total_out
        cls._run_total_cost += cost

        return {
            "model": model,
            "input_tokens": total_in,
            "output_tokens": total_out,
            "cost_usd": round(cost, 6),
        }

    @classmethod
    def start_run(cls, run_id: str) -> None:
        """Begin a new run — call once at the start of a graph invocation."""
        cls._current_run_id = run_id
        cls._current_run_entries = []
        cls._run_start_time = time.monotonic()
        cls._current_node_llm_calls = []
        cls._run_total_input_tokens = 0
        cls._run_total_output_tokens = 0
        cls._run_total_cost = 0.0
        cls._current_prompt_version = None
        cls._current_memory_context = None
        cls._current_prompt_data = {}
        cls._current_routing_decision = None
        cls._current_cache_hit = None
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
            "total_input_tokens": cls._run_total_input_tokens,
            "total_output_tokens": cls._run_total_output_tokens,
            "estimated_cost_usd": round(cls._run_total_cost, 6),
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

            # Clear any leftover LLM calls from a previous node
            AuditStore._current_node_llm_calls = []

            try:
                result = await fn(state, **kwargs)
                elapsed_ms = int((time.monotonic() - start) * 1000)

                # Consume token data and AT3 context recorded by the node
                token_data = AuditStore._consume_llm_calls()
                at3 = AuditStore._consume_at3_context()

                entry = {
                    "node": node_name,
                    "timestamp": timestamp,
                    "duration_ms": elapsed_ms,
                    "model": token_data["model"],
                    "prompt_version": at3["prompt_version"],
                    "input_tokens": token_data["input_tokens"],
                    "output_tokens": token_data["output_tokens"],
                    "cost_usd": token_data["cost_usd"],
                    "cache_hit": at3["cache_hit"],
                    "errors": [],
                    "input_state": input_summary,
                    "parsed_output": _safe_serialize(result),
                    "raw_prompt": at3["raw_prompt"],
                    "raw_llm_response": at3["raw_llm_response"],
                    "memory_context": at3["memory_context"],
                    "routing_decision": at3["routing_decision"],
                }

                store.record_node(entry)
                return result

            except Exception as exc:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                token_data = AuditStore._consume_llm_calls()
                at3 = AuditStore._consume_at3_context()

                entry = {
                    "node": node_name,
                    "timestamp": timestamp,
                    "duration_ms": elapsed_ms,
                    "model": token_data["model"],
                    "prompt_version": at3["prompt_version"],
                    "input_tokens": token_data["input_tokens"],
                    "output_tokens": token_data["output_tokens"],
                    "cost_usd": token_data["cost_usd"],
                    "cache_hit": at3["cache_hit"],
                    "errors": [str(exc)],
                    "input_state": input_summary,
                    "parsed_output": None,
                    "raw_prompt": at3["raw_prompt"],
                    "raw_llm_response": at3["raw_llm_response"],
                    "memory_context": at3["memory_context"],
                    "routing_decision": at3["routing_decision"],
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

    # Model and tokens
    model = entry.get("model")
    in_tok = entry.get("input_tokens", 0)
    out_tok = entry.get("output_tokens", 0)
    cost = entry.get("cost_usd", 0)
    if model and (in_tok or out_tok):
        lines.append(f"- **Model:** {model}")
        lines.append(f"- **Tokens:** {in_tok} in / {out_tok} out (${cost:.4f})")

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

    total_in = sum(e.get("input_tokens", 0) or 0 for e in entries)
    total_out = sum(e.get("output_tokens", 0) or 0 for e in entries)
    total_cost = sum(e.get("cost_usd", 0) or 0 for e in entries)

    lines = [
        f"\n## Run {run_id} — {now}\n",
        f"- **Duration:** {total_duration_ms}ms",
        f"- **Tokens:** {total_in} in / {total_out} out",
        f"- **Cost:** ${total_cost:.4f}",
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
                if fc == "test_flake":
                    return "flake_healed" if "healer" in [e["node"] for e in entries] else "flake"
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
