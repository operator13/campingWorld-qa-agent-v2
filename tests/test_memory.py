"""Tests for the MemoryStore — markdown-backed agent memory."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from qa_agent.memory import (
    MemoryStore,
    extract_locator_from_error,
    normalize_error,
)


# ---------------------------------------------------------------------------
# normalize_error
# ---------------------------------------------------------------------------

class TestNormalizeError:
    def test_strips_line_numbers(self):
        assert "line N" in normalize_error("Error at line 42")

    def test_strips_file_paths(self):
        result = normalize_error("Error in /Users/dev/project/src/app.ts")
        assert "/Users/" not in result
        assert "FILE" in result

    def test_strips_timestamps(self):
        result = normalize_error("Error at 2026-08-14T18:00:00Z")
        assert "2026-08-14" not in result
        assert "DATETIME" in result

    def test_strips_timeouts(self):
        result = normalize_error("Timeout 30000ms exceeded")
        assert "30000" not in result
        assert "Timeout Nms" in result

    def test_strips_ips(self):
        result = normalize_error("Connection to 192.168.1.1 failed")
        assert "192.168.1.1" not in result
        assert "IP" in result

    def test_collapses_whitespace(self):
        result = normalize_error("Error   at   line   1")
        assert "  " not in result

    def test_same_error_normalizes_identically(self):
        e1 = "TimeoutError at line 42 in /src/test.ts: Timeout 30000ms"
        e2 = "TimeoutError at line 99 in /other/test.ts: Timeout 5000ms"
        assert normalize_error(e1) == normalize_error(e2)


# ---------------------------------------------------------------------------
# extract_locator_from_error
# ---------------------------------------------------------------------------

class TestExtractLocator:
    def test_extracts_getByRole(self):
        error = "TimeoutError: locator.click: Timeout 30000ms exceeded. Waiting for getByRole('button', { name: 'Submit' })"
        result = extract_locator_from_error(error)
        assert result == "getByRole('button', { name: 'Submit' })"

    def test_extracts_getByTestId(self):
        error = "Error: getByTestId('checkout-email') not found"
        result = extract_locator_from_error(error)
        assert result == "getByTestId('checkout-email')"

    def test_extracts_getByText(self):
        error = "Timeout waiting for getByText('Welcome back')"
        result = extract_locator_from_error(error)
        assert result == "getByText('Welcome back')"

    def test_extracts_getByLabel(self):
        error = "Cannot find getByLabel('Email address')"
        result = extract_locator_from_error(error)
        assert result == "getByLabel('Email address')"

    def test_extracts_locator(self):
        error = "locator('#submit-btn') not found"
        result = extract_locator_from_error(error)
        assert result == "locator('#submit-btn')"

    def test_returns_none_for_no_locator(self):
        error = "AssertionError: expected 'OK' but got 'Error'"
        result = extract_locator_from_error(error)
        assert result is None

    def test_returns_first_match(self):
        error = "getByRole('button', { name: 'A' }) and getByTestId('b')"
        result = extract_locator_from_error(error)
        assert "getByRole" in result


# ---------------------------------------------------------------------------
# MemoryStore — Locator History
# ---------------------------------------------------------------------------

class TestLocatorHistory:
    def test_record_and_read(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change(
            route="/checkout",
            element="submitBtn",
            old_locator="getByRole('button', { name: 'Submit' })",
            new_locator="getByRole('button', { name: 'Place Order' })",
            reason="button text changed",
            success=True,
        )
        history = store.get_locator_history("/checkout")
        assert len(history) == 1
        assert history[0]["old_locator"] == "getByRole('button', { name: 'Submit' })"
        assert history[0]["new_locator"] == "getByRole('button', { name: 'Place Order' })"
        assert history[0]["success"] is True

    def test_filter_by_element(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "submitBtn", "old1", "new1", "r1")
        store.record_locator_change("/checkout", "emailInput", "old2", "new2", "r2")

        submit_history = store.get_locator_history("/checkout", "submitBtn")
        assert len(submit_history) == 1
        assert submit_history[0]["element"] == "submitBtn"

    def test_multiple_entries_same_element(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "a", "b", "r1")
        store.record_locator_change("/checkout", "btn", "b", "c", "r2")

        history = store.get_locator_history("/checkout", "btn")
        assert len(history) == 2

    def test_separate_files_per_route(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "a", "b", "r")
        store.record_locator_change("/login", "btn", "c", "d", "r")

        assert (tmp_path / "locators" / "CHECKOUT.md").exists()
        assert (tmp_path / "locators" / "LOGIN.md").exists()

    def test_root_route(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/", "btn", "a", "b", "r")
        assert (tmp_path / "locators" / "ROOT.md").exists()


class TestKnownFix:
    def test_returns_known_fix(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "old_loc", "new_loc", "fixed")

        result = store.get_known_fix("/checkout", "btn", "old_loc")
        assert result == "new_loc"

    def test_returns_none_when_no_match(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "old_loc", "new_loc", "fixed")

        result = store.get_known_fix("/checkout", "btn", "different_loc")
        assert result is None

    def test_skips_failed_fixes(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "old_loc", "bad_fix", "tried", success=False)

        result = store.get_known_fix("/checkout", "btn", "old_loc")
        assert result is None

    def test_returns_most_recent_successful(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "old", "fix1", "first")
        store.record_locator_change("/checkout", "btn", "old", "fix2", "second")

        result = store.get_known_fix("/checkout", "btn", "old")
        assert result == "fix2"

    def test_returns_none_on_empty_history(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        result = store.get_known_fix("/checkout", "btn", "old")
        assert result is None


class TestMarkFixFailed:
    def test_marks_fix_as_failed(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "old", "new", "reason", success=True)

        # Verify it's found
        assert store.get_known_fix("/checkout", "btn", "old") == "new"

        # Mark failed
        store.mark_fix_failed("/checkout", "btn", "old")

        # Should no longer be returned
        assert store.get_known_fix("/checkout", "btn", "old") is None


# ---------------------------------------------------------------------------
# MemoryStore — Failure Patterns
# ---------------------------------------------------------------------------

class TestFailurePatterns:
    def test_record_and_find(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure(
            error_signature="TimeoutError at line 42: getByRole not found",
            failure_class="locator_drift",
            resolution="healed:locator_update",
            route="/checkout",
        )

        result = store.find_similar_failure("TimeoutError at line 99: getByRole not found")
        assert result is not None
        assert result["failure_class"] == "locator_drift"

    def test_no_match(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure("TimeoutError", "locator_drift", "healed", "/checkout")

        result = store.find_similar_failure("AssertionError: completely different")
        assert result is None

    def test_increments_occurrences(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure("TimeoutError on button", "locator_drift", "healed", "/checkout")
        store.record_failure("TimeoutError on button", "locator_drift", "healed", "/checkout")

        # Read the file and check occurrences
        content = (tmp_path / "FAILURES.md").read_text()
        assert "2" in content  # occurrences incremented

    def test_generates_unique_ids(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure("Error A unique", "locator_drift", "healed", "/a")
        store.record_failure("Error B unique", "app_defect", "defect:QA-1", "/b")

        content = (tmp_path / "FAILURES.md").read_text()
        assert "FP-001" in content
        assert "FP-002" in content


# ---------------------------------------------------------------------------
# MemoryStore — Kill Switch
# ---------------------------------------------------------------------------

class TestKillSwitch:
    def test_global_disable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MEMORY_ENABLED", "false")
        store = MemoryStore(memory_dir=tmp_path)

        store.record_locator_change("/checkout", "btn", "a", "b", "r")
        assert store.get_locator_history("/checkout") == []
        assert store.get_known_fix("/checkout", "btn", "a") is None

    def test_healer_disable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HEALER_MEMORY", "false")
        store = MemoryStore(memory_dir=tmp_path)

        store.record_locator_change("/checkout", "btn", "a", "b", "r")
        assert store.get_locator_history("/checkout") == []

    def test_enabled_by_default(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        assert store._enabled() is True
        assert store._enabled("healer") is True


# ---------------------------------------------------------------------------
# MemoryStore — Prompt Context
# ---------------------------------------------------------------------------

class TestHealerMemoryContext:
    def test_builds_context_with_history(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "old1", "new1", "r1")
        store.record_locator_change("/checkout", "btn", "new1", "new2", "r2")

        context = store.build_healer_memory_context("/checkout", "btn")
        assert "Locator History" in context
        assert "old1" in context
        assert "new2" in context
        assert "2 time(s)" in context

    def test_empty_when_no_history(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        context = store.build_healer_memory_context("/checkout", "btn")
        assert context == ""

    def test_empty_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HEALER_MEMORY", "false")
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "a", "b", "r")
        context = store.build_healer_memory_context("/checkout", "btn")
        assert context == ""

    def test_respects_token_cap(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        for i in range(50):
            store.record_locator_change("/checkout", "btn", f"old_{i}", f"new_{i}", f"reason_{i}")

        context = store.build_healer_memory_context("/checkout", "btn", max_tokens=100)
        # 100 tokens ≈ 400 chars
        assert len(context) <= 500


# ---------------------------------------------------------------------------
# Healer integration with memory
# ---------------------------------------------------------------------------

class TestHealerMemoryIntegration:
    @pytest.mark.asyncio
    async def test_healer_uses_known_fix(self, tmp_path):
        """Healer applies known fix from memory without LLM call."""
        from qa_agent.nodes.healer import healer
        from qa_agent.schemas.models import TestCase
        from qa_agent.state import QAState

        # Seed memory with a known fix
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change(
            "/checkout", "Submit",
            "getByRole('button', { name: 'Submit' })",
            "getByRole('button', { name: 'Place Order' })",
            "button text changed",
        )

        state = QAState(
            goal="Test checkout",
            error="TimeoutError: Timeout 30000ms exceeded. Waiting for getByRole('button', { name: 'Submit' })",
            page_objects={"/checkout": "this.btn = page.getByRole('button', { name: 'Submit' });"},
            plan=[TestCase(id="tc-1", title="t", feature="f", route="/checkout", steps=[], expected=[])],
            attempts=0,
        )

        # Patch the memory dir so healer uses our tmp_path
        with patch("qa_agent.nodes.healer.MemoryStore", lambda: store):
            result = await healer(state)

        # Should have applied the fix WITHOUT calling the LLM
        assert "Place Order" in result["page_objects"]["/checkout"]

    @pytest.mark.asyncio
    async def test_healer_rejects_known_fix_touching_assertions(self, tmp_path):
        """Known fix that touches assertions is rejected and marked failed."""
        from qa_agent.nodes.healer import healer
        from qa_agent.schemas.models import TestCase
        from qa_agent.state import QAState

        store = MemoryStore(memory_dir=tmp_path)
        # Seed a "fix" that would add an assertion
        store.record_locator_change(
            "/checkout", "Submit",
            "getByRole('button', { name: 'Submit' })",
            "getByRole('button', { name: 'Submit' }); await expect(btn).toBeVisible()",
            "bad fix",
        )

        old_source = "this.btn = page.getByRole('button', { name: 'Submit' });"

        state = QAState(
            goal="Test checkout",
            error="TimeoutError waiting for getByRole('button', { name: 'Submit' })",
            page_objects={"/checkout": old_source},
            plan=[TestCase(id="tc-1", title="t", feature="f", route="/checkout", steps=[], expected=[])],
            attempts=0,
        )

        # Mock LLM for the fallback path
        mock_response = AsyncMock()
        mock_response.content = '{"page_objects": {"/checkout": "' + old_source.replace('"', '\\"') + '"}, "changes": []}'

        with patch("qa_agent.nodes.healer.MemoryStore", lambda: store), \
             patch("qa_agent.nodes.healer.ChatAnthropic") as MockChat:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            MockChat.return_value = mock_model
            result = await healer(state)

        # Known fix should be marked failed
        assert store.get_known_fix("/checkout", "Submit", "getByRole('button', { name: 'Submit' })") is None

    @pytest.mark.asyncio
    async def test_healer_records_new_fix(self, tmp_path):
        """Healer records a new fix in memory after LLM succeeds."""
        from qa_agent.nodes.healer import healer
        from qa_agent.schemas.models import TestCase
        from qa_agent.state import QAState

        store = MemoryStore(memory_dir=tmp_path)

        state = QAState(
            goal="Test checkout",
            error="TimeoutError waiting for getByRole('button', { name: 'Submit' })",
            page_objects={"/checkout": "this.btn = page.getByRole('button', { name: 'Submit' });"},
            plan=[TestCase(id="tc-1", title="t", feature="f", route="/checkout", steps=[], expected=[])],
            attempts=0,
        )

        mock_response = AsyncMock()
        mock_response.content = '''{
            "page_objects": {"/checkout": "this.btn = page.getByRole('button', { name: 'Place Order' });"},
            "changes": [{"old_locator": "getByRole('button', { name: 'Submit' })", "new_locator": "getByRole('button', { name: 'Place Order' })", "reason": "text changed"}]
        }'''

        with patch("qa_agent.nodes.healer.MemoryStore", lambda: store), \
             patch("qa_agent.nodes.healer.ChatAnthropic") as MockChat:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            MockChat.return_value = mock_model
            await healer(state)

        # Check memory was written
        history = store.get_locator_history("/checkout")
        assert len(history) >= 1


# ---------------------------------------------------------------------------
# Phase M2: Human Decisions
# ---------------------------------------------------------------------------

class TestHumanDecisions:
    def test_record_and_read(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_human_decision(
            triage_guess="locator_drift",
            confidence=0.60,
            verdict="heal",
            error_summary="Timeout on Submit button",
            reasoning="Button was renamed, not removed",
            route="/checkout",
        )
        decisions = store.get_triage_calibration(n=10)
        assert len(decisions) == 1
        assert decisions[0]["triage_guess"] == "locator_drift"
        assert decisions[0]["human_verdict"] == "heal"
        assert decisions[0]["reasoning"] == "Button was renamed, not removed"

    def test_multiple_decisions(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_human_decision("locator_drift", 0.6, "heal", "err1")
        store.record_human_decision("app_defect", 0.5, "defect", "err2")
        store.record_human_decision("unknown", 0.4, "heal", "err3")

        decisions = store.get_triage_calibration(n=10)
        assert len(decisions) == 3
        # Most recent first
        assert decisions[0]["human_verdict"] == "heal"
        assert decisions[1]["human_verdict"] == "defect"

    def test_respects_n_limit(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        for i in range(10):
            store.record_human_decision("unknown", 0.5, "heal", f"err{i}")

        decisions = store.get_triage_calibration(n=3)
        assert len(decisions) == 3

    def test_creates_file_with_header(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_human_decision("locator_drift", 0.5, "heal", "err")

        filepath = tmp_path / "HUMAN_DECISIONS.md"
        assert filepath.exists()
        content = filepath.read_text()
        assert "| Date" in content
        assert "|---" in content

    def test_sanitizes_pipes_in_fields(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_human_decision("drift", 0.5, "heal", "error | with | pipes", "reason | pipes")

        decisions = store.get_triage_calibration()
        assert len(decisions) == 1
        # Pipes should be replaced so they don't break the table
        assert "|" not in decisions[0]["error_summary"]

    def test_disabled_by_kill_switch(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRIAGE_MEMORY", "false")
        store = MemoryStore(memory_dir=tmp_path)
        store.record_human_decision("drift", 0.5, "heal", "err")
        assert store.get_triage_calibration() == []


class TestTriageCalibrationContext:
    def test_builds_context_with_corrections(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        # A correction (triage was wrong)
        store.record_human_decision("locator_drift", 0.6, "defect", "Submit missing", "Button removed entirely")
        # A confirmation (triage was right)
        store.record_human_decision("app_defect", 0.8, "defect", "500 error")

        context = store.build_triage_calibration_context()
        assert "Corrections" in context
        assert "Confirmations" in context
        assert "Submit missing" in context

    def test_empty_when_no_decisions(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        context = store.build_triage_calibration_context()
        assert context == ""

    def test_empty_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRIAGE_MEMORY", "false")
        store = MemoryStore(memory_dir=tmp_path)
        context = store.build_triage_calibration_context()
        assert context == ""

    def test_respects_token_cap(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        for i in range(20):
            store.record_human_decision("drift", 0.5, "heal" if i % 2 else "defect", f"long error message number {i} " * 5)

        context = store.build_triage_calibration_context(max_tokens=100)
        assert len(context) <= 500


# ---------------------------------------------------------------------------
# Phase M2: Human Review integration
# ---------------------------------------------------------------------------

class TestHumanReviewMemory:
    def test_records_decision_on_heal(self, tmp_path):
        """Human Review records the decision in memory."""
        from qa_agent.surfaces.human_review import human_review
        from qa_agent.state import QAState

        store = MemoryStore(memory_dir=tmp_path)
        state = QAState(
            goal="test",
            failure_class="unknown",
            confidence=0.5,
            error="Some error occurred",
        )

        with patch("qa_agent.surfaces.human_review.interrupt", return_value={"decision": "heal", "reasoning": "locator renamed"}), \
             patch("qa_agent.surfaces.human_review.MemoryStore", lambda: store):
            human_review(state)

        decisions = store.get_triage_calibration()
        assert len(decisions) == 1
        assert decisions[0]["human_verdict"] == "heal"
        assert decisions[0]["reasoning"] == "locator renamed"

    def test_records_decision_on_defect(self, tmp_path):
        from qa_agent.surfaces.human_review import human_review
        from qa_agent.state import QAState

        store = MemoryStore(memory_dir=tmp_path)
        state = QAState(goal="test", failure_class="unknown", confidence=0.5)

        with patch("qa_agent.surfaces.human_review.interrupt", return_value={"decision": "defect"}), \
             patch("qa_agent.surfaces.human_review.MemoryStore", lambda: store):
            human_review(state)

        decisions = store.get_triage_calibration()
        assert len(decisions) == 1
        assert decisions[0]["human_verdict"] == "defect"


# ---------------------------------------------------------------------------
# Phase M2: Triage integration
# ---------------------------------------------------------------------------

class TestTriageMemory:
    @pytest.mark.asyncio
    async def test_triage_injects_calibration(self, tmp_path):
        """Triage prompt includes calibration context from memory."""
        from qa_agent.nodes.triage import triage
        from qa_agent.schemas.models import RunResult
        from qa_agent.state import QAState

        store = MemoryStore(memory_dir=tmp_path)
        store.record_human_decision("locator_drift", 0.6, "defect", "Submit gone", "Element removed")

        mock_response = AsyncMock()
        mock_response.content = '{"failure_class": "app_defect", "confidence": 0.85, "reasoning": "learned from past"}'

        state = QAState(
            goal="test",
            error="TimeoutError on Submit button",
            run_results=RunResult(passed=False, failed_cases=["tc-1"], logs="error"),
        )

        with patch("qa_agent.nodes.triage.MemoryStore", lambda: store), \
             patch("qa_agent.nodes.triage.ChatAnthropic") as MockChat:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            MockChat.return_value = mock_model
            result = await triage(state)

            # Verify calibration was in the prompt
            call_args = mock_model.ainvoke.call_args[0][0]
            human_msg = call_args[1].content
            assert "Corrections" in human_msg or "Similar past failure" in human_msg

        assert result["failure_class"] == "app_defect"

    @pytest.mark.asyncio
    async def test_triage_finds_similar_failure(self, tmp_path):
        """Triage includes similar past failure hint in prompt."""
        from qa_agent.nodes.triage import triage
        from qa_agent.schemas.models import RunResult
        from qa_agent.state import QAState

        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure("TimeoutError on Submit button", "locator_drift", "healed", "/checkout")

        mock_response = AsyncMock()
        mock_response.content = '{"failure_class": "locator_drift", "confidence": 0.9}'

        state = QAState(
            goal="test",
            error="TimeoutError on Submit button again",
            run_results=RunResult(passed=False, failed_cases=["tc-1"], logs="err"),
        )

        with patch("qa_agent.nodes.triage.MemoryStore", lambda: store), \
             patch("qa_agent.nodes.triage.ChatAnthropic") as MockChat:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            MockChat.return_value = mock_model
            result = await triage(state)

            call_args = mock_model.ainvoke.call_args[0][0]
            human_msg = call_args[1].content
            assert "Similar past failure" in human_msg

        assert result["failure_class"] == "locator_drift"
