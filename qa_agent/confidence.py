"""Confidence rubric — formal 5-criteria scoring for Triage classification.

Replaces the loose "rate your confidence 0-1" with a structured, auditable
rubric. Each criterion scores 0.0-0.2, total 0.0-1.0. Anti-inflation guards
cap the score in specific scenarios to prevent overconfidence.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from qa_agent.memory import MemoryStore, normalize_error

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceBreakdown:
    """Detailed breakdown of a confidence score."""

    c1_error_type: float = 0.0
    c2_dom_evidence: float = 0.0
    c3_history_match: float = 0.0
    c4_human_calibration: float = 0.0
    c5_consistency: float = 0.0
    raw_score: float = 0.0
    guards_applied: list[str] = field(default_factory=list)
    final_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "c1_error_type": self.c1_error_type,
            "c2_dom_evidence": self.c2_dom_evidence,
            "c3_history_match": self.c3_history_match,
            "c4_human_calibration": self.c4_human_calibration,
            "c5_consistency": self.c5_consistency,
            "raw_score": self.raw_score,
            "guards_applied": self.guards_applied,
            "final_score": self.final_score,
        }

    def to_prompt_string(self) -> str:
        """Format as a readable string for prompt injection."""
        lines = [
            "Confidence breakdown:",
            f"  C1 Error type signal:     {self.c1_error_type:.1f}/0.2",
            f"  C2 DOM evidence:          {self.c2_dom_evidence:.1f}/0.2",
            f"  C3 Historical match:      {self.c3_history_match:.1f}/0.2",
            f"  C4 Human calibration:     {self.c4_human_calibration:.1f}/0.2",
            f"  C5 Consistency check:     {self.c5_consistency:.1f}/0.2",
            f"  Raw score:                {self.raw_score:.2f}",
        ]
        if self.guards_applied:
            lines.append(f"  Guards applied:           {', '.join(self.guards_applied)}")
        lines.append(f"  Final score:              {self.final_score:.2f}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Criterion scorers
# ---------------------------------------------------------------------------

# C1: Error type signal patterns
_DRIFT_ERROR_PATTERNS = [
    re.compile(r"selector[- ]not[- ]found", re.I),
    re.compile(r"locator\.click.*Timeout", re.I),
    re.compile(r"waiting for getBy", re.I),
    re.compile(r"element not found", re.I),
    re.compile(r"stale element", re.I),
]

_DEFECT_ERROR_PATTERNS = [
    re.compile(r"AssertionError", re.I),
    re.compile(r"assert.*expected.*got", re.I),
    re.compile(r"ERR_FAILED\s*[345]\d\d", re.I),       # 3xx/4xx/5xx HTTP errors
    re.compile(r"HTTP\s*[345]\d\d", re.I),
    re.compile(r"Internal Server Error", re.I),
    re.compile(r"console\.error", re.I),
    re.compile(r"Unhandled.*Exception", re.I),
    re.compile(r"TypeError:", re.I),                    # JS runtime errors
    re.compile(r"ReferenceError:", re.I),               # undefined variable errors
    re.compile(r"Cannot read properties of null", re.I),
    re.compile(r"ERR_TOO_MANY_REDIRECTS", re.I),        # redirect loops
    re.compile(r"Forbidden", re.I),                      # 403
    re.compile(r"Service Unavailable", re.I),            # 503
    re.compile(r"Hydration failed", re.I),               # SSR mismatch
]

_FLAKE_ERROR_PATTERNS = [
    re.compile(r"scrollIntoViewIfNeeded.*Timeout", re.I),
    re.compile(r"locator\.(click|fill|type)\s*:.*Timeout.*exceeded", re.I),
    re.compile(r"element is not visible", re.I),
    re.compile(r"element is not stable", re.I),
    re.compile(r"element is outside of the viewport", re.I),
]

# Assertion failures that look like timing issues — content hasn't loaded yet
# e.g., count() returns 0 because async content hasn't rendered
_ASYNC_CONTENT_ASSERTION_PATTERNS = [
    re.compile(r"toBeGreaterThan.*Expected:.*>.*0.*Received:\s*0", re.S | re.I),
    re.compile(r"toHaveCount.*Expected:.*\d+.*Received:\s*0", re.S | re.I),
    re.compile(r"\.count\(\).*expect.*Received:\s*0", re.S | re.I),
]

_TIMEOUT_PATTERN = re.compile(r"TimeoutError|Timeout.*exceeded", re.I)
_NO_ELEMENT_PATTERN = re.compile(r"no element matching|0 elements", re.I)


def detect_failure_class_hint(error: str) -> str:
    """Suggest a failure class based on error patterns alone.

    Returns 'locator_drift', 'app_defect', 'test_flake', or 'unknown'.
    Used by Triage to seed the LLM's classification.
    """
    if not error:
        return "unknown"
    drift_match = any(p.search(error) for p in _DRIFT_ERROR_PATTERNS)
    defect_match = any(p.search(error) for p in _DEFECT_ERROR_PATTERNS)
    flake_match = any(p.search(error) for p in _FLAKE_ERROR_PATTERNS)
    has_no_element = bool(_NO_ELEMENT_PATTERN.search(error))

    # Check if this looks like an assertion failure caused by async content not loading
    async_content_flake = any(p.search(error) for p in _ASYNC_CONTENT_ASSERTION_PATTERNS)
    if async_content_flake:
        return "test_flake"

    if defect_match and not drift_match:
        return "app_defect"
    if drift_match and has_no_element:
        return "locator_drift"
    if flake_match and not has_no_element:
        return "test_flake"
    if drift_match:
        return "locator_drift"
    return "unknown"


def score_c1_error_type(error: str) -> float:
    """C1: Error type signal (0.0-0.3).

    Strong unambiguous signals get 0.3 (raised from 0.2) to ensure
    clear-cut drift/defect patterns reach the CONF_SURE threshold.
    """
    if not error:
        return 0.0

    drift_match = any(p.search(error) for p in _DRIFT_ERROR_PATTERNS)
    defect_match = any(p.search(error) for p in _DEFECT_ERROR_PATTERNS)
    flake_match = any(p.search(error) for p in _FLAKE_ERROR_PATTERNS)
    async_content_flake = any(p.search(error) for p in _ASYNC_CONTENT_ASSERTION_PATTERNS)
    is_timeout = bool(_TIMEOUT_PATTERN.search(error))
    has_no_element = bool(_NO_ELEMENT_PATTERN.search(error))

    # Async content assertion (count=0 when content hasn't loaded) → flake
    if async_content_flake:
        return 0.3

    if drift_match and defect_match:
        return 0.1  # conflicting signals — ambiguous
    # Flake check first — if a specific interaction method timed out without
    # "no element matching", it's a flake, not drift
    if flake_match and not has_no_element and not defect_match:
        return 0.3  # strong flake signal — interaction timeout, element likely exists

    if drift_match and not defect_match:
        if has_no_element:
            return 0.3  # strong confirmed drift — element truly absent
        if is_timeout:
            return 0.15  # timeout on a locator — likely drift but not certain
        return 0.3  # non-timeout drift signal (stale element, selector-not-found)
    if defect_match and not drift_match:
        return 0.3  # strong unambiguous defect signal
    if is_timeout:
        return 0.1  # generic timeout — ambiguous
    return 0.0


def score_c2_dom_evidence(
    error: str,
    dom_snapshot: str | None,
    failure_class: str,
) -> float:
    """C2: DOM evidence (0.0-0.2)."""
    if not dom_snapshot:
        return 0.0

    # Try to extract what element was expected
    # If failure_class is drift and we can see a similar element in DOM → 0.2
    # If failure_class is defect and element is completely absent → 0.2
    # Partial match → 0.1

    dom_lower = dom_snapshot.lower()
    has_interactive = any(tag in dom_lower for tag in ["<button", "<input", "<a ", "<select", "role="])
    has_error_state = any(s in dom_lower for s in ["error", "500", "404", "crash", "exception"])

    if failure_class == "locator_drift":
        if has_interactive:
            return 0.2  # DOM has interactive elements — likely renamed, not removed
        return 0.1  # DOM exists but no clear evidence of the element
    elif failure_class == "app_defect":
        if has_error_state:
            return 0.2  # DOM shows error state
        if not has_interactive:
            return 0.2  # DOM is empty/broken — element completely absent
        return 0.1
    elif failure_class == "test_flake":
        if has_interactive:
            return 0.2  # element IS in DOM — confirms flake, not drift
        return 0.1

    return 0.1


def score_c3_history_match(
    error: str,
    memory: MemoryStore,
) -> float:
    """C3: Historical pattern match (0.0-0.2)."""
    similar = memory.find_similar_failure(error)

    if similar:
        occurrences = similar.get("occurrences", 1)
        if occurrences >= 3:
            return 0.2  # well-known pattern
        return 0.1  # seen before but not many times

    return 0.0


def score_c4_human_calibration(
    failure_class: str,
    memory: MemoryStore,
) -> float:
    """C4: Human calibration alignment (0.0-0.2)."""
    decisions = memory.get_triage_calibration(n=20)
    if not decisions:
        return 0.1  # no data — neutral

    # Only count decisions where the triage guess matches the class we're scoring
    expected_verdict = "heal" if failure_class in ("locator_drift", "test_flake") else "defect"

    agreements = 0
    disagreements = 0

    for d in decisions:
        # Only consider decisions where Triage made the same classification
        if d.get("triage_guess") != failure_class:
            continue
        if d.get("human_verdict") == expected_verdict:
            agreements += 1
        else:
            disagreements += 1

    if agreements > disagreements and agreements >= 2:
        return 0.2
    if disagreements > agreements and disagreements >= 2:
        return 0.0  # humans disagree with this classification
    return 0.1


def score_c5_consistency(
    c1: float,
    c2: float,
    c3: float,
    c4: float,
) -> float:
    """C5: Consistency check (0.0-0.2).

    How many independent signals agree? A very strong C1 (≥0.25)
    counts as 2 strong signals because the error pattern alone is
    highly diagnostic.
    """
    # A strong C1 (unambiguous error pattern) counts double
    effective_signals = [c1, c2, c3, c4]
    strong_signals = sum(1 for c in effective_signals if c >= 0.15)
    if c1 >= 0.25:
        strong_signals += 1  # bonus for very clear error pattern

    weak_signals = sum(1 for c in effective_signals if 0.05 < c < 0.15)
    no_signals = sum(1 for c in effective_signals if c <= 0.05)

    if strong_signals >= 3:
        return 0.2
    if strong_signals >= 2:
        return 0.15
    if strong_signals >= 1 and weak_signals >= 1:
        return 0.1
    if no_signals >= 3:
        return 0.0
    return 0.05


# ---------------------------------------------------------------------------
# Anti-inflation guards
# ---------------------------------------------------------------------------

def apply_guards(
    raw_score: float,
    error: str,
    dom_snapshot: str | None,
    memory: MemoryStore,
) -> tuple[float, list[str]]:
    """Apply anti-inflation guards that cap the score."""
    score = raw_score
    guards: list[str] = []

    # Guard 1: First time seeing this error → cap at 0.8
    # Raised from 0.7 to allow clear-cut patterns (strong C1) to pass
    # CONF_SURE threshold (0.75) even on first encounter.
    similar = memory.find_similar_failure(error)
    if not similar:
        if score > 0.8:
            score = 0.8
            guards.append("G1: first-seen pattern → capped at 0.8")

    # Guard 2: Humans have overridden 2+ times → cap at 0.6
    decisions = memory.get_triage_calibration(n=20)
    normalized = normalize_error(error)
    norm_words = set(normalized.lower().split())
    override_count = 0
    for d in decisions:
        d_norm = normalize_error(d.get("error_summary", ""))
        d_words = set(d_norm.lower().split())
        # Word-level matching: require >50% overlap with at least 3 words
        if not norm_words or not d_words:
            continue
        intersection = norm_words & d_words
        smaller = min(len(norm_words), len(d_words))
        if smaller >= 3 and len(intersection) / smaller >= 0.5:
            guess = d.get("triage_guess", "")
            verdict = d.get("human_verdict", "")
            is_agree = (guess == "locator_drift" and verdict == "heal") or \
                       (guess == "app_defect" and verdict == "defect")
            if not is_agree:
                override_count += 1
    if override_count >= 2:
        if score > 0.6:
            score = 0.6
            guards.append(f"G2: {override_count} human overrides → capped at 0.6")

    # Guard 3: No DOM snapshot → cap at 0.5
    # Relaxed: skip G3 when C1 is strong (≥0.25) because the error pattern
    # alone is sufficient evidence (e.g., assertion errors don't need DOM)
    c1_score = score_c1_error_type(error)
    if not dom_snapshot and c1_score < 0.25:
        if score > 0.5:
            score = 0.5
            guards.append("G3: no DOM snapshot → capped at 0.5")

    # Guard 4: TimeoutError alone (no DOM) → cap at 0.6
    # Only applies if G3 hasn't already capped lower
    # Relaxed: skip G4 when flake patterns are strong (C1 >= 0.3) — timing
    # flakes are legitimately diagnosed from the error pattern alone
    if _TIMEOUT_PATTERN.search(error) and not dom_snapshot:
        flake_match = any(p.search(error) for p in _FLAKE_ERROR_PATTERNS)
        if flake_match and c1_score >= 0.25:
            pass  # Strong flake signal — don't cap
        elif score > 0.6 and not any("G3" in g for g in guards):
            score = 0.6
            guards.append("G4: timeout without DOM → capped at 0.6")

    return round(score, 2), guards


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def score_confidence(
    error: str,
    failure_class: str,
    dom_snapshot: str | None = None,
    memory: MemoryStore | None = None,
) -> ConfidenceBreakdown:
    """Score confidence using the 5-criteria rubric + anti-inflation guards.

    Returns a ConfidenceBreakdown with per-criterion scores, guards applied,
    and the final capped score.
    """
    if memory is None:
        memory = MemoryStore()

    c1 = score_c1_error_type(error)
    c2 = score_c2_dom_evidence(error, dom_snapshot, failure_class)
    c3 = score_c3_history_match(error, memory)
    c4 = score_c4_human_calibration(failure_class, memory)
    c5 = score_c5_consistency(c1, c2, c3, c4)

    raw = round(c1 + c2 + c3 + c4 + c5, 2)
    final, guards = apply_guards(raw, error, dom_snapshot, memory)

    breakdown = ConfidenceBreakdown(
        c1_error_type=c1,
        c2_dom_evidence=c2,
        c3_history_match=c3,
        c4_human_calibration=c4,
        c5_consistency=c5,
        raw_score=raw,
        guards_applied=guards,
        final_score=final,
    )

    logger.info(
        "Confidence rubric: raw=%.2f final=%.2f guards=%s",
        raw, final, guards or "none",
    )

    return breakdown


def build_rubric_prompt_context() -> str:
    """Build the rubric context for injection into the Triage system prompt."""
    rubric_path = _get_rubric_path()
    if rubric_path.exists():
        return rubric_path.read_text()
    return ""


def _get_rubric_path() -> "Path":
    from pathlib import Path
    return Path(__file__).resolve().parent.parent / "memory" / "CONFIDENCE_RUBRIC.md"
