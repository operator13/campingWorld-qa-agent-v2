"""Tests for cost/load controls."""

import pytest

from qa_agent.budget import (
    BudgetExhaustedError,
    ConcurrencyLimiter,
    TokenBudget,
)


class TestTokenBudget:
    def test_initial_state(self):
        budget = TokenBudget(max_tokens=100_000)
        assert budget.total_tokens == 0
        assert budget.remaining == 100_000
        assert not budget.exhausted

    def test_record_usage(self):
        budget = TokenBudget(max_tokens=1000)
        budget.record(input_tokens=300, output_tokens=200)
        assert budget.input_tokens == 300
        assert budget.output_tokens == 200
        assert budget.total_tokens == 500
        assert budget.remaining == 500

    def test_exhaustion(self):
        budget = TokenBudget(max_tokens=1000)
        budget.record(600, 500)
        assert budget.exhausted
        assert budget.remaining == 0

    def test_check_raises_when_exhausted(self):
        budget = TokenBudget(max_tokens=100)
        budget.record(60, 50)
        with pytest.raises(BudgetExhaustedError):
            budget.check()

    def test_check_passes_when_ok(self):
        budget = TokenBudget(max_tokens=1000)
        budget.record(100, 100)
        budget.check()  # should not raise

    def test_summary(self):
        budget = TokenBudget(max_tokens=5000)
        budget.record(1000, 500)
        s = budget.summary()
        assert s["input_tokens"] == 1000
        assert s["output_tokens"] == 500
        assert s["total_tokens"] == 1500
        assert s["max_tokens"] == 5000
        assert s["remaining"] == 3500

    def test_multiple_records_accumulate(self):
        budget = TokenBudget(max_tokens=10000)
        budget.record(100, 50)
        budget.record(200, 100)
        budget.record(300, 150)
        assert budget.total_tokens == 900


class TestConcurrencyLimiter:
    def test_acquire_within_limit(self):
        limiter = ConcurrencyLimiter(max_concurrent=2)
        assert limiter.acquire() is True
        assert limiter.acquire() is True
        assert limiter.acquire() is False  # third blocked

    def test_release_frees_slot(self):
        limiter = ConcurrencyLimiter(max_concurrent=1)
        assert limiter.acquire() is True
        assert limiter.acquire() is False
        limiter.release()
        assert limiter.acquire() is True

    def test_context_manager(self):
        limiter = ConcurrencyLimiter(max_concurrent=1)
        with limiter:
            assert limiter.acquire() is False  # slot taken
        assert limiter.acquire() is True  # slot released
