# Build Spec: Eval Agent for CampingWorld QA Automation

## Mission

Build an Eval Agent that creates thorough, automated evaluations for every agent in the CampingWorld QA Automation pipeline. The agent mirrors the skillset of an Anthropic Research Engineer (Model Evaluations) — converting abstract notions of "does this agent work well" into concrete, measurable metrics with regression detection.

---

## Agents Under Evaluation

| Agent / System | What It Does | Current Eval Coverage |
|-------|-------------|----------------------|
| **Design Reader** | Reads Figma designs → produces `ExpectedUI` spec | None |
| **Planner** | ACs + UI spec → `TestCase[]` plan | AC Coverage ≥80% (keyword fuzzy match) |
| **Generator** | Test plan → Playwright POM + spec files | Locator Quality ≥70% (semantic vs brittle) |
| **Executor** | Runs Playwright tests, parses results | None (execution is deterministic) |
| **Triage** | Classifies failures as `locator_drift`, `app_defect`, `unknown` | Triage Accuracy ≥75% (golden set) |
| **Healer** | Repairs broken locators in POMs | None |
| **Orchestrator** | Crawls site map, bulk-generates POM + tests | None |
| **Memory System** | Markdown-based learning across runs | None |
| **Human Review** | Routes uncertain triage decisions to humans for verdict | None |
| **Defect Report** | Files Jira tickets for confirmed app defects | None |
| **Intake (Jira)** | Extracts goal, ACs, app_url from Jira tickets | None |
| **Intake (Figma)** | Extracts Figma frame references for design reader | None |
| **Budget** | Tracks LLM token spend and enforces budget limits | None |
| **PR Gate** | Surface that blocks/passes PRs based on test results | None |
| **Observability** | Logs, metrics, and alerting for the pipeline | None |
| **Weekly Review** | Summarizes weekly pipeline health and trends | None |

---

## Eval Agent Architecture

### Core Responsibilities

1. **Design and execute evals** across all agents — reasoning quality, output correctness, safety, regression detection
2. **Build eval execution infrastructure** — automated, reproducible, CI-ready
3. **Own monitoring dashboards** — detect regressions across runs
4. **Debug anomalous results** — root-cause analysis when metrics shift
5. **Run experiments** — test prompt variations, model swaps, scaffolding changes

### Eval Agent Components

```
eval-agent/
├── evals/
│   ├── design_reader_eval.py    # Figma → ExpectedUI quality
│   ├── planner_eval.py          # AC coverage, test plan quality
│   ├── generator_eval.py        # Code quality, locator quality, compilability
│   ├── triage_eval.py           # Classification accuracy, confidence calibration
│   ├── healer_eval.py           # Fix success rate, assertion guardrail integrity
│   ├── orchestrator_eval.py     # Crawl completeness, POM validity
│   ├── memory_eval.py           # Recall accuracy, staleness detection
│   └── e2e_eval.py              # Full pipeline end-to-end
├── golden/
│   ├── design_reader/           # Known Figma designs → expected ExpectedUI outputs
│   ├── planner/                 # Known ACs → expected test plans
│   ├── generator/               # Known plans → expected POM/test structure
│   ├── triage/                  # Known failures → expected classifications
│   ├── healer/                  # Known broken locators → expected fixes
│   └── e2e/                     # Full pipeline golden scenarios
├── datasets/
│   ├── dom_snapshots/           # Real captured DOM snapshots for offline eval
│   ├── failure_scenarios/       # Curated failure cases (locator drift, app bugs, flaky)
│   ├── figma_mocks/             # Mock Figma responses
│   └── site_map_variants/       # Different site structures for robustness
├── metrics/
│   ├── scorecards.py            # Metric definitions and thresholds
│   ├── dashboard.py             # Results visualization and trend tracking
│   └── regression_detector.py   # Automatic regression detection across runs
├── runners/
│   ├── single_eval.py           # Run one eval in isolation
│   ├── full_suite.py            # Run all evals
│   └── comparison.py            # A/B compare two model/prompt configs
├── reports/
│   └── YYYY-MM-DD_HH-MM-SS/    # Timestamped eval results (same pattern as test-results)
└── config.py                    # Thresholds, model configs, dataset paths
```

---

## Eval Specifications Per Agent

### 1. Design Reader Eval

**What to measure:**
- **Element extraction completeness** — % of interactive elements in the Figma design correctly identified
- **Route mapping accuracy** — correct frame → route assignment
- **Schema conformance** — output validates against `ExpectedUI` Pydantic model
- **Hallucination rate** — elements in output that don't exist in the Figma design

**Golden dataset:** 5-10 Figma frames with manually annotated expected outputs

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| Element Recall | ≥85% | Annotated elements found in output / total annotated |
| Element Precision | ≥90% | Valid elements / total elements in output |
| Schema Valid | 100% | Pydantic parse success |
| Route Accuracy | ≥90% | Correct route / total frames |

---

### 2. Planner Eval

**What to measure:**
- **AC Coverage** — every acceptance criterion maps to at least one test case
- **Test plan completeness** — critical user flows covered (happy path, error states, edge cases)
- **Deduplication** — no redundant test cases
- **Priority ordering** — smoke tests tagged and ordered first
- **Memory integration** — volatile routes and flaky tests get appropriate tags

**Golden dataset:** 10 feature specs with manually written expected test plans

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| AC Coverage | ≥90% | Fuzzy keyword match of ACs in test steps. *(Raised from 0.80 in `run_eval.py` to push quality higher.)* |
| Flow Coverage | ≥80% | Critical flows checklist |
| Duplicate Rate | ≤5% | Semantic similarity between test cases |
| Priority Correctness | ≥85% | Smoke tags on correct tests |
| Memory Utilization | ≥70% | Volatile/flaky data reflected in plan |

---

### 3. Generator Eval

**What to measure:**
- **Compilability** — generated TypeScript compiles without errors
- **Locator quality** — semantic locators (getByRole, getByText, getByLabel) vs brittle (CSS class, ID, tag)
- **POM structure** — proper class structure, constructor, methods, exports
- **Test structure** — proper describe/test blocks, beforeEach, assertions
- **Import correctness** — imports resolve, no circular deps
- **Assertion coverage** — each test has at least one meaningful assertion

**Golden dataset:** 10 test plans → expected POM/test code quality scores

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| Compile Success | 100% | `tsc --noEmit`. *(NEW capability — not yet in code. The orchestrator's `pom_validator.py` and `test_validator.py` exist but are regex-based. This eval requires augmenting them with real TypeScript compilation.)* |
| Locator Quality | ≥80% | Semantic / total locators ratio. *(Raised from 0.70 in `run_eval.py` to push quality higher.)* |
| POM Validity | 100% | Has class, constructor, Page param, navigate(), exports |
| Test Validity | 100% | Has describe, test, beforeEach, ≥1 assertion per test |
| Assertion Density | ≥1.5/test | Total assertions / total tests |

---

### 4. Triage Eval

**What to measure:**
- **Classification accuracy** — correct `failure_class` assignment
- **Confidence calibration** — predicted confidence correlates with actual correctness
- **Rubric adherence** — all 5 criteria (C1-C5) scored, no inflation
- **Memory utilization** — similar past failures and human corrections influence decision
- **Speed** — classification latency

**Golden dataset:** 30+ failure scenarios with ground-truth labels:
- 10 locator drift (element renamed, moved, removed)
- 10 app defects (broken functionality, server errors, missing features)
- 10 unknown/ambiguous (network timeouts, race conditions, unclear root cause — the codebase maps `flaky` to `unknown`, so all non-deterministic and ambiguous cases use the `unknown` class)

> **Note:** The code uses 3 classes: `locator_drift`, `app_defect`, `unknown`. There is no separate `flaky` class — timing/flaky failures are classified as `unknown`.

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| Classification Accuracy | ≥85% | Correct class / total. *(Raised from 0.75 in `run_eval.py` to push quality higher.)* |
| Confidence Calibration | ECE ≤ 0.10 | Expected Calibration Error |
| Overconfidence Rate | ≤10% | Wrong classifications with confidence ≥ 0.75 |
| Memory Hit Rate | ≥60% | Similar past failure found when one exists |
| Latency p95 | ≤5s | 95th percentile response time |

---

### 5. Healer Eval

**What to measure:**
- **Fix success rate** — healed locator passes on re-run
- **Assertion guardrail** — NEVER modifies assertion lines (zero tolerance)
- **Minimal diff** — changes only what's broken, doesn't rewrite unrelated code
- **Memory fast-path** — known fixes applied without LLM call
- **Regression rate** — fix doesn't break other tests

**Golden dataset:** 20 broken locator scenarios with known correct fixes

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| Fix Success Rate | ≥75% | Fixed test passes / total heal attempts |
| Assertion Integrity | 100% | Zero assertion-line diffs (regex guardrail) |
| Diff Minimality | ≥90% | Changed lines are all locator/wait related |
| Cache Hit Rate | ≥30% | Known fixes applied without LLM call |
| Regression Rate | ≤5% | Other tests broken by fix / total fixes |

---

### 6. Orchestrator Eval

**What to measure:**
- **Crawl completeness** — all site map pages visited
- **Snapshot quality** — DOM snapshots contain interactive elements
- **POM validity** — generated POMs compile and have correct structure
- **Test validity** — generated tests compile and have assertions
- **Popup handling** — popups dismissed before snapshot
- **Dynamic URL resolution** — product/RV detail pages resolved correctly

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| Crawl Completion | ≥90% | Pages crawled / pages in site map |
| Snapshot Size | ≥100 chars | Non-trivial DOM captured |
| POM Compile | 100% | TypeScript compiles |
| Test Compile | 100% | TypeScript compiles |
| Popup Dismissed | 100% | No popup in snapshot text |

---

### 7. Memory System Eval

**What to measure:**
- **Recall accuracy** — correct past failure retrieved for similar new failure
- **Staleness detection** — entries older than 90 days pruned
- **Deduplication** — no duplicate failure patterns
- **Write integrity** — concurrent writes don't corrupt files
- **Learning effectiveness** — triage accuracy improves with more memory data

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| Recall@1 | ≥70% | Correct past failure returned by `find_similar_failure()`. *(Code returns a single match, not ranked results. To use Recall@3, the code would need updating to support ranked retrieval — this is a prerequisite.)* |
| Stale Entry Rate | ≤5% | Entries past TTL / total entries |
| Duplicate Rate | ≤3% | Semantic duplicates / total patterns |
| Write Integrity | 100% | Concurrent write stress test |
| Learning Curve | Positive slope | Triage accuracy vs memory size regression |

---

### 8. End-to-End Pipeline Eval

**What to measure:**
- **Full pipeline success** — feature spec → passing tests in single run
- **Self-healing success** — broken test → healed → green in ≤ MAX_ATTEMPTS
- **Defect detection rate** — real app bugs correctly identified and reported
- **False positive rate** — valid code flagged as defective
- **Total cycle time** — feature spec to first green run

**Golden dataset:** 5 end-to-end scenarios mixing new features, regressions, and locator drift

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| E2E Success Rate | ≥80% | Green run / total scenarios |
| Self-Heal Rate | ≥70% | Auto-healed / total locator failures |
| Defect Detection | ≥85% | True bugs caught / total bugs |
| False Positive Rate | ≤10% | False bug reports / total reports |
| Cycle Time p50 | ≤10 min | Median spec-to-green time |

---

### 9. Human Review Eval

**What to measure:**
- **Decision quality** — does the human review node correctly route `heal` vs `defect` verdicts?
- **Wait time** — how long does the system wait for a human response?
- **Decision consistency** — do similar failure patterns get consistent verdicts?
- **Calibration feedback loop effectiveness** — do human corrections improve future triage confidence?

**Golden dataset:** 15 failure scenarios with known correct verdicts (heal vs defect)

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| Decision Quality | ≥90% | Correct verdict (heal/defect) vs ground truth |
| Wait Time p95 | ≤30 min | 95th percentile time waiting for human response |
| Decision Consistency | ≥85% | Same verdict for semantically similar failures |
| Calibration Loop Effect | Positive | Triage confidence accuracy improves after N human corrections |

---

### 10. Defect Report Eval

**What to measure:**
- **Report quality** — does the Jira ticket contain actionable information (error, route, steps, screenshots)?
- **Jira filing success rate** — does the API call succeed and return a ticket key?
- **Deduplication accuracy** — are duplicate defects detected and linked rather than filed as new?
- **Fingerprint uniqueness** — does each distinct defect get a unique fingerprint?

**Golden dataset:** 10 defect scenarios (5 unique defects, 5 duplicates of existing defects)

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| Report Completeness | ≥90% | Required fields (error, route, steps, screenshots) present |
| Filing Success Rate | ≥95% | Jira API returns ticket key / total attempts |
| Dedup Accuracy | ≥85% | Correctly identified duplicates / total duplicates |
| Fingerprint Uniqueness | 100% | Distinct defects produce distinct fingerprints |

---

### 11. Intake Eval

**What to measure:**
- **AC extraction completeness (Jira)** — are all acceptance criteria extracted from Jira tickets?
- **Figma ref extraction accuracy** — are Figma file references correctly parsed and frames identified?
- **Field extraction (Jira)** — are goal, ACs, and app_url correctly extracted from various Jira ticket formats?
- **MCP response handling (Figma)** — are Figma node counts and frames correctly interpreted?

**Golden dataset:** 10 Jira tickets with manually annotated fields + 5 Figma file references with known frame counts

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| AC Extraction Recall | ≥90% | Extracted ACs / total ACs in ticket |
| AC Extraction Precision | ≥95% | Valid ACs / total extracted ACs |
| Figma Ref Accuracy | ≥95% | Correct file ref + frame IDs / total |
| Jira Field Coverage | ≥90% | goal + ACs + app_url extracted / total tickets with those fields |

---

### 12. Executor Eval

**What to measure:**
- **DOM snapshot capture** — does the executor return a usable DOM snapshot? (Currently returns `None` — this is a prerequisite)
- **Test file writing success** — are POM and test files written to disk correctly?
- **Playwright subprocess reliability** — does `npx playwright test` launch and return results consistently?
- **Result parsing accuracy** — are pass/fail results and failed case names parsed correctly from Playwright JSON output?

**Golden dataset:** 5 known test suites with expected pass/fail outcomes

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| DOM Snapshot Captured | 100% | Non-None, non-empty snapshot returned. *(PREREQUISITE: currently returns None — must be implemented before this eval can run.)* |
| File Write Success | 100% | Written files exist on disk and match expected content |
| Subprocess Reliability | ≥95% | Playwright process exits with parseable output / total runs |
| Result Parse Accuracy | ≥95% | Correctly parsed failed case names / total failed cases |

---

### 13. Budget Eval

**What to measure:**
- **Budget tracking accuracy** — does the budget system accurately track token spend across nodes?
- **Cost estimation vs actual** — does estimated cost match actual Claude API usage?
- **Budget exhaustion detection** — does the system correctly halt when budget is exceeded?

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| Tracking Accuracy | ≥99% | Tracked tokens vs actual tokens from API responses |
| Cost Estimation Error | ≤5% | |estimated - actual| / actual |
| Exhaustion Detection | 100% | System halts when budget exceeded / total budget breaches |

---

### 14. PR Gate Eval

**What to measure:**
- **Gate decision quality** — does the PR gate correctly block failing runs and pass green runs?
- **Confidence threshold correctness** — are borderline cases handled according to configured thresholds?
- **Test results summary accuracy** — does the gate surface accurate pass/fail counts?

**Golden dataset:** 10 PR scenarios (5 should pass, 5 should block) with known test outcomes

**Metrics:**
| Metric | Threshold | Method |
|--------|-----------|--------|
| Gate Decision Accuracy | ≥95% | Correct block/pass decision vs ground truth |
| Threshold Adherence | 100% | Borderline cases match configured threshold behavior |
| Summary Accuracy | 100% | Reported pass/fail counts match actual |

---

## Prerequisites

The following code changes are needed before all evals can run:

1. **Audit Trail must be built first (Phase AT1-AT4)** — evals depend on timing instrumentation, token tracking, and prompt versioning that the `@audit_node` decorator provides. No timing data is currently captured on any node.
2. **Executor must capture DOM snapshots** — `_run_playwright_tests()` currently returns `None` for `dom_snapshot`. This blocks the Executor eval (DOM Snapshot Captured metric) and degrades Triage eval (C2 DOM evidence scoring always gets 0.0 without a snapshot).
3. **Memory must support ranked retrieval for Recall@3** — `find_similar_failure()` returns a single match (`dict | None`). The Memory eval uses Recall@1 to match the current code. If ranked retrieval is desired, the code must be updated to return a ranked list.
4. **Triage does not have a `flaky` class** — the code uses 3 classes: `locator_drift`, `app_defect`, `unknown`. The golden dataset uses `unknown` for timing/flaky/ambiguous cases.
5. **Generator "Compile Success" requires `tsc`** — the existing `pom_validator.py` and `test_validator.py` in the orchestrator are regex-based. Real TypeScript compilation via `tsc --noEmit` is a new capability that must be added.

---

## Regression Detection System

### How It Works

1. Every eval run produces a **scorecard** — a JSON file with all metrics per agent
2. Scorecards are stored in `reports/YYYY-MM-DD_HH-MM-SS/scorecard.json`
3. The **regression detector** compares the latest scorecard against the previous N runs
4. Any metric that drops below threshold OR drops >10% from rolling average triggers an **alert**

### Alert Levels

| Level | Trigger | Action |
|-------|---------|--------|
| INFO | Metric improved >5% | Log only |
| WARN | Metric dropped 5-10% | Flag in dashboard |
| CRITICAL | Metric dropped >10% or below threshold | Block deployment, notify |

### Dashboard

A terminal-based dashboard (or HTML report similar to Playwright's) showing:
- Per-agent metric trends over time
- Current vs threshold vs historical average
- Failed eval details with root cause hints
- A/B comparison view for prompt/model experiments

---

## Implementation Plan

### Phase 1: Golden Dataset Creation (Week 1)
- Capture real DOM snapshots, failure scenarios, and Figma mocks
- Create ground-truth labels for triage classification
- Write expected outputs for planner and generator

### Phase 2: Individual Agent Evals (Week 2-3)
- Implement eval for each agent (planner, generator, triage, healer)
- Run baseline measurements
- Set thresholds based on current performance

### Phase 3: E2E Eval + Regression Detection (Week 4)
- Wire up end-to-end pipeline eval
- Build scorecard system and regression detector
- Create dashboard

### Phase 4: CI Integration + Experimentation (Week 5)
- Integrate evals into CI (run on every prompt/model change)
- Build A/B comparison runner for prompt experiments
- Document runbooks for debugging eval regressions

---

## CLI Interface

```bash
# Run all evals
eval-agent run

# Run specific agent eval
eval-agent run --agent triage
eval-agent run --agent healer

# Compare two configurations
eval-agent compare --baseline main --candidate feature-branch

# Show dashboard
eval-agent dashboard

# Generate regression report
eval-agent report --since 2026-08-01
```

---

## Key Design Principles

1. **Deterministic where possible** — use seeded inputs, not live site calls, for eval consistency
2. **Fast feedback** — individual agent evals complete in <2 minutes
3. **No eval gaming** — metrics measure downstream impact, not proxy signals
4. **Human-calibrated** — thresholds set from observed real-world performance, not arbitrary targets
5. **Composable** — run one agent's eval or the full suite
6. **Versioned golden data** — git-tracked, reviewed, updated when the site changes
7. **Offline-first** — evals run against captured snapshots, not live campingworld.com
