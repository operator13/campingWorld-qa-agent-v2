"""Tests for Audit Trail Phase AT2 — Token Tracking + Cost Estimation."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from qa_agent.audit import AuditStore, audit_node
from qa_agent.config import estimate_cost, COST_PER_MILLION_TOKENS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FakeState:
    """Minimal state object for testing."""
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


class MockLLMResponse:
    """Simulates a LangChain AIMessage with usage_metadata."""

    def __init__(self, input_tokens: int = 1000, output_tokens: int = 500, model: str = "claude-sonnet-4-6"):
        self.usage_metadata = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
        self.response_metadata = {"model": model}
        self.content = '{"result": "ok"}'


@pytest.fixture(autouse=True)
def reset_audit_state():
    """Reset AuditStore class-level state before each test."""
    AuditStore._current_run_id = None
    AuditStore._current_run_entries = []
    AuditStore._run_start_time = None
    AuditStore._current_node_llm_calls = []
    AuditStore._run_total_input_tokens = 0
    AuditStore._run_total_output_tokens = 0
    AuditStore._run_total_cost = 0.0
    yield
    AuditStore._current_run_id = None
    AuditStore._current_run_entries = []
    AuditStore._current_node_llm_calls = []


# ---------------------------------------------------------------------------
# Cost estimation tests
# ---------------------------------------------------------------------------

class TestCostEstimation:

    def test_sonnet_cost_calculation(self):
        cost = estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert cost == 3.00 + 15.00  # $3 input + $15 output

    def test_opus_cost_calculation(self):
        cost = estimate_cost("claude-opus-4-6", 1_000_000, 1_000_000)
        assert cost == 15.00 + 75.00

    def test_haiku_cost_calculation(self):
        cost = estimate_cost("claude-haiku-4-5", 1_000_000, 1_000_000)
        assert cost == 0.80 + 4.00

    def test_unknown_model_uses_sonnet_pricing(self):
        cost = estimate_cost("unknown-model", 1_000_000, 1_000_000)
        assert cost == 3.00 + 15.00  # Falls back to default

    def test_zero_tokens_zero_cost(self):
        cost = estimate_cost("claude-sonnet-4-6", 0, 0)
        assert cost == 0.0

    def test_small_token_count(self):
        cost = estimate_cost("claude-sonnet-4-6", 1000, 500)
        expected = (1000 / 1_000_000 * 3.00) + (500 / 1_000_000 * 15.00)
        assert abs(cost - expected) < 0.000001

    def test_cost_map_has_expected_models(self):
        assert "claude-sonnet-4-6" in COST_PER_MILLION_TOKENS
        assert "claude-opus-4-6" in COST_PER_MILLION_TOKENS
        assert "claude-haiku-4-5" in COST_PER_MILLION_TOKENS


# ---------------------------------------------------------------------------
# record_llm_call tests
# ---------------------------------------------------------------------------

class TestRecordLlmCall:

    def test_records_token_counts(self):
        response = MockLLMResponse(input_tokens=1500, output_tokens=300)
        AuditStore.record_llm_call(response, model="claude-sonnet-4-6")

        assert len(AuditStore._current_node_llm_calls) == 1
        call = AuditStore._current_node_llm_calls[0]
        assert call["input_tokens"] == 1500
        assert call["output_tokens"] == 300
        assert call["model"] == "claude-sonnet-4-6"

    def test_records_model_from_response_metadata(self):
        response = MockLLMResponse(model="claude-opus-4-6")
        AuditStore.record_llm_call(response)  # No explicit model

        call = AuditStore._current_node_llm_calls[0]
        assert call["model"] == "claude-opus-4-6"

    def test_explicit_model_overrides_metadata(self):
        response = MockLLMResponse(model="claude-opus-4-6")
        AuditStore.record_llm_call(response, model="claude-sonnet-4-6")

        call = AuditStore._current_node_llm_calls[0]
        assert call["model"] == "claude-sonnet-4-6"

    def test_handles_missing_usage_metadata(self):
        response = MagicMock()
        response.usage_metadata = None
        response.response_metadata = {}
        AuditStore.record_llm_call(response)

        call = AuditStore._current_node_llm_calls[0]
        assert call["input_tokens"] == 0
        assert call["output_tokens"] == 0

    def test_multiple_calls_accumulate(self):
        AuditStore.record_llm_call(MockLLMResponse(100, 50))
        AuditStore.record_llm_call(MockLLMResponse(200, 75))

        assert len(AuditStore._current_node_llm_calls) == 2


# ---------------------------------------------------------------------------
# _consume_llm_calls tests
# ---------------------------------------------------------------------------

class TestConsumeLlmCalls:

    def test_consumes_and_clears(self):
        AuditStore.start_run("test-consume")
        AuditStore.record_llm_call(MockLLMResponse(1000, 500))

        result = AuditStore._consume_llm_calls()

        assert result["input_tokens"] == 1000
        assert result["output_tokens"] == 500
        assert result["model"] == "claude-sonnet-4-6"
        assert result["cost_usd"] > 0
        assert AuditStore._current_node_llm_calls == []  # Cleared

    def test_sums_multiple_calls(self):
        AuditStore.start_run("test-sum")
        AuditStore.record_llm_call(MockLLMResponse(1000, 500))
        AuditStore.record_llm_call(MockLLMResponse(2000, 300))

        result = AuditStore._consume_llm_calls()

        assert result["input_tokens"] == 3000
        assert result["output_tokens"] == 800

    def test_empty_returns_zeros(self):
        result = AuditStore._consume_llm_calls()

        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0
        assert result["cost_usd"] == 0.0
        assert result["model"] is None

    def test_accumulates_run_totals(self):
        AuditStore.start_run("test-totals")

        AuditStore.record_llm_call(MockLLMResponse(1000, 500))
        AuditStore._consume_llm_calls()

        AuditStore.record_llm_call(MockLLMResponse(2000, 300))
        AuditStore._consume_llm_calls()

        assert AuditStore._run_total_input_tokens == 3000
        assert AuditStore._run_total_output_tokens == 800
        assert AuditStore._run_total_cost > 0


# ---------------------------------------------------------------------------
# Decorator integration with token tracking
# ---------------------------------------------------------------------------

class TestAuditNodeWithTokens:

    @pytest.mark.asyncio
    async def test_decorator_captures_tokens(self, tmp_path):
        AuditStore.start_run("test-decorator-tokens")

        @audit_node("test_llm_node")
        async def fake_llm_node(state):
            # Simulate what a real node does: call LLM then record
            response = MockLLMResponse(1500, 300)
            AuditStore.record_llm_call(response, model="claude-sonnet-4-6")
            return {"result": "ok"}

        await fake_llm_node(FakeState())

        entry = AuditStore._current_run_entries[0]
        assert entry["input_tokens"] == 1500
        assert entry["output_tokens"] == 300
        assert entry["model"] == "claude-sonnet-4-6"
        assert entry["cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_decorator_non_llm_node_has_zero_tokens(self):
        AuditStore.start_run("test-no-llm")

        @audit_node("test_no_llm_node")
        async def no_llm_node(state):
            return {"result": "done"}

        await no_llm_node(FakeState())

        entry = AuditStore._current_run_entries[0]
        assert entry["input_tokens"] == 0
        assert entry["output_tokens"] == 0
        assert entry["cost_usd"] == 0.0
        assert entry["model"] is None

    @pytest.mark.asyncio
    async def test_decorator_captures_tokens_on_error(self):
        AuditStore.start_run("test-error-tokens")

        @audit_node("test_error_node")
        async def error_node(state):
            response = MockLLMResponse(500, 100)
            AuditStore.record_llm_call(response, model="claude-sonnet-4-6")
            raise ValueError("intentional error")

        with pytest.raises(ValueError):
            await error_node(FakeState())

        entry = AuditStore._current_run_entries[0]
        assert entry["input_tokens"] == 500
        assert entry["output_tokens"] == 100
        assert entry["errors"] == ["intentional error"]


# ---------------------------------------------------------------------------
# End-to-end run with token totals
# ---------------------------------------------------------------------------

class TestEndRunWithTokens:

    @pytest.mark.asyncio
    async def test_end_run_populates_totals(self):
        AuditStore.start_run("test-run-totals")

        @audit_node("node_a")
        async def node_a(state):
            AuditStore.record_llm_call(MockLLMResponse(1000, 500))
            return {}

        @audit_node("node_b")
        async def node_b(state):
            AuditStore.record_llm_call(MockLLMResponse(2000, 300))
            return {}

        await node_a(FakeState())
        await node_b(FakeState())

        AuditStore.end_run()

        json_path = Path("memory/audit_runs/test-run-totals.json")
        assert json_path.exists()

        data = json.loads(json_path.read_text())
        assert data["total_input_tokens"] == 3000
        assert data["total_output_tokens"] == 800
        assert data["estimated_cost_usd"] > 0

        # Per-node tokens
        assert data["nodes"][0]["input_tokens"] == 1000
        assert data["nodes"][1]["input_tokens"] == 2000

        # Cleanup
        json_path.unlink()
