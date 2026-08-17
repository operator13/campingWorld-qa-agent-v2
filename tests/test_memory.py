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


# ---------------------------------------------------------------------------
# Phase M3: App Structure
# ---------------------------------------------------------------------------

class TestAppStructure:
    def test_update_and_read_route(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/checkout", testids=["checkout-submit", "checkout-email"], components=["CartSummary"])

        info = store.get_route_info("/checkout")
        assert info is not None
        assert info["route"] == "/checkout"
        assert "checkout-submit" in info["testids"]
        assert "CartSummary" in info["components"]

    def test_creates_app_structure_file(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/login", testids=["login-email"])

        assert (tmp_path / "APP_STRUCTURE.md").exists()

    def test_update_existing_route(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/checkout", testids=["old-id"])
        store.update_route("/checkout", testids=["new-id"])

        info = store.get_route_info("/checkout")
        assert "new-id" in info["testids"]

    def test_multiple_routes(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/checkout", testids=["a"])
        store.update_route("/login", testids=["b"])

        assert store.get_route_info("/checkout") is not None
        assert store.get_route_info("/login") is not None

    def test_returns_none_for_unknown_route(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        assert store.get_route_info("/nonexistent") is None

    def test_increment_changes(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/checkout", testids=["a"])
        store.increment_route_changes("/checkout")
        store.increment_route_changes("/checkout")

        info = store.get_route_info("/checkout")
        assert info["changes"] == 2

    def test_get_all_routes(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/checkout", testids=["a"])
        store.update_route("/login", testids=["b"])

        routes = store.get_all_routes()
        assert len(routes) == 2


class TestVolatileRoutes:
    def test_returns_volatile_routes(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/checkout", testids=["a"])
        for _ in range(10):
            store.increment_route_changes("/checkout")

        volatile = store.get_volatile_routes(threshold=0.5)
        assert len(volatile) >= 1
        assert volatile[0]["route"] == "/checkout"

    def test_excludes_stable_routes(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/login", testids=["a"])

        volatile = store.get_volatile_routes(threshold=1.0)
        assert len(volatile) == 0

    def test_sorted_by_frequency(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/a", testids=[])
        store.update_route("/b", testids=[])
        for _ in range(5):
            store.increment_route_changes("/a")
        for _ in range(10):
            store.increment_route_changes("/b")

        volatile = store.get_volatile_routes(threshold=0.1)
        assert volatile[0]["route"] == "/b"

    def test_disabled_by_kill_switch(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MEMORY_ENABLED", "false")
        store = MemoryStore(memory_dir=tmp_path)
        assert store.get_volatile_routes() == []


class TestTestStability:
    def test_record_and_read(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_test_result("tc-checkout-01", "/checkout", True)

        history = store.get_test_history("tc-checkout-01")
        assert history is not None
        assert history["runs"] == 1
        assert history["passes"] == 1
        assert history["fails"] == 0
        assert history["flakiness"] == 0.0

    def test_accumulates_results(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_test_result("tc-1", "/checkout", True)
        store.record_test_result("tc-1", "/checkout", True)
        store.record_test_result("tc-1", "/checkout", False, "locator_drift")

        history = store.get_test_history("tc-1")
        assert history["runs"] == 3
        assert history["passes"] == 2
        assert history["fails"] == 1
        assert round(history["flakiness"], 2) == 0.33

    def test_flaky_detection(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        for i in range(5):
            store.record_test_result("tc-1", "/checkout", i < 3)

        flaky = store.get_flaky_tests(threshold=0.2)
        assert len(flaky) == 1
        assert flaky[0]["test_id"] == "tc-1"

    def test_stable_test_not_flagged(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        for _ in range(10):
            store.record_test_result("tc-stable", "/login", True)

        flaky = store.get_flaky_tests(threshold=0.2)
        assert len(flaky) == 0

    def test_multiple_tests(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_test_result("tc-1", "/checkout", True)
        store.record_test_result("tc-2", "/login", False, "app_defect")

        h1 = store.get_test_history("tc-1")
        h2 = store.get_test_history("tc-2")
        assert h1["passes"] == 1
        assert h2["fails"] == 1

    def test_returns_none_for_unknown_test(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        assert store.get_test_history("tc-nonexistent") is None

    def test_disabled_by_kill_switch(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PLANNER_MEMORY", "false")
        store = MemoryStore(memory_dir=tmp_path)
        store.record_test_result("tc-1", "/checkout", True)
        assert store.get_flaky_tests() == []

    def test_records_failure_class(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_test_result("tc-1", "/checkout", False, "locator_drift")

        history = store.get_test_history("tc-1")
        assert history["last_failure"] == "locator_drift"


class TestPlannerMemoryContext:
    def test_includes_volatile_routes(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/checkout", testids=["a"])
        for _ in range(10):
            store.increment_route_changes("/checkout")

        context = store.build_planner_memory_context()
        assert "Volatile Routes" in context
        assert "/checkout" in context

    def test_includes_flaky_tests(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        for i in range(5):
            store.record_test_result("tc-flaky", "/checkout", i < 2)

        context = store.build_planner_memory_context()
        assert "Flaky Tests" in context
        assert "tc-flaky" in context

    def test_empty_when_nothing_notable(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        context = store.build_planner_memory_context()
        assert context == ""

    def test_empty_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PLANNER_MEMORY", "false")
        store = MemoryStore(memory_dir=tmp_path)
        assert store.build_planner_memory_context() == ""


class TestGeneratorMemoryContext:
    def test_includes_known_testids(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/checkout", testids=["checkout-submit", "checkout-email"])

        context = store.build_generator_memory_context("/checkout")
        assert "Known testids" in context
        assert "checkout-submit" in context

    def test_includes_drift_history(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "old_loc", "new_loc", "drifted")

        context = store.build_generator_memory_context("/checkout")
        assert "drift history" in context
        assert "old_loc" in context

    def test_empty_for_unknown_route(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        context = store.build_generator_memory_context("/nonexistent")
        assert context == ""

    def test_empty_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GENERATOR_MEMORY", "false")
        store = MemoryStore(memory_dir=tmp_path)
        assert store.build_generator_memory_context("/checkout") == ""


# ---------------------------------------------------------------------------
# Phase M4: Maintenance
# ---------------------------------------------------------------------------

class TestPruneStale:
    def test_prunes_old_locator_entries(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        # Write an entry with an old date
        filepath = store._locator_file("/checkout")
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(
            "# Locator History: /checkout\n\n"
            "## submitBtn\n"
            "- 2020-01-01: `old` → `new` | reason: ancient | success: yes\n"
            "- 2026-08-01: `a` → `b` | reason: recent | success: yes\n"
        )

        pruned = store.prune_stale(max_age_days=90)
        assert pruned >= 1

        content = filepath.read_text()
        assert "2020-01-01" not in content
        assert "2026-08-01" in content

    def test_prunes_old_failure_patterns(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        filepath = tmp_path / "FAILURES.md"
        filepath.write_text(
            "# Failure Patterns\n"
            "\n## FP-001: old error\n"
            "- **Signature:** `old error`\n"
            "- **Class:** locator_drift\n"
            "- **Resolution:** healed\n"
            "- **Routes:** /old\n"
            "- **Occurrences:** 1\n"
            "- **Last seen:** 2020-01-01\n"
            "- **Stale after:** 2020-04-01\n"
            "\n## FP-002: new error\n"
            "- **Signature:** `new error`\n"
            "- **Class:** app_defect\n"
            "- **Resolution:** defect\n"
            "- **Routes:** /new\n"
            "- **Occurrences:** 1\n"
            "- **Last seen:** 2026-08-01\n"
            "- **Stale after:** 2026-11-01\n"
        )

        pruned = store.prune_stale(max_age_days=90)
        assert pruned >= 1

        content = filepath.read_text()
        assert "old error" not in content
        assert "new error" in content

    def test_prunes_old_human_decisions(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        filepath = tmp_path / "HUMAN_DECISIONS.md"
        filepath.write_text(
            "# Human Review Decisions\n\n"
            "| Date | Route | Error (summary) | Triage guess | Confidence | Human verdict | Reasoning |\n"
            "|------|-------|----------------|--------------|------------|---------------|----------|\n"
            "| 2020-01-01 | /old | old error | drift | 0.50 | heal | ancient |\n"
            "| 2026-08-01 | /new | new error | drift | 0.60 | heal | recent |\n"
        )

        pruned = store.prune_stale(max_age_days=90)
        assert pruned >= 1

        content = filepath.read_text()
        assert "2020-01-01" not in content
        assert "2026-08-01" in content

    def test_returns_zero_when_nothing_stale(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "a", "b", "recent")

        pruned = store.prune_stale(max_age_days=90)
        assert pruned == 0

    def test_returns_zero_on_empty_memory(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        pruned = store.prune_stale()
        assert pruned == 0


class TestDedupFailurePatterns:
    def test_merges_duplicates(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        filepath = tmp_path / "FAILURES.md"
        filepath.write_text(
            "# Failure Patterns\n"
            "\n## FP-001: timeout on button\n"
            "- **Signature:** `timeout on button`\n"
            "- **Class:** locator_drift\n"
            "- **Resolution:** healed\n"
            "- **Routes:** /checkout\n"
            "- **Occurrences:** 3\n"
            "- **Last seen:** 2026-08-01\n"
            "- **Stale after:** 2026-11-01\n"
            "\n## FP-002: timeout on button\n"
            "- **Signature:** `timeout on button`\n"
            "- **Class:** locator_drift\n"
            "- **Resolution:** healed\n"
            "- **Routes:** /checkout\n"
            "- **Occurrences:** 2\n"
            "- **Last seen:** 2026-08-10\n"
            "- **Stale after:** 2026-11-10\n"
        )

        merged = store.dedup_failure_patterns()
        assert merged == 1

        content = filepath.read_text()
        assert content.count("## FP-") == 1
        assert "5" in content  # 3 + 2 occurrences

    def test_no_duplicates_returns_zero(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure("error A unique", "drift", "healed", "/a")
        store.record_failure("error B unique", "defect", "filed", "/b")

        merged = store.dedup_failure_patterns()
        assert merged == 0

    def test_returns_zero_on_empty(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        merged = store.dedup_failure_patterns()
        assert merged == 0


class TestStats:
    def test_counts_all_entry_types(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "a", "b", "r")
        store.record_locator_change("/checkout", "input", "c", "d", "r")
        store.record_failure("error sig unique", "drift", "healed", "/checkout")
        store.record_human_decision("drift", 0.5, "heal", "err")
        store.update_route("/checkout", testids=["a"])
        store.record_test_result("tc-1", "/checkout", True)

        s = store.stats()
        assert s["files"]["locators"] >= 2
        assert s["files"]["failures"] >= 1
        assert s["files"]["human_decisions"] >= 1
        assert s["files"]["app_routes"] >= 1
        assert s["files"]["test_stability"] >= 1
        assert s["total_entries"] >= 6
        assert s["total_size_kb"] > 0

    def test_empty_memory(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        s = store.stats()
        assert s["total_entries"] == 0

    def test_size_is_reasonable(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        for i in range(20):
            store.record_locator_change("/checkout", f"el-{i}", f"old-{i}", f"new-{i}", "reason")

        s = store.stats()
        assert s["total_size_kb"] < 100  # should be tiny


class TestCLIMemory:
    def test_memory_stats_runs(self):
        """CLI memory stats doesn't crash."""
        from qa_agent.cli import _memory_stats
        # Just verify it runs without error
        _memory_stats()

    def test_memory_prune_runs(self, tmp_path):
        """CLI memory prune doesn't crash."""
        from qa_agent.cli import _memory_prune
        _memory_prune(max_age=90)

    def test_memory_learn_runs(self):
        """CLI memory learn doesn't crash."""
        from qa_agent.cli import _memory_learn
        _memory_learn()


# ---------------------------------------------------------------------------
# Phase M5: Lessons
# ---------------------------------------------------------------------------

class TestRecordLesson:
    def test_record_route_insight(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_lesson("route_insight", "/checkout", "Buttons rename every deploy — use testid")

        lessons = store.get_lessons(route="/checkout")
        assert len(lessons) >= 1
        assert "testid" in lessons[0]["content"]

    def test_record_decision_reflection(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_decision_reflection(
            route="/checkout",
            error="Timeout on Submit button",
            triage_class="locator_drift",
            triage_confidence=0.82,
            triage_correct=True,
            healer_fix="Changed to getByTestId",
            outcome="Passed on retry",
        )

        lessons = store.get_lessons(route="/checkout")
        reflections = [l for l in lessons if l["type"] == "decision_reflection"]
        assert len(reflections) >= 1
        assert "locator_drift" in reflections[0]["content"]

    def test_record_pattern(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_lesson("pattern", "/", "Button text rename | 5 | 100% | getByTestId")

        scoreboard = store.get_pattern_scoreboard()
        assert len(scoreboard) >= 1

    def test_creates_lessons_file(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_lesson("route_insight", "/login", "Stable route")

        assert (tmp_path / "LESSONS.md").exists()

    def test_multiple_lessons_same_route(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_lesson("route_insight", "/checkout", "Lesson 1")
        store.record_lesson("route_insight", "/checkout", "Lesson 2")

        lessons = store.get_lessons(route="/checkout")
        route_insights = [l for l in lessons if l["type"] == "route_insight"]
        assert len(route_insights) >= 1
        # Both should be in the content
        content = route_insights[0]["content"]
        assert "Lesson 1" in content
        assert "Lesson 2" in content

    def test_filter_by_route(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_lesson("route_insight", "/checkout", "Checkout lesson")
        store.record_lesson("route_insight", "/login", "Login lesson")

        checkout = store.get_lessons(route="/checkout")
        assert all("/checkout" in l.get("route", "") for l in checkout)

    def test_disabled_by_kill_switch(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LESSONS_MEMORY", "false")
        store = MemoryStore(memory_dir=tmp_path)
        store.record_lesson("route_insight", "/checkout", "Should not be saved")
        assert store.get_lessons() == []


class TestPatternScoreboard:
    def test_generates_from_locator_history(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        # Seed locator history
        store.record_locator_change("/checkout", "btn",
            "getByRole('button', { name: 'Submit' })",
            "getByTestId('checkout-submit')", "name changed")
        store.record_locator_change("/checkout", "btn2",
            "getByRole('button', { name: 'Cancel' })",
            "getByTestId('checkout-cancel')", "name changed")

        scoreboard = store.generate_pattern_scoreboard()
        assert len(scoreboard) >= 1
        # Should identify button text rename pattern
        assert any("rename" in p["pattern"].lower() or "text" in p["pattern"].lower() for p in scoreboard)

    def test_empty_on_no_data(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        scoreboard = store.generate_pattern_scoreboard()
        assert scoreboard == []

    def test_disabled_by_kill_switch(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LESSONS_MEMORY", "false")
        store = MemoryStore(memory_dir=tmp_path)
        assert store.generate_pattern_scoreboard() == []


class TestRouteInsightsGeneration:
    def test_generates_stability_insight(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/checkout", testids=["checkout-submit"])
        for _ in range(15):
            store.increment_route_changes("/checkout")

        insights = store.generate_route_insights()
        assert "/checkout" in insights
        assert "LOW" in insights["/checkout"] or "MEDIUM" in insights["/checkout"]

    def test_stable_route_insight(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/login", testids=["login-email"])
        # No changes — should be HIGH stability

        insights = store.generate_route_insights()
        assert "/login" in insights
        assert "HIGH" in insights["/login"]

    def test_empty_on_no_routes(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        insights = store.generate_route_insights()
        assert insights == {}


class TestLessonsContext:
    def test_includes_scoreboard(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_lesson("pattern", "/", "Button rename | 5 | 100% | getByTestId")

        context = store.build_lessons_context()
        assert "Pattern Scoreboard" in context

    def test_includes_route_insights(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_lesson("route_insight", "/checkout", "Buttons change every deploy")

        context = store.build_lessons_context(route="/checkout")
        assert "Route Insights" in context
        assert "Buttons change" in context

    def test_empty_when_no_lessons(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        context = store.build_lessons_context()
        assert context == ""

    def test_empty_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LESSONS_MEMORY", "false")
        store = MemoryStore(memory_dir=tmp_path)
        assert store.build_lessons_context() == ""

    def test_respects_token_cap(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        for i in range(20):
            store.record_lesson("pattern", "/", f"Pattern {i} long description " * 5 + f"| {i} | 50% | mixed")

        context = store.build_lessons_context(max_tokens=100)
        assert len(context) <= 500
