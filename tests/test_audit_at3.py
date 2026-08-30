"""Tests for Audit Trail Phase AT3 — Prompt Versioning, Memory Context, Routing."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from qa_agent.audit import AuditStore, audit_node


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FakeState:
    goal = "test goal"
    failure_class = None
    confidence = 0
    attempts = 0
    app_url = None
    error = None
    plan = []
    run_results = None
    page_objects = {}
    test_code = {}
    acceptance_criteria = []


@pytest.fixture(autouse=True)
def reset_audit_state():
    AuditStore._current_run_id = None
    AuditStore._current_run_entries = []
    AuditStore._run_start_time = None
    AuditStore._current_node_llm_calls = []
    AuditStore._run_total_input_tokens = 0
    AuditStore._run_total_output_tokens = 0
    AuditStore._run_total_cost = 0.0
    AuditStore._current_prompt_version = None
    AuditStore._current_memory_context = None
    AuditStore._current_prompt_data = {}
    AuditStore._current_routing_decision = None
    AuditStore._current_cache_hit = None
    yield
    AuditStore._current_run_id = None
    AuditStore._current_run_entries = []
    AuditStore._current_node_llm_calls = []
    # Clean up env var
    os.environ.pop("AUDIT_RAW", None)


# ---------------------------------------------------------------------------
# Prompt versioning tests
# ---------------------------------------------------------------------------

class TestPromptVersioning:

    def test_hash_produces_consistent_version(self):
        AuditStore.record_prompt_version("Hello world", "TEST.md")
        assert AuditStore._current_prompt_version is not None
        assert AuditStore._current_prompt_version.startswith("TEST.md@sha256:")
        assert len(AuditStore._current_prompt_version) > len("TEST.md@sha256:")

    def test_same_text_same_hash(self):
        AuditStore.record_prompt_version("Same text", "A.md")
        v1 = AuditStore._current_prompt_version
        AuditStore.record_prompt_version("Same text", "A.md")
        v2 = AuditStore._current_prompt_version
        assert v1 == v2

    def test_different_text_different_hash(self):
        AuditStore.record_prompt_version("Version 1", "PROMPT.md")
        v1 = AuditStore._current_prompt_version
        AuditStore.record_prompt_version("Version 2", "PROMPT.md")
        v2 = AuditStore._current_prompt_version
        assert v1 != v2

    def test_prompt_name_in_version_string(self):
        AuditStore.record_prompt_version("text", "TRIAGE.md")
        assert "TRIAGE.md" in AuditStore._current_prompt_version


# ---------------------------------------------------------------------------
# Memory context tests
# ---------------------------------------------------------------------------

class TestMemoryContext:

    def test_records_files_read(self):
        AuditStore.record_memory_context(
            files_read=["FAILURES.md", "HUMAN_DECISIONS.md"],
            similar_failures=1,
            calibration_examples=3,
        )
        ctx = AuditStore._current_memory_context
        assert ctx["files_read"] == ["FAILURES.md", "HUMAN_DECISIONS.md"]
        assert ctx["similar_failures_found"] == 1
        assert ctx["calibration_examples"] == 3

    def test_defaults_to_empty(self):
        AuditStore.record_memory_context()
        ctx = AuditStore._current_memory_context
        assert ctx["files_read"] == []
        assert ctx["similar_failures_found"] == 0

    def test_context_tokens_tracked(self):
        AuditStore.record_memory_context(context_tokens=412)
        assert AuditStore._current_memory_context["context_tokens"] == 412


# ---------------------------------------------------------------------------
# Prompt data (raw prompt/response) tests
# ---------------------------------------------------------------------------

class TestPromptData:

    def test_records_raw_data(self):
        AuditStore.record_prompt_data(
            raw_prompt="What is 2+2?",
            raw_response="4",
        )
        assert AuditStore._current_prompt_data["raw_prompt"] == "What is 2+2?"
        assert AuditStore._current_prompt_data["raw_response"] == "4"

    def test_raw_data_excluded_by_default(self):
        """Raw data should NOT appear in consumed output unless AUDIT_RAW is set."""
        AuditStore.record_prompt_data(raw_prompt="secret", raw_response="answer")
        result = AuditStore._consume_at3_context()
        assert result["raw_prompt"] is None
        assert result["raw_llm_response"] is None

    def test_raw_data_included_with_env_var(self):
        os.environ["AUDIT_RAW"] = "true"
        AuditStore.record_prompt_data(raw_prompt="secret", raw_response="answer")
        result = AuditStore._consume_at3_context()
        assert result["raw_prompt"] == "secret"
        assert result["raw_llm_response"] == "answer"

    def test_raw_data_with_env_var_yes(self):
        os.environ["AUDIT_RAW"] = "yes"
        AuditStore.record_prompt_data(raw_prompt="p", raw_response="r")
        result = AuditStore._consume_at3_context()
        assert result["raw_prompt"] == "p"

    def test_raw_data_with_env_var_false(self):
        os.environ["AUDIT_RAW"] = "false"
        AuditStore.record_prompt_data(raw_prompt="p", raw_response="r")
        result = AuditStore._consume_at3_context()
        assert result["raw_prompt"] is None


# ---------------------------------------------------------------------------
# Routing decision tests
# ---------------------------------------------------------------------------

class TestRoutingDecision:

    def test_records_routing_decision(self):
        AuditStore.record_routing_decision("healer", "confidence 0.82 >= 0.75")
        assert AuditStore._current_routing_decision == {
            "next_node": "healer",
            "reason": "confidence 0.82 >= 0.75",
        }

    def test_routing_decision_in_consumed_output(self):
        AuditStore.record_routing_decision("metrics", "passed")
        result = AuditStore._consume_at3_context()
        assert result["routing_decision"]["next_node"] == "metrics"


# ---------------------------------------------------------------------------
# Cache hit tests
# ---------------------------------------------------------------------------

class TestCacheHit:

    def test_records_cache_hit_true(self):
        AuditStore.record_cache_hit(True)
        assert AuditStore._current_cache_hit is True

    def test_records_cache_hit_false(self):
        AuditStore.record_cache_hit(False)
        assert AuditStore._current_cache_hit is False

    def test_cache_hit_in_consumed_output(self):
        AuditStore.record_cache_hit(True)
        result = AuditStore._consume_at3_context()
        assert result["cache_hit"] is True


# ---------------------------------------------------------------------------
# _consume_at3_context tests
# ---------------------------------------------------------------------------

class TestConsumeAt3Context:

    def test_consumes_and_resets(self):
        AuditStore.record_prompt_version("text", "P.md")
        AuditStore.record_memory_context(files_read=["F.md"])
        AuditStore.record_routing_decision("healer", "drift")
        AuditStore.record_cache_hit(False)

        result = AuditStore._consume_at3_context()

        assert result["prompt_version"].startswith("P.md@sha256:")
        assert result["memory_context"]["files_read"] == ["F.md"]
        assert result["routing_decision"]["next_node"] == "healer"
        assert result["cache_hit"] is False

        # Verify reset
        assert AuditStore._current_prompt_version is None
        assert AuditStore._current_memory_context is None
        assert AuditStore._current_routing_decision is None
        assert AuditStore._current_cache_hit is None

    def test_all_none_when_nothing_recorded(self):
        result = AuditStore._consume_at3_context()
        assert result["prompt_version"] is None
        assert result["memory_context"] is None
        assert result["routing_decision"] is None
        assert result["cache_hit"] is None


# ---------------------------------------------------------------------------
# Decorator integration with AT3
# ---------------------------------------------------------------------------

class TestAuditNodeWithAT3:

    @pytest.mark.asyncio
    async def test_decorator_captures_prompt_version(self):
        AuditStore.start_run("test-at3-pv")

        @audit_node("test_node")
        async def node_with_prompt(state):
            AuditStore.record_prompt_version("my prompt text", "MY_PROMPT.md")
            return {"result": "ok"}

        await node_with_prompt(FakeState())

        entry = AuditStore._current_run_entries[0]
        assert entry["prompt_version"] is not None
        assert "MY_PROMPT.md" in entry["prompt_version"]

    @pytest.mark.asyncio
    async def test_decorator_captures_memory_context(self):
        AuditStore.start_run("test-at3-mc")

        @audit_node("test_node")
        async def node_with_memory(state):
            AuditStore.record_memory_context(
                files_read=["FAILURES.md"],
                similar_failures=2,
            )
            return {}

        await node_with_memory(FakeState())

        entry = AuditStore._current_run_entries[0]
        assert entry["memory_context"]["files_read"] == ["FAILURES.md"]
        assert entry["memory_context"]["similar_failures_found"] == 2

    @pytest.mark.asyncio
    async def test_decorator_captures_routing_decision(self):
        AuditStore.start_run("test-at3-rd")

        @audit_node("test_node")
        async def node_with_routing(state):
            AuditStore.record_routing_decision("triage", "failed")
            return {}

        await node_with_routing(FakeState())

        entry = AuditStore._current_run_entries[0]
        assert entry["routing_decision"]["next_node"] == "triage"

    @pytest.mark.asyncio
    async def test_decorator_captures_cache_hit(self):
        AuditStore.start_run("test-at3-ch")

        @audit_node("test_node")
        async def cached_node(state):
            AuditStore.record_cache_hit(True)
            return {}

        await cached_node(FakeState())

        entry = AuditStore._current_run_entries[0]
        assert entry["cache_hit"] is True

    @pytest.mark.asyncio
    async def test_non_llm_node_has_null_at3_fields(self):
        AuditStore.start_run("test-at3-null")

        @audit_node("executor")
        async def plain_node(state):
            return {"passed": True}

        await plain_node(FakeState())

        entry = AuditStore._current_run_entries[0]
        assert entry["prompt_version"] is None
        assert entry["memory_context"] is None
        assert entry["routing_decision"] is None
        assert entry["cache_hit"] is None

    @pytest.mark.asyncio
    async def test_full_at3_entry_in_json(self):
        """End-to-end: all AT3 fields populated and written to JSON."""
        AuditStore.start_run("test-at3-e2e")

        @audit_node("triage")
        async def full_node(state):
            AuditStore.record_prompt_version("system prompt", "TRIAGE.md")
            AuditStore.record_memory_context(
                files_read=["FAILURES.md", "HUMAN_DECISIONS.md"],
                similar_failures=1,
                calibration_examples=3,
            )
            AuditStore.record_routing_decision("healer", "drift with high confidence")
            AuditStore.record_cache_hit(False)
            return {"failure_class": "locator_drift", "confidence": 0.85}

        await full_node(FakeState())
        AuditStore.end_run()

        json_path = Path("memory/audit_runs/test-at3-e2e.json")
        assert json_path.exists()

        data = json.loads(json_path.read_text())
        node = data["nodes"][0]
        assert node["prompt_version"].startswith("TRIAGE.md@sha256:")
        assert node["memory_context"]["similar_failures_found"] == 1
        assert node["routing_decision"]["next_node"] == "healer"
        assert node["cache_hit"] is False

        json_path.unlink()
