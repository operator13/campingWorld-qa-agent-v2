# Feature: Retrospective Agent

> An agent that periodically analyzes triage reports, unhealed failures, and agent performance to recommend improvements to the Triage rubric, Healer strategies, and test configurations — closing the feedback loop so the system learns from its own failures.

**Status:** PLANNED
**Priority:** High
**Depends on:** Triage Agent, Healer Agent, Eval Agent, Audit Trail

---

## The Problem

The system detects failures, classifies them, attempts healing, and documents everything — but no agent reads the documented findings to improve future performance. Triage reports with full reasoning, confidence breakdowns, and not_healed_reasons accumulate in `health-reports/` without anyone analyzing them.

**Current feedback loops that exist:**
- Triage reads `FAILURES.md` for similar past failures → helps with repeat patterns
- Triage reads `HUMAN_DECISIONS.md` for calibration → helps with human-corrected patterns
- Healer reads `locators/` for known fixes → avoids repeated LLM calls
- Healer reads `TIMING_FIXES.md` for known timing fixes → same

**Feedback loops that are missing:**
- Nobody analyzes **why failures go unhealed** → rubric doesn't improve
- Nobody detects **recurring unhealed patterns** → same failures keep surfacing
- Nobody evaluates **whether Healer strategies are effective** → bad strategies persist
- Nobody identifies **systemic issues** → like "C2 is always 0.0 because we never capture DOM"
- Nobody recommends **config changes** → like "increase beforeEach timeout from 30s to 60s"

---

## The Solution

A **Retrospective Agent** that runs after every N test runs (or on-demand) and produces actionable recommendations by analyzing the accumulated data across triage reports, health reports, eval results, and memory files.

---

## What the Retrospective Agent Analyzes

### 1. Unhealed Failure Patterns

Scans all triage reports for failures that were not healed and identifies recurring patterns:

```
FINDING: "beforeEach timeout" failures occurred 5 times in the last 7 days
  - All classified as test_flake with confidence < 0.30
  - All on nav.spec.ts, product.spec.ts, cart.spec.ts
  - None healed — confidence too low due to missing DOM snapshot
  
RECOMMENDATION: Add beforeEach navigation timeout as a recognized
  flake pattern in confidence.py with C1 score 0.25 (currently 0.10).
  This would raise confidence above CONF_SURE for known slow-loading pages.
  
ALTERNATIVE: Increase Playwright navigation timeout from 30s to 60s
  in playwright.config.ts to reduce false timeouts on slow networks.
```

### 2. Confidence Rubric Gaps

Analyzes the confidence breakdown across all triage reports to find systematic scoring weaknesses:

```
FINDING: C2 (DOM evidence) is 0.00 in 78% of triage runs
  - DOM snapshots are rarely captured during test failures
  - This caps confidence at 0.50 via Guard G3 for many legitimate failures
  
RECOMMENDATION: Investigate why DOM snapshots aren't being captured.
  If Playwright doesn't provide them on navigation timeout, consider
  capturing a partial DOM before the timeout fires.

FINDING: C3 (historical match) gives 0.20 to failures seen 3+ times,
  but "beforeEach timeout" has been seen 5 times and still gets 0.00
  
ROOT CAUSE: The error normalization in find_similar_failure() doesn't
  match "beforeEach" timeouts because the URL in the error differs each run.
  
RECOMMENDATION: Normalize URLs in error signatures before matching.
```

### 3. Healer Effectiveness

Reviews healed vs unhealed outcomes to evaluate strategy performance:

```
FINDING: Healer timing fix Strategy A (waitFor before interaction) 
  succeeded 85% of the time, but Strategy D (networkidle) succeeded 0%
  
RECOMMENDATION: Deprioritize Strategy D in HEALER.md prompt.
  Network idle waits are unreliable on campingworld.com due to
  analytics scripts that never finish loading.

FINDING: 3 locator drift fixes were marked as failed after re-run
  - All used getByText() which broke again within 2 days
  
RECOMMENDATION: Add to HEALER.md: "Avoid getByText() for elements
  with dynamic text. Prefer getByTestId() or getByRole()."
```

### 4. Test Stability Trends

Analyzes `TEST_STABILITY.md` and health report history for deteriorating tests:

```
FINDING: cart.spec.ts "Top Picks section shows Add To Cart buttons"
  has failed 4 of the last 10 runs (40% flakiness)
  
RECOMMENDATION: This test depends on a recommendation API that
  returns empty results intermittently. Either:
  - Add a conditional skip when the carousel is empty
  - Increase waitFor timeout for the carousel section
  - Mark as known flaky and reduce its weight in health scoring

FINDING: rv-parts.spec.ts has failed every run for the last 3 days
  - Always "page renders a heading" — TimeoutError on navigation
  
RECOMMENDATION: The /rv-parts page may have been removed or redirected.
  Investigate whether the page still exists. If removed, delete the spec.
```

### 5. Cost Optimization

Reviews token usage across eval and triage runs:

```
FINDING: Triage agent uses 67K tokens per eval run — 55% of total cost
  - 35 scenarios × ~1,900 tokens average per scenario
  - C1 pattern matching could short-circuit 60% of scenarios without LLM
  
RECOMMENDATION: Add a fast-path in triage: if C1 score is 0.30 and
  error pattern is well-known (selector-not-found + "no element matching"),
  skip the LLM call and classify directly. Estimated savings: $0.20/run.
```

---

## Architecture

### Input Sources

| Source | What It Provides |
|--------|-----------------|
| `health-reports/*-triage.json` | Unhealed failures with reasoning, confidence breakdown, error |
| `health-reports/*.json` | Domain pass/fail history, health scores over time |
| `memory/FAILURES.md` | Known failure patterns and resolutions |
| `memory/TEST_STABILITY.md` | Per-test flakiness scores |
| `memory/TIMING_FIXES.md` | Timing fix attempts and success rates |
| `memory/HEALER_STATS.md` | Cache hit rate, LLM call count |
| `memory/locators/*.md` | Locator change history, fix success/failure |
| `qa_agent/eval/reports/*/` | Eval scores, token usage, regressions |
| `memory/HUMAN_DECISIONS.md` | Human overrides and calibration data |

### Output

The Retrospective Agent produces a **Retrospective Report** saved to `memory/RETROSPECTIVE.md` and `memory/retrospectives/{timestamp}.json`:

```markdown
# Retrospective Report — 2026-08-31

## Summary
- Analyzed: 14 triage reports, 52 health reports, 4 eval runs
- Findings: 7 (3 high, 2 medium, 2 low)
- Recommendations: 9

## High Priority Findings
...

## Medium Priority Findings
...

## Recommendations
1. [HIGH] Add beforeEach timeout to flake patterns (confidence.py)
2. [HIGH] Increase navigation timeout to 60s (playwright.config.ts)
3. [MEDIUM] Deprioritize Strategy D in Healer prompt
4. [MEDIUM] Normalize URLs in error signature matching
...
```

### Agent Design

```python
async def retrospective(
    lookback_days: int = 7,
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    """Analyze recent triage, health, and eval data to produce improvement recommendations."""
    
    # 1. Load all data sources
    triage_reports = load_recent_triage_reports(lookback_days)
    health_reports = load_recent_health_reports(lookback_days)
    eval_reports = load_recent_eval_reports()
    stability = load_test_stability()
    healer_stats = load_healer_stats()
    timing_fixes = load_timing_fixes()
    
    # 2. Analyze each dimension
    unhealed_patterns = analyze_unhealed_failures(triage_reports)
    rubric_gaps = analyze_confidence_gaps(triage_reports)
    healer_effectiveness = analyze_healer_outcomes(triage_reports, timing_fixes, healer_stats)
    stability_trends = analyze_test_stability(stability, health_reports)
    cost_analysis = analyze_cost_trends(eval_reports)
    
    # 3. Generate recommendations (LLM-assisted)
    findings = unhealed_patterns + rubric_gaps + healer_effectiveness + stability_trends + cost_analysis
    recommendations = await generate_recommendations(findings)
    
    # 4. Save report
    report = build_retrospective_report(findings, recommendations)
    save_retrospective(report)
    
    return report
```

### LLM vs Rule-Based

| Analysis | Approach | Why |
|----------|----------|-----|
| Unhealed pattern detection | Rule-based | Count occurrences, group by error pattern — no LLM needed |
| Confidence gap analysis | Rule-based | Statistical analysis of C1-C5 distributions |
| Healer effectiveness | Rule-based | Success/failure rates from TIMING_FIXES.md |
| Test stability trends | Rule-based | Flakiness scores and pass/fail ratios |
| Cost analysis | Rule-based | Sum tokens from eval reports |
| Recommendation generation | LLM-assisted | Synthesize findings into actionable, context-aware advice |
| Root cause analysis | LLM-assisted | Connect patterns across data sources to identify systemic issues |

Most analysis is rule-based (cheap, fast). The LLM is only used for the final synthesis step — turning raw findings into human-readable recommendations with context.

---

## How Recommendations Get Applied

### Automatic (Future — with human approval)

The Retrospective Agent could propose code changes:
```
RECOMMENDATION: Add beforeEach timeout to flake patterns
PROPOSED CHANGE: confidence.py line 92 — add to _FLAKE_ERROR_PATTERNS:
  re.compile(r"beforeEach.*Timeout", re.I)
  
[APPROVE] [REJECT] [MODIFY]
```

User clicks APPROVE → the change is applied, committed, and the next triage run benefits.

### Manual (Phase 1)

The report surfaces recommendations that a human reads and decides whether to act on. The dashboard could show a "RETROSPECTIVE" section with the latest findings.

### Memory Integration

Recommendations feed back into the agent memory system:
- Approved recommendations → recorded in `memory/LESSONS.md`
- Rejected recommendations → recorded so the agent doesn't suggest them again
- Applied changes → tracked in `memory/RETROSPECTIVE.md` for future reference

---

## Dashboard Integration

### Retrospective Card

A new section on the dashboard between Agent Evaluation and Test Runner:

```
┌──────────────────────────────────────────────────────────────────────┐
│  RETROSPECTIVE                        Last run: 2 hours ago  [▶ RUN]│
│                                                                      │
│  7 findings  •  3 high priority  •  9 recommendations               │
│                                                                      │
│  ⚡ [HIGH] Add beforeEach timeout to flake patterns                 │
│  ⚡ [HIGH] Increase navigation timeout to 60s                       │
│  ⚡ [HIGH] rv-parts.spec.ts may need removal (failing 3 days)       │
│  ◉ [MED]  Deprioritize Healer Strategy D                           │
│  ◉ [MED]  Normalize URLs in error matching                         │
│                                                                      │
│  [VIEW FULL REPORT]                                                  │
└──────────────────────────────────────────────────────────────────────┘
```

### Trigger Options

- **Manual**: Click RUN on the dashboard or `qa-agent retrospective`
- **Automatic**: After every N test runs (configurable, default: every 10 runs)
- **Scheduled**: Weekly cron job alongside the weekly self-review

---

## Files to Modify

| File | Change |
|------|--------|
| `qa_agent/retrospective.py` | New — core analysis engine |
| `qa_agent/cli.py` | Add `qa-agent retrospective` command |
| `qa_agent/dashboard/server.py` | Add retrospective API endpoints |
| `qa_agent/dashboard/static/app.js` | Retrospective card rendering |
| `qa_agent/dashboard/static/styles.css` | Retrospective card styling |
| `qa_agent/dashboard/static/index.html` | Retrospective section |

### Files to Create

| File | Purpose |
|------|---------|
| `qa_agent/retrospective.py` | Retrospective Agent — analysis + recommendation engine |
| `memory/RETROSPECTIVE.md` | Latest retrospective findings + applied changes |
| `memory/retrospectives/` | Timestamped retrospective report history (JSON) |

---

## Build Phases

### Phase RA1 — Data Collection + Rule-Based Analysis (~1 day)

| # | Task |
|---|------|
| 1 | Load and parse recent triage reports (unhealed failures, confidence breakdowns) |
| 2 | Analyze unhealed failure patterns — group by error type, spec file, frequency |
| 3 | Analyze confidence rubric gaps — C1-C5 distribution, guards fired frequency |
| 4 | Analyze healer effectiveness — success rates by strategy, fix durability |
| 5 | Analyze test stability trends — deteriorating tests, persistent failures |
| 6 | Analyze cost trends — token usage per agent over time |

### Phase RA2 — LLM-Assisted Recommendations (~0.5 day)

| # | Task |
|---|------|
| 1 | Feed findings to Claude for synthesis into actionable recommendations |
| 2 | Prioritize: HIGH (immediate action needed), MEDIUM (should address), LOW (nice to have) |
| 3 | Include specific file/line references for code changes |
| 4 | Generate human-readable retrospective report (markdown + JSON) |

### Phase RA3 — CLI + Storage (~0.5 day)

| # | Task |
|---|------|
| 1 | `qa-agent retrospective` CLI command |
| 2 | Save reports to `memory/RETROSPECTIVE.md` and `memory/retrospectives/{timestamp}.json` |
| 3 | Auto-trigger after configurable N test runs |
| 4 | Notify dashboard via WebSocket when retrospective completes |

### Phase RA4 — Dashboard Integration (~0.5 day)

| # | Task |
|---|------|
| 1 | Retrospective card on dashboard with findings summary |
| 2 | RUN button to trigger retrospective from browser |
| 3 | VIEW FULL REPORT opens detailed findings panel |
| 4 | Real-time update via `retrospective:complete` WebSocket event |

### Phase RA5 — Auto-Apply Recommendations (Future)

| # | Task |
|---|------|
| 1 | Propose code diffs for each recommendation |
| 2 | APPROVE/REJECT buttons on dashboard |
| 3 | Auto-apply approved changes, commit, re-run affected evals |
| 4 | Track applied vs rejected in memory for learning |

---

## Relationship to Other Agents

```
                    ┌──────────────────┐
                    │  RETROSPECTIVE   │
                    │     AGENT        │
                    └──────┬───────────┘
                           │ reads
          ┌────────────────┼────────────────────┐
          ▼                ▼                    ▼
   ┌─────────────┐  ┌───────────┐  ┌──────────────────┐
   │  Triage     │  │  Health   │  │  Eval Reports    │
   │  Reports    │  │  Reports  │  │  + Audit Trail   │
   └──────┬──────┘  └───────────┘  └──────────────────┘
          │
          │ recommends improvements to
          ▼
   ┌─────────────┐  ┌───────────┐  ┌──────────────────┐
   │  Triage     │  │  Healer   │  │  Test Config     │
   │  Rubric     │  │  Prompts  │  │  + Stability     │
   └─────────────┘  └───────────┘  └──────────────────┘
```

The Retrospective Agent is the **meta-agent** — it doesn't fix tests or classify failures. It improves the agents that do.

---

## Success Criteria

1. Retrospective analyzes triage reports and identifies recurring unhealed patterns
2. Produces actionable recommendations with specific file/line references
3. Detects confidence rubric gaps (e.g., "C2 always 0.0") with root cause
4. Identifies ineffective Healer strategies with success rate data
5. Flags deteriorating tests before they become persistent failures
6. Surfaces cost optimization opportunities with estimated savings
7. Report is human-readable (markdown) and machine-parseable (JSON)
8. Dashboard shows findings summary with priority levels
9. Can be triggered from CLI, dashboard, or automatically after N runs
10. Recommendations feed back into agent memory when applied
