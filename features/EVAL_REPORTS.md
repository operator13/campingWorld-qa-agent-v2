# Feature: Eval Reports with Recommendations

> Every eval run generates a human-readable report with actionable recommendations — explaining what went wrong, why, and how to fix it.

**Status:** IMPLEMENTED
**Priority:** High
**Depends on:** Eval Agent (BUILD_SPEC_EVAL_AGENT.md), Audit Trail (AGENT_AUDIT_TRAIL.md)

---

## The Problem

The Eval Agent produces a JSON scorecard with accuracy numbers, but doesn't explain what went wrong or suggest next steps. An engineer looking at "Triage Accuracy: 20% — FAIL" has to manually dig through misses to understand the root cause.

## The Solution

A pure Python recommendations engine that pattern-matches on eval misses and generates prioritized, actionable recommendations. No LLM needed — deterministic rules.

---

## What Gets Generated

### 1. Console Output (CLI)

```
=== QA Agent · EVAL (triage) ===

Scenarios: 30 loaded, 0 skipped (expired)

Triage Accuracy:  20.0%  (threshold: 75.0%)  FAIL
  app_defect:     0.0%  (0/12)
  locator_drift:  0.0%  (0/10)
  unknown:        75.0%  (6/8)

Misses: 24 scenario(s)

Recommendations (4):

  [HIGH] locator_drift
    Finding: 10/10 locator_drift scenarios classify correctly but confidence
             averages 0.65 (needs >=0.75). The confidence rubric is capping
             scores too low.
    Action:  Option 1: Tune the confidence rubric in qa_agent/confidence.py
             to produce higher scores for locator_drift patterns.
             Option 2: Lower expected_confidence_min in golden data to ~0.65.

  [HIGH] unknown
    Finding: 2 scenario(s) expected 'unknown' but triage returned 'app_defect':
             unknown_js_error_ambiguous, unknown_hydration_error.
    Action:  Add clearer 'unknown' vs 'app_defect' disambiguation examples
             to the triage prompt in qa_agent/prompts/TRIAGE.md.

  [HIGH] overall
    Finding: Overall accuracy 20.0% is below threshold 75.0% (gap: 55.0%).
             24 of 30 scenarios missed.
    Action:  Address the confidence and classification issues above.

  [LOW] improvement
    Finding: 2 scenario(s) recovered since previous run.
    Action:  No action needed — this is positive progress.

Scorecard: eval-20260830-111601
Report:    qa_agent/eval/reports/ (JSON + Markdown)
Overall:   FAIL
```

### 2. JSON Scorecard (`qa_agent/eval/reports/triage-*.json`)

Recommendations embedded as a top-level key:

```json
{
  "eval_run_id": "eval-20260830-111601",
  "triage_accuracy": { ... },
  "recommendations": [
    {
      "priority": "high",
      "category": "locator_drift",
      "finding": "10/10 locator_drift scenarios classify correctly...",
      "action": "Option 1: Tune the confidence rubric..."
    }
  ]
}
```

### 3. Markdown Report (`qa_agent/eval/reports/triage-*.md`)

Full human-readable report with:
- Summary (run ID, timestamp, pass/fail)
- Accuracy breakdown by category (table)
- Regression status
- Recommendations (prioritized, with finding + action)
- Misses detail table (scenario, expected, got, confidence)

---

## Recommendation Rules

| Pattern | Detection | Priority |
|---------|-----------|----------|
| Confidence underrun (≥50% of category) | `got_class == expected_class` and `got_conf < expected_conf_min` | HIGH |
| Misclassification | `got_class != expected_class` | HIGH |
| Below threshold | `score < threshold` | HIGH |
| Category at 0% | `by_category[cat].score == 0` | HIGH |
| Major regression | `regression.severity == "major"` | HIGH |
| Minor regression | `regression.severity == "minor"` | MEDIUM |
| New failures | `regression.new_failures` not empty | MEDIUM |
| Recovered scenarios | `regression.recovered` not empty | LOW |
| All passing | No misses | LOW |

---

## Architecture

```
eval_runner.py
  └── score_triage_accuracy()     → accuracy dict with misses
  └── detect_regression()          → regression report
  └── generate_recommendations()   → list of recommendations (NEW)
  └── build_scorecard()            → scorecard + recommendations
  └── save_scorecard()             → JSON file
  └── format_report_markdown()     → Markdown file (NEW)
```

`recommendations.py` is pure Python — no LLM calls, no external dependencies, deterministic. It pattern-matches on misses and produces structured recommendations.

---

## Files

| File | Status |
|------|--------|
| `qa_agent/eval/recommendations.py` | IMPLEMENTED — recommendation engine + markdown formatter |
| `qa_agent/eval/eval_runner.py` | MODIFIED — calls recommendations, writes .md report |
| `qa_agent/cli.py` | MODIFIED — prints recommendations in console output |
| `tests/test_eval_agent.py` | MODIFIED — 8 new tests (35 total) |

## Tests

8 tests covering:
- Confidence underrun detection
- Misclassification detection
- Below-threshold recommendation
- Major regression recommendation
- All-passing recommendation
- Priority sorting
- Markdown report structure
- Empty recommendations handling
