"""Tests for ProgressTracker — JSON checkpoint."""

from __future__ import annotations

import json

import pytest

from qa_agent.orchestrator.progress import ProgressTracker


@pytest.fixture
def tracker(tmp_path):
    return ProgressTracker(path=tmp_path / "progress.json")


# ---------------------------------------------------------------------------
# Mark done
# ---------------------------------------------------------------------------

def test_mark_done(tracker):
    tracker.mark_done("Homepage")
    assert tracker.is_done("Homepage") is True


def test_is_done_false_for_unknown(tracker):
    assert tracker.is_done("Unknown Page") is False


# ---------------------------------------------------------------------------
# Mark failed
# ---------------------------------------------------------------------------

def test_mark_failed(tracker):
    tracker.mark_failed("Cart", "timeout error")
    assert tracker.is_done("Cart") is False
    summary = tracker.summary()
    assert "Cart" in summary["failed"]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def test_summary_categorizes(tracker):
    tracker.mark_done("Homepage")
    tracker.mark_done("Search")
    tracker.mark_failed("Cart", "error")
    summary = tracker.summary()
    assert set(summary["done"]) == {"Homepage", "Search"}
    assert summary["failed"] == ["Cart"]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_persists_to_disk(tmp_path):
    path = tmp_path / "progress.json"
    t1 = ProgressTracker(path=path)
    t1.mark_done("Homepage")

    # New tracker reads from disk
    t2 = ProgressTracker(path=path)
    assert t2.is_done("Homepage") is True


def test_handles_corrupt_file(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text("not valid json!!!")
    tracker = ProgressTracker(path=path)
    assert tracker.is_done("anything") is False


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def test_reset_clears_all(tracker):
    tracker.mark_done("Homepage")
    tracker.mark_done("Cart")
    tracker.reset()
    assert tracker.is_done("Homepage") is False
    assert tracker.is_done("Cart") is False


def test_reset_removes_file(tmp_path):
    path = tmp_path / "progress.json"
    tracker = ProgressTracker(path=path)
    tracker.mark_done("X")
    assert path.exists()
    tracker.reset()
    assert not path.exists()


# ---------------------------------------------------------------------------
# Resume flow
# ---------------------------------------------------------------------------

def test_resume_skips_done(tracker):
    """Simulates resume: done pages return True, pending return False."""
    tracker.mark_done("Homepage")
    tracker.mark_failed("Cart", "err")

    assert tracker.is_done("Homepage") is True   # skip
    assert tracker.is_done("Cart") is False       # retry
    assert tracker.is_done("Search") is False     # new
