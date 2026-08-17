"""Regression tests for pre-mortem pass 3 fixes.

Each test targets a specific issue that was found and fixed.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from qa_agent.memory import MemoryStore
from qa_agent.nodes.metrics import MetricsDB


# ---------------------------------------------------------------------------
# Fix 1: _write_locked Windows fallback doesn't crash
# ---------------------------------------------------------------------------

class TestWriteLockedFallback:
    def test_write_locked_works_without_fcntl(self, tmp_path):
        """_write_locked falls back gracefully when fcntl is unavailable."""
        store = MemoryStore(memory_dir=tmp_path)
        filepath = tmp_path / "test.md"

        # Simulate Windows by making fcntl import fail
        with patch.dict("sys.modules", {"fcntl": None}):
            import importlib
            # The fallback should write without crashing
            MemoryStore._write_locked(filepath, "test content")

        assert filepath.exists()
        assert filepath.read_text() == "test content"

    def test_append_locked_works_without_fcntl(self, tmp_path):
        """_append_locked falls back gracefully when fcntl is unavailable."""
        filepath = tmp_path / "test.md"
        filepath.write_text("line1\n")

        with patch.dict("sys.modules", {"fcntl": None}):
            MemoryStore._append_locked(filepath, "line2\n")

        assert "line2" in filepath.read_text()


# ---------------------------------------------------------------------------
# Fix 2: clear_pattern_scoreboard actually persists
# ---------------------------------------------------------------------------

class TestClearPatternScoreboard:
    def test_clears_and_persists(self, tmp_path):
        """clear_pattern_scoreboard writes the cleaned content to disk."""
        store = MemoryStore(memory_dir=tmp_path)
        filepath = tmp_path / "LESSONS.md"
        filepath.write_text(
            "# Lessons Learned\n\n"
            "## Pattern Scoreboard\n\n"
            "| Pattern | Occurrences | Success rate | Best strategy |\n"
            "|---------|-------------|-------------|---------------|\n"
            "| Button rename | 5 | 100% | getByTestId |\n"
            "| Testid change | 3 | 75% | getByRole |\n\n"
            "## Route Insights\n"
        )

        store.clear_pattern_scoreboard()

        content = filepath.read_text()
        assert "| Pattern |" in content  # header preserved
        assert "|---" in content  # separator preserved
        assert "Button rename" not in content  # data rows removed
        assert "Testid change" not in content
        assert "## Route Insights" in content  # other sections preserved


# ---------------------------------------------------------------------------
# Fix 5-7: TOCTOU methods use _read_modify_write
# ---------------------------------------------------------------------------

class TestAtomicOperations:
    def test_record_locator_change_atomic(self, tmp_path):
        """record_locator_change uses atomic read-modify-write."""
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "old1", "new1", "reason1")
        store.record_locator_change("/checkout", "btn", "old2", "new2", "reason2")

        history = store.get_locator_history("/checkout", "btn")
        assert len(history) == 2

    def test_mark_fix_failed_atomic(self, tmp_path):
        """mark_fix_failed uses atomic read-modify-write."""
        store = MemoryStore(memory_dir=tmp_path)
        store.record_locator_change("/checkout", "btn", "old", "new", "reason", success=True)
        store.mark_fix_failed("/checkout", "btn", "old")

        assert store.get_known_fix("/checkout", "btn", "old") is None

    def test_increment_route_changes_atomic(self, tmp_path):
        """increment_route_changes uses atomic read-modify-write."""
        store = MemoryStore(memory_dir=tmp_path)
        store.update_route("/checkout", testids=["a"])
        store.increment_route_changes("/checkout")
        store.increment_route_changes("/checkout")
        store.increment_route_changes("/checkout")

        info = store.get_route_info("/checkout")
        assert info["changes"] == 3

    def test_record_healer_event_atomic(self, tmp_path):
        """record_healer_event uses atomic read-modify-write."""
        store = MemoryStore(memory_dir=tmp_path)
        store.record_healer_event("cache_hit")
        store.record_healer_event("cache_hit")
        store.record_healer_event("llm_call")

        rate = store.get_healer_cache_hit_rate()
        assert round(rate, 2) == 0.67  # 2/3


# ---------------------------------------------------------------------------
# Fix 8: MetricsDB mark_triage_correctness uses locking
# ---------------------------------------------------------------------------

class TestMetricsDBLocking:
    def test_mark_correctness_persists(self, tmp_path):
        """mark_triage_correctness writes correctly."""
        db = MetricsDB(db_path=tmp_path)
        run_id = db.record_run(
            goal="t", route="/", passed=False,
            failed_cases=["tc-1"], failure_class="drift",
            confidence=0.8, attempts=0, fingerprint=None, outcome="failed",
        )
        t_id = db.record_triage_call(run_id, "drift", 0.8)
        db.mark_triage_correctness(t_id, True)

        stats = db.compute_triage_accuracy()
        assert stats["total_audited"] == 1
        assert stats["correct"] == 1


# ---------------------------------------------------------------------------
# Fix 9: _append_row_with_id generates unique IDs
# ---------------------------------------------------------------------------

class TestUniqueIDs:
    def test_sequential_ids(self, tmp_path):
        """Multiple record_run calls produce sequential IDs."""
        db = MetricsDB(db_path=tmp_path)
        id1 = db.record_run(goal="t1", route="/", passed=True, failed_cases=[], failure_class=None, confidence=0.0, attempts=0, fingerprint=None, outcome="pass")
        id2 = db.record_run(goal="t2", route="/", passed=True, failed_cases=[], failure_class=None, confidence=0.0, attempts=0, fingerprint=None, outcome="pass")
        id3 = db.record_run(goal="t3", route="/", passed=True, failed_cases=[], failure_class=None, confidence=0.0, attempts=0, fingerprint=None, outcome="pass")

        assert id1 == 1
        assert id2 == 2
        assert id3 == 3

    def test_triage_ids_sequential(self, tmp_path):
        """Multiple record_triage_call produce sequential IDs."""
        db = MetricsDB(db_path=tmp_path)
        run_id = db.record_run(goal="t", route="/", passed=False, failed_cases=["tc-1"], failure_class="drift", confidence=0.8, attempts=0, fingerprint=None, outcome="failed")
        t1 = db.record_triage_call(run_id, "drift", 0.8)
        t2 = db.record_triage_call(run_id, "defect", 0.9)

        assert t1 == 1
        assert t2 == 2


# ---------------------------------------------------------------------------
# Fix 10: verify_unverified_fixes updates in place (no duplicates)
# ---------------------------------------------------------------------------

class TestVerifyFixes:
    def test_verify_updates_in_place(self, tmp_path):
        """verify_unverified_fixes changes success:no to success:yes without duplicates."""
        store = MemoryStore(memory_dir=tmp_path)
        # Record unverified fix
        store.record_locator_change("/checkout", "btn", "old", "new", "reason", success=False)

        # Verify it's not returned as known fix (success=no)
        assert store.get_known_fix("/checkout", "btn", "old") is None

        # Verify the fix
        store.verify_unverified_fixes("/checkout")

        # Now it should be found
        assert store.get_known_fix("/checkout", "btn", "old") == "new"

        # Should not have duplicates — only 1 entry
        history = store.get_locator_history("/checkout", "btn")
        assert len(history) == 1
        assert history[0]["success"] is True


# ---------------------------------------------------------------------------
# Fix 15: write_weekly_review uses locked append
# ---------------------------------------------------------------------------

class TestWeeklyReviewLocking:
    def test_write_review_persists(self, tmp_path):
        """write_weekly_review writes content correctly."""
        from qa_agent.weekly_review import write_weekly_review

        review = {
            "date": "2026-08-17",
            "grade": "B",
            "markdown": "## Week of 2026-08-17\n\nTest content\n",
        }
        write_weekly_review(review, memory_dir=tmp_path)

        filepath = tmp_path / "WEEKLY_REVIEW.md"
        assert filepath.exists()
        content = filepath.read_text()
        assert "2026-08-17" in content
        assert "Test content" in content


# ---------------------------------------------------------------------------
# Fix 20: Guard G2 uses word-level matching
# ---------------------------------------------------------------------------

class TestGuardG2WordMatching:
    def test_g2_does_not_fire_on_short_mismatch(self, tmp_path):
        """G2 doesn't falsely fire when error summaries are too short to match."""
        from qa_agent.confidence import apply_guards

        store = MemoryStore(memory_dir=tmp_path)
        # Record a decision with a very short error summary
        store.record_human_decision("drift", 0.6, "defect", "Error")
        store.record_human_decision("drift", 0.5, "defect", "Error")

        # G2 should NOT fire because "Error" is too short (< 3 words)
        score, guards = apply_guards(0.9, "Error on checkout submit button", None, store)
        assert not any("G2" in g for g in guards)


# ---------------------------------------------------------------------------
# Fix 22: clear_auto_generated_insights removes only auto entries
# ---------------------------------------------------------------------------

class TestClearAutoInsights:
    def test_preserves_manual_entries(self, tmp_path):
        """clear_auto_generated_insights only removes auto-generated entries."""
        store = MemoryStore(memory_dir=tmp_path)
        filepath = tmp_path / "LESSONS.md"
        filepath.write_text(
            "# Lessons Learned\n\n"
            "## Route Insights\n\n"
            "### /checkout\n"
            "- **2026-08-17:** Manual lesson entered by human\n"
            "- **2026-08-17:** Auto insight *(source: auto-generated)*\n"
            "\n## Decision Reflections\n"
        )

        store.clear_auto_generated_insights()

        content = filepath.read_text()
        assert "Manual lesson" in content
        assert "auto-generated" not in content


# ---------------------------------------------------------------------------
# Fix 13: Stale docstring
# ---------------------------------------------------------------------------

class TestDocstring:
    def test_no_sqlite_reference_in_memory_docstring(self):
        """memory.py docstring doesn't reference SQLite anymore."""
        import qa_agent.memory as mem
        assert "SQLite" not in (mem.__doc__ or "")
