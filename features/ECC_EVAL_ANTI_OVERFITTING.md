# Build Spec: ECC Eval Anti-Overfitting Safeguards

## Mission

Ensure the ECC eval framework produces accurate, generalizable scores — not scores inflated by shortcuts that only work on the current golden dataset. Specifically, prevent the file backfill optimization from masking extraction failures on multi-file scenarios.

**Status:** PLANNED
**Priority:** High
**Depends on:** ECC Agent Evals (Phase 1-4 complete)

---

## Problem

The file backfill optimization (`len(code_files) == 1` → infer file from scenario context) correctly handles single-file scenarios but creates a risk:

1. **All 94 detection scenarios currently use single files** — the backfill fires on every scenario, meaning the extractor's file parsing is never truly tested
2. **If multi-file scenarios are added**, the backfill won't fire, and any extractor weaknesses will cause recall to drop suddenly
3. **Scores look inflated** — 100% recall may reflect the backfill working, not the extractor working

This is textbook overfitting: the system performs well on the current test set because of an optimization tailored to that set's structure.

---

## Safeguards

### 1. Multi-File Scenarios (Required)

Add multi-file scenarios to each detection agent's golden dataset where the backfill CANNOT fire. These test the extractor's real file-parsing ability.

| Agent | Current Scenarios | Multi-File to Add | Target |
|-------|-------------------|-------------------|--------|
| security-reviewer | 20 (all single-file) | 5 | 25 total, 20% multi-file |
| code-reviewer | 15 (all single-file) | 3 | 18 total, 17% multi-file |
| silent-failure-hunter | 15 (all single-file) | 3 | 18 total, 17% multi-file |
| python-reviewer | 12 (all single-file) | 2 | 14 total, 14% multi-file |
| typescript-reviewer | 12 (all single-file) | 2 | 14 total, 14% multi-file |
| fastapi-reviewer | 10 (all single-file) | 2 | 12 total, 17% multi-file |
| performance-optimizer | 10 (all single-file) | 2 | 12 total, 17% multi-file |

Multi-file scenario example:
```json
{
  "scenario_id": "sec_021_multi_file_auth_bypass",
  "code_files": {
    "api/routes.py": "samples/sec_021_routes.py",
    "api/middleware.py": "samples/sec_021_middleware.py",
    "models/user.py": "samples/sec_021_user.py"
  },
  "planted_issues": [
    {
      "issue_id": "VULN-021",
      "file": "api/routes.py",
      "line_range": [15, 15],
      "category": "auth_bypass"
    }
  ]
}
```

### 2. Separate Scoring: Backfilled vs Non-Backfilled

Track how many findings were backfilled vs naturally extracted in the scorecard:

```json
{
  "scores": {
    "recall": 0.95,
    "recall_without_backfill": 0.80,
    "backfill_rate": 0.60
  }
}
```

- `recall` — overall recall including backfill (current metric)
- `recall_without_backfill` — recall from findings where the extractor found the file on its own
- `backfill_rate` — percentage of matched findings that relied on backfill

Dashboard displays both. If `recall_without_backfill` is significantly lower than `recall`, the extractor needs improvement.

### 3. Backfill Decay Target

Set a target to reduce `backfill_rate` over time by improving the extractor:

| Milestone | Target Backfill Rate | Action |
|-----------|---------------------|--------|
| Current | ~60% (estimated) | Baseline |
| Phase 1 | < 40% | Improve extractor for Format B headers |
| Phase 2 | < 20% | Handle all known agent output formats |
| Phase 3 | < 10% | Backfill is a safety net, not a crutch |

### 4. Extractor Coverage Tests

Add unit tests that verify the extractor handles all known output formats WITHOUT backfill:

```python
class TestExtractorFormats:
    """Ensure extractor handles all agent output formats without backfill."""

    def test_format_a_labeled_file_line(self):
        """### Finding N / **File:** `x.py` / **Line:** N"""

    def test_format_b_severity_header_with_dash_line(self):
        """[CRITICAL] Title — Line N"""

    def test_format_c_inline_file_colon_line(self):
        """file.py:12"""

    def test_format_d_backtick_comma_line(self):
        """`file.py`, line 12"""

    def test_format_e_location_label(self):
        """Location:** `file.py`, line 12"""

    def test_format_f_finding_label(self):
        """**Finding:** description mentioning `file.py`"""

    def test_multi_file_correct_attribution(self):
        """Agent reviews 3 files, findings attributed to correct files."""
```

### 5. Golden Dataset Diversity Score

Track structural diversity of the golden dataset:

```json
{
  "dataset_health": {
    "total_scenarios": 25,
    "single_file_scenarios": 20,
    "multi_file_scenarios": 5,
    "unique_file_extensions": [".py", ".ts"],
    "avg_planted_issues_per_scenario": 1.4,
    "diversity_score": 0.72
  }
}
```

---

## Implementation Phases

### Phase 1: Add Multi-File Scenarios (Week 1)

| # | Task |
|---|------|
| 1 | Create 5 multi-file security-reviewer scenarios |
| 2 | Create 3 multi-file code-reviewer scenarios |
| 3 | Create 3 multi-file silent-failure-hunter scenarios |
| 4 | Run baselines with mixed dataset — compare recall with/without backfill |

### Phase 2: Separate Scoring (Week 2)

| # | Task |
|---|------|
| 1 | Track `backfill_count` in eval runner when backfill fires |
| 2 | Compute `recall_without_backfill` in scorecard |
| 3 | Add `backfill_rate` to dashboard card display |
| 4 | Add extractor format coverage unit tests |

### Phase 3: Extractor Hardening (Week 3)

| # | Task |
|---|------|
| 1 | Analyze multi-file scenario failures to identify missing extractor patterns |
| 2 | Add new extraction strategies for unhandled formats |
| 3 | Drive `backfill_rate` below 20% |
| 4 | Add remaining multi-file scenarios to other detection agents |

---

## Success Criteria

- [ ] All detection agents have at least 15% multi-file scenarios
- [ ] `recall_without_backfill` displayed on dashboard alongside `recall`
- [ ] `backfill_rate` tracked and trending downward
- [ ] Extractor unit tests cover all 7+ known output formats
- [ ] Multi-file scenario recall >= 70% without backfill
- [ ] No single-file-only shortcuts in the matching pipeline
