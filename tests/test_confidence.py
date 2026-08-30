"""Tests for the confidence rubric scoring engine."""

from __future__ import annotations

import pytest

from qa_agent.confidence import (
    ConfidenceBreakdown,
    apply_guards,
    score_c1_error_type,
    score_c2_dom_evidence,
    score_c3_history_match,
    score_c4_human_calibration,
    score_c5_consistency,
    score_confidence,
)
from qa_agent.memory import MemoryStore


# ---------------------------------------------------------------------------
# C1: Error type signal
# ---------------------------------------------------------------------------

class TestC1ErrorType:
    def test_clear_drift_signal(self):
        assert score_c1_error_type("selector-not-found: button 'Submit'") == 0.3

    def test_clear_defect_signal(self):
        assert score_c1_error_type("AssertionError: expected 'OK' got 'Error'") == 0.3

    def test_http_500_defect(self):
        assert score_c1_error_type("net::ERR_FAILED 500 Internal Server Error") == 0.3

    def test_timeout_ambiguous(self):
        assert score_c1_error_type("TimeoutError: Timeout 30000ms exceeded") == 0.1

    def test_generic_error(self):
        assert score_c1_error_type("Something went wrong") == 0.0

    def test_empty_error(self):
        assert score_c1_error_type("") == 0.0

    def test_stale_element(self):
        assert score_c1_error_type("stale element reference") == 0.3

    def test_waiting_for_locator(self):
        assert score_c1_error_type("waiting for getByRole('button')") == 0.3


# ---------------------------------------------------------------------------
# C2: DOM evidence
# ---------------------------------------------------------------------------

class TestC2DomEvidence:
    def test_no_dom(self):
        assert score_c2_dom_evidence("error", None, "locator_drift") == 0.0

    def test_dom_with_drift(self):
        dom = "<div><button>Place Order</button></div>"
        assert score_c2_dom_evidence("error", dom, "locator_drift") == 0.2

    def test_dom_with_defect(self):
        dom = "<div class='error'>500 Internal Server Error</div>"
        assert score_c2_dom_evidence("error", dom, "app_defect") == 0.2

    def test_dom_unknown(self):
        dom = "<div>Some content</div>"
        assert score_c2_dom_evidence("error", dom, "unknown") == 0.1


# ---------------------------------------------------------------------------
# C3: Historical pattern match
# ---------------------------------------------------------------------------

class TestC3HistoryMatch:
    def test_known_pattern(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure("timeout on submit button", "locator_drift", "healed", "/checkout")
        store.record_failure("timeout on submit button", "locator_drift", "healed", "/checkout")
        store.record_failure("timeout on submit button", "locator_drift", "healed", "/checkout")

        assert score_c3_history_match("timeout on submit button", store) == 0.2

    def test_seen_once(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure("rare error on login", "app_defect", "filed", "/login")

        assert score_c3_history_match("rare error on login", store) == 0.1

    def test_no_history(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        assert score_c3_history_match("completely new error", store) == 0.0


# ---------------------------------------------------------------------------
# C4: Human calibration alignment
# ---------------------------------------------------------------------------

class TestC4HumanCalibration:
    def test_humans_agree(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_human_decision("locator_drift", 0.8, "heal", "err1")
        store.record_human_decision("locator_drift", 0.7, "heal", "err2")
        store.record_human_decision("locator_drift", 0.9, "heal", "err3")

        assert score_c4_human_calibration("locator_drift", store) == 0.2

    def test_no_decisions(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        assert score_c4_human_calibration("locator_drift", store) == 0.1  # neutral

    def test_humans_disagree(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_human_decision("locator_drift", 0.6, "defect", "err1")
        store.record_human_decision("locator_drift", 0.5, "defect", "err2")
        store.record_human_decision("locator_drift", 0.7, "defect", "err3")

        result = score_c4_human_calibration("locator_drift", store)
        assert result <= 0.1  # humans override this classification


# ---------------------------------------------------------------------------
# C5: Consistency check
# ---------------------------------------------------------------------------

class TestC5Consistency:
    def test_all_strong(self):
        assert score_c5_consistency(0.2, 0.2, 0.2, 0.2) == 0.2

    def test_three_strong(self):
        assert score_c5_consistency(0.2, 0.2, 0.2, 0.0) == 0.2

    def test_two_strong(self):
        assert score_c5_consistency(0.2, 0.2, 0.0, 0.0) == 0.15

    def test_one_strong_one_weak(self):
        assert score_c5_consistency(0.2, 0.1, 0.0, 0.0) == 0.1

    def test_no_signals(self):
        assert score_c5_consistency(0.0, 0.0, 0.0, 0.0) == 0.0


# ---------------------------------------------------------------------------
# Anti-inflation guards
# ---------------------------------------------------------------------------

class TestGuards:
    def test_guard1_first_seen(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        score, guards = apply_guards(0.9, "brand new error", None, store)
        assert score <= 0.8
        assert any("G1" in g for g in guards)

    def test_guard1_not_applied_for_known(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure("known error", "drift", "healed", "/")
        score, guards = apply_guards(0.9, "known error", None, store)
        assert not any("G1" in g for g in guards)

    def test_guard3_no_dom(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure("known error", "drift", "healed", "/")
        score, guards = apply_guards(0.8, "known error", None, store)
        assert score <= 0.5
        assert any("G3" in g for g in guards)

    def test_guard4_timeout_no_dom(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure("TimeoutError on button", "drift", "healed", "/")
        score, guards = apply_guards(0.8, "TimeoutError on button", None, store)
        assert score <= 0.6
        assert any("G3" in g or "G4" in g for g in guards)

    def test_no_guards_when_score_below_caps(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        score, guards = apply_guards(0.3, "new error", None, store)
        assert score == 0.3
        assert guards == []

    def test_guard_with_dom_present(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure("known error", "drift", "healed", "/")
        dom = "<div>content</div>"
        score, guards = apply_guards(0.9, "known error", dom, store)
        # G3 should NOT fire (DOM is present)
        assert not any("G3" in g for g in guards)


# ---------------------------------------------------------------------------
# Full score_confidence
# ---------------------------------------------------------------------------

class TestScoreConfidence:
    def test_clear_drift(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        store.record_failure("selector-not-found button Submit", "locator_drift", "healed", "/checkout")
        store.record_failure("selector-not-found button Submit", "locator_drift", "healed", "/checkout")
        store.record_failure("selector-not-found button Submit", "locator_drift", "healed", "/checkout")

        breakdown = score_confidence(
            error="selector-not-found: button 'Submit'",
            failure_class="locator_drift",
            dom_snapshot="<div><button>Place Order</button></div>",
            memory=store,
        )
        assert breakdown.final_score >= 0.5
        assert breakdown.c1_error_type == 0.3
        assert breakdown.c2_dom_evidence == 0.2

    def test_ambiguous_timeout(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        breakdown = score_confidence(
            error="TimeoutError: Timeout 30000ms exceeded",
            failure_class="unknown",
            dom_snapshot=None,
            memory=store,
        )
        # Should be low — timeout, no DOM, no history
        assert breakdown.final_score <= 0.5

    def test_returns_breakdown_object(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        breakdown = score_confidence("error", "unknown", memory=store)
        assert isinstance(breakdown, ConfidenceBreakdown)
        assert 0.0 <= breakdown.final_score <= 1.0
        assert isinstance(breakdown.guards_applied, list)

    def test_to_dict(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        breakdown = score_confidence("error", "unknown", memory=store)
        d = breakdown.to_dict()
        assert "c1_error_type" in d
        assert "final_score" in d
        assert "guards_applied" in d

    def test_to_prompt_string(self, tmp_path):
        store = MemoryStore(memory_dir=tmp_path)
        breakdown = score_confidence("selector-not-found", "locator_drift", memory=store)
        s = breakdown.to_prompt_string()
        assert "C1 Error type signal" in s
        assert "Final score" in s

    def test_consistency_between_runs(self, tmp_path):
        """Same error scored twice should produce identical results."""
        store = MemoryStore(memory_dir=tmp_path)
        b1 = score_confidence("selector-not-found: button", "locator_drift", memory=store)
        b2 = score_confidence("selector-not-found: button", "locator_drift", memory=store)
        assert b1.final_score == b2.final_score
        assert b1.c1_error_type == b2.c1_error_type
