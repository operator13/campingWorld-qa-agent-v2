# Feature: Eval Observability — Tracing & Experiment Comparison

> Add full LLM execution tracing and experiment comparison to the eval system — either via LangSmith integration or built in-house. Enables "did this change make the agent better?" with visual diffs.

**Status:** PLANNED
**Priority:** Medium
**Depends on:** Agent Evaluation System, Audit Trail, QA Command Center Dashboard

---

## The Problem

Our eval system scores agents and detects regressions, but lacks two critical observability capabilities:

1. **Full LLM tracing** — We track total tokens/cost per eval run, but can't see individual LLM calls inside each scenario. When a triage scenario scores wrong, we can't inspect the actual prompt, response, latency, or reasoning chain.

2. **Experiment comparison** — We detect "score dropped 3%" but can't show side-by-side what changed. Did the same scenario flip from pass to fail? Did a prompt change cause it? Which specific scenarios regressed?

---

## Current State vs What's Missing

| Capability | We Already Have | What's Missing |
|---|---|---|
| **Golden datasets** | 35 triage, 10 generator, 15 healer, 8 planner scenarios | Dataset versioning, UI to manage/edit scenarios |
| **Scoring** | Custom scorers per agent | LLM-as-judge, pairwise comparison, built-in scorers |
| **Regression detection** | Compare vs previous run, 2% threshold | Side-by-side experiment comparison with visual diffs |
| **Tracing** | Partial — audit trail tracks tokens/cost | Full execution traces with every LLM call, latency, token breakdown |
| **Human review** | Spec'd (Human Review Notifications) | Built-in annotation queues, inline annotation |
| **Dashboard** | Cyberpunk dashboard with real-time scores | Heat maps, experiment tables, score visualization |
| **Cost tracking** | Cumulative odometer per agent | Per-scenario cost breakdown, integrated into traces |

---

## Two Approaches

### Option A: LangSmith Integration

Integrate [LangSmith](https://docs.langchain.com/langsmith/evaluation-concepts) as an observability layer alongside our existing eval system.

### Option B: Build In-House

Build tracing and experiment comparison directly into our dashboard and eval runner.

---

## Option A: LangSmith Integration

### What LangSmith Provides

**Offline Evaluators:**
- Run agents against curated datasets, capture outputs + evaluator scores + traces
- Compare versions side-by-side to catch regressions before shipping
- LLM-as-judge scoring alongside our custom scorers

**Datasets:**
- Collections of inputs with expected outputs
- Version control — track changes to golden scenarios over time
- Web UI to browse, add, edit, and delete scenarios

**Experiments:**
- Capture agent outputs, scores, and traces for a dataset run
- Compare experiments across different code versions
- Heat maps showing which scenarios improved/regressed
- Latency and cost breakdown per scenario

**Tracing:**
- Full execution trace for every LLM call
- Input prompt, output response, token count, latency
- Nested traces for multi-step agent flows (triage → healer)
- Trace visualization in LangSmith UI

### Implementation

```python
# In eval_runner.py — add LangSmith tracing
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "ls_..."
os.environ["LANGCHAIN_PROJECT"] = "qa-automation-evals"

# LangSmith automatically traces all ChatAnthropic calls
# No code changes needed in agent nodes — tracing is automatic
# via langchain-anthropic integration
```

```python
# Dataset management
from langsmith import Client
client = Client()

# Upload golden scenarios as a LangSmith dataset
dataset = client.create_dataset("triage-golden-v1")
for scenario in triage_scenarios:
    client.create_example(
        inputs={"error": scenario["error"], "dom": scenario.get("dom_snippet")},
        outputs={"expected_class": scenario["expected_class"]},
        dataset_id=dataset.id,
    )
```

```python
# Run experiment
from langsmith.evaluation import evaluate

results = evaluate(
    lambda inputs: triage(build_state(inputs)),
    data="triage-golden-v1",
    evaluators=[accuracy_evaluator, confidence_evaluator],
    experiment_prefix="triage-v2.1",
)
```

### Pros
- Tracing is automatic (zero code changes in agent nodes)
- Experiment comparison UI is built-in and polished
- Dataset versioning out of the box
- LLM-as-judge evaluators ready to use
- Human annotation queues for review

### Cons
- Third-party dependency — data leaves our system
- Monthly cost for LangSmith ($0 free tier, $39/seat developer, custom enterprise)
- Duplicate dashboard — LangSmith UI + our cyberpunk dashboard
- Not integrated with our approval mechanism (Retrospective Agent)
- Vendor lock-in on evaluation workflow

### Files to Modify (Option A)

| File | Change |
|------|--------|
| `qa_agent/eval/eval_runner.py` | Add LangSmith tracing env vars, dataset upload, experiment tracking |
| `qa_agent/config.py` | Add LANGSMITH_API_KEY, LANGSMITH_PROJECT config |
| `requirements.txt` / `pyproject.toml` | Add `langsmith` dependency |

---

## Option B: Build In-House

Build tracing and experiment comparison directly into our existing system.

### What We'd Build

#### 1. Full LLM Tracing

Capture every LLM call's full context during eval runs:

```json
{
  "trace_id": "eval-triage-20260903-001",
  "scenario": "locator_drift_button_renamed",
  "agent": "triage",
  "calls": [
    {
      "call_id": 1,
      "model": "claude-sonnet-4-6",
      "input_prompt": "A test just failed. Analyze the failure...\n## Error\n```\nTimeoutError: locator.click...",
      "input_tokens": 1842,
      "output_response": "{\"failure_class\": \"locator_drift\", \"confidence\": 0.85, \"reasoning\": \"...\"}",
      "output_tokens": 156,
      "latency_ms": 2340,
      "cost_usd": 0.0078,
      "timestamp": "2026-09-03T18:15:42Z"
    }
  ],
  "result": {
    "failure_class": "locator_drift",
    "confidence": 0.85,
    "correct": true
  }
}
```

Stored in `qa_agent/eval/traces/{agent}/{run_id}/` as JSON files.

#### 2. Experiment Comparison

Compare two eval runs side-by-side:

```
EXPERIMENT COMPARISON: triage eval-20260902 vs eval-20260903

Overall: 85.7% → 82.9% (▼ 2.8%)

SCENARIOS THAT CHANGED:
┌──────────────────────────────────┬──────────┬──────────┬────────┐
│ Scenario                         │ Run A    │ Run B    │ Change │
├──────────────────────────────────┼──────────┼──────────┼────────┤
│ flake_scroll_into_view_timeout   │ ✓ pass   │ ✓ pass   │ —      │
│ unknown_generic_timeout_no_dom   │ ✗ miss   │ ✓ pass   │ ▲ FIX  │
│ locator_drift_testid_changed     │ ✓ pass   │ ✗ miss   │ ▼ REG  │
│ app_defect_assertion_value       │ ✓ pass   │ ✓ pass   │ —      │
└──────────────────────────────────┴──────────┴──────────┴────────┘

REGRESSIONS (1):
  locator_drift_testid_changed:
    Run A: classified as locator_drift (correct), confidence 0.82
    Run B: classified as test_flake (wrong), confidence 0.71
    Root cause: New flake pattern matched too broadly

IMPROVEMENTS (1):
  unknown_generic_timeout_no_dom:
    Run A: classified as test_flake (wrong)
    Run B: classified as unknown (correct)
```

#### 3. Dashboard Integration

Add an "Experiments" tab or section to the dashboard:

```
┌──────────────────────────────────────────────────────────────────────┐
│  EXPERIMENT HISTORY                                                  │
│                                                                      │
│  Run ID            Date        Score   Δ       Regressions  Fixes   │
│  eval-20260903-b   Sep 3 18:15  82.9%  ▼ 2.8%    1           1     │
│  eval-20260903-a   Sep 3 14:28  85.7%  ─ 0.0%    0           0     │
│  eval-20260902     Sep 2 22:19  85.7%  ▲ 2.8%    0           2     │
│  eval-20260901     Sep 1 15:30  82.9%  ─ 0.0%    0           0     │
│                                                                      │
│  Click any two rows to compare                                       │
│                                        [COMPARE SELECTED]            │
│                                                                      │
│  ┌── Comparison View ─────────────────────────────────────────────┐  │
│  │ eval-20260903-b vs eval-20260903-a                             │  │
│  │                                                                 │  │
│  │ ▼ locator_drift_testid_changed: PASS → FAIL                   │  │
│  │   Before: locator_drift (0.82)                                 │  │
│  │   After:  test_flake (0.71)                                    │  │
│  │   [View Trace A] [View Trace B]                                │  │
│  │                                                                 │  │
│  │ ▲ unknown_generic_timeout_no_dom: FAIL → PASS                  │  │
│  │   Before: test_flake (0.50)                                    │  │
│  │   After:  unknown (0.30)                                       │  │
│  │   [View Trace A] [View Trace B]                                │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

#### 4. Trace Viewer

Click "View Trace" to see the full LLM call:

```
┌── Trace: triage eval-20260903-b / locator_drift_testid_changed ──────┐
│                                                                       │
│  Model: claude-sonnet-4-6                                            │
│  Latency: 2.34s                                                      │
│  Tokens: 1,842 in / 156 out                                         │
│  Cost: $0.0078                                                       │
│                                                                       │
│  ── Input Prompt ──────────────────────────────────────────────────  │
│  A test just failed. Analyze the failure and classify it.            │
│                                                                       │
│  ## Error message                                                     │
│  ```                                                                  │
│  TimeoutError: page.locator: Timeout 30000ms exceeded.               │
│  Call log:                                                            │
│    - waiting for getByTestId('add-to-cart-btn')                      │
│    - no element matching getByTestId('add-to-cart-btn')              │
│  ```                                                                  │
│  ...                                                                  │
│                                                                       │
│  ── Output Response ───────────────────────────────────────────────  │
│  {                                                                    │
│    "failure_class": "test_flake",                                    │
│    "confidence": 0.71,                                               │
│    "reasoning": "Timeout on element lookup, no DOM..."               │
│  }                                                                    │
│                                                                       │
│  ── Evaluation ────────────────────────────────────────────────────  │
│  Expected: locator_drift                                              │
│  Got: test_flake ✗                                                   │
│  Confidence expected min: 0.75                                       │
│  Confidence got: 0.71 ✗                                              │
└───────────────────────────────────────────────────────────────────────┘
```

#### 5. Experiment Results Table (LangSmith-Style)

An interactive data table showing every scenario in an eval run — inspired by LangSmith's experiment view. Heat map coloring, sortable columns, expandable rows.

**Full Dashboard Visual:**

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  EXPERIMENT RESULTS — Triage eval-20260903-182843                                        │
│                                                                                          │
│  [Compact] [Full] [Diff]    Agent: [Triage ▾]    [✓ Heat Map] [⊞ Columns]  [+ Compare] │
│                                                                                          │
│  ┌───────────────────────┬─────────────┬──────────────┬──────────┬──────┬──────┬───────┐ │
│  │ Scenario              │ Expected    │ Got          │ Accuracy │ Conf │ Lat  │Tokens │ │
│  │                       │             │              │          │      │      │       │ │
│  ├───────────────────────┼─────────────┼──────────────┼──────────┼──────┼──────┼───────┤ │
│  │ drift_button_renamed  │ loc_drift   │ loc_drift    │ ██ 1.00  │ 0.85 │ 2.3s │ 1,842 │ │
│  │ drift_testid_changed  │ loc_drift   │ loc_drift    │ ██ 1.00  │ 0.82 │ 2.1s │ 1,756 │ │
│  │ drift_label_text      │ loc_drift   │ loc_drift    │ ██ 1.00  │ 0.88 │ 2.4s │ 1,901 │ │
│  │ defect_assertion_val  │ app_defect  │ app_defect   │ ██ 1.00  │ 0.91 │ 1.9s │ 1,623 │ │
│  │ defect_http_500       │ app_defect  │ app_defect   │ ██ 1.00  │ 0.87 │ 2.0s │ 1,712 │ │
│  │ flake_scroll_timeout  │ test_flake  │ test_flake   │ ██ 1.00  │ 0.50 │ 2.2s │ 1,845 │ │
│  │ flake_click_timeout   │ test_flake  │ test_flake   │ ██ 1.00  │ 0.52 │ 2.1s │ 1,798 │ │
│  │ unknown_generic_to..  │ unknown     │ test_flake   │ ░░ 0.00  │ 0.50 │ 2.5s │ 1,934 │ │
│  │ unknown_ci_env_to..   │ unknown     │ test_flake   │ ░░ 0.00  │ 0.45 │ 2.3s │ 1,867 │ │
│  │ unknown_element_det.. │ unknown     │ test_flake   │ ░░ 0.00  │ 0.05 │ 2.0s │ 1,654 │ │
│  │ ...                   │             │              │          │      │      │       │ │
│  └───────────────────────┴─────────────┴──────────────┴──────────┴──────┴──────┴───────┘ │
│                                                                                          │
│  Summary: 30/35 correct (85.7%)  │  Avg latency: 2.2s  │  Total tokens: 67,518          │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Column Definitions:**

| Column | Data Source | Heat Map Color |
|--------|-----------|---------------|
| **Scenario** | Golden scenario name (clickable → expands row with full details) | — |
| **Expected** | `expected_class` from golden scenario | — |
| **Got** | Agent's actual `failure_class` output | Green if matches expected, red if mismatch |
| **Accuracy** | 1.0 if correct, 0.0 if wrong | Green (1.0) → Red (0.0) gradient |
| **Conf** | Agent's confidence score | Green (≥0.75) → Yellow (0.5-0.74) → Red (<0.5) |
| **Lat** | Per-scenario LLM call latency | Green (<2s) → Yellow (2-5s) → Red (>5s) |
| **Tokens** | Input + output tokens for this scenario | — (informational) |

**Per-Agent Column Variants:**

| Agent | Columns |
|-------|---------|
| **Triage** | Scenario, Expected Class, Got Class, Accuracy, Confidence, C1-C5 Breakdown, Latency, Tokens |
| **Planner** | Scenario, Goal, AC Coverage, Plan Quality, Test Count, Latency, Tokens |
| **Generator** | Scenario, Locator Quality, POM Validity, Test Validity, Import Correctness, Latency, Tokens |
| **Healer** | Scenario, Fix Type, Fix Present, Assertions Preserved, No Hard Waits, Latency, Tokens |

**View Modes:**

| Mode | What It Shows |
|------|--------------|
| **Compact** | One row per scenario — score columns only, no details |
| **Full** | Expandable rows — click to see input error, LLM response, reasoning |
| **Diff** | Two experiments side-by-side — highlight cells that changed between runs |

**Expanded Row (click a scenario):**

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  ▼ unknown_generic_timeout_no_dom                              ░░ MISS           │
│                                                                                   │
│  ── Input ──────────────────────────────────────────────────────────────────────  │
│  Error: TimeoutError: page.waitForNavigation: Timeout 30000ms exceeded.          │
│                                                                                   │
│  ── Expected ───────────────────────────────────────────────────────────────────  │
│  Class: unknown    Confidence min: 0.0                                           │
│                                                                                   │
│  ── Got ────────────────────────────────────────────────────────────────────────  │
│  Class: test_flake    Confidence: 0.50                                           │
│  Reasoning: "Navigation timeout pattern matches flake — but no DOM evidence..." │
│                                                                                   │
│  ── Confidence Breakdown ───────────────────────────────────────────────────────  │
│  C1: 0.10  C2: 0.00  C3: 0.20  C4: 0.10  C5: 0.10  Raw: 0.50  Guards: none    │
│                                                                                   │
│  ── Trace ──────────────────────────────────────────────────────────────────────  │
│  Model: claude-sonnet-4-6    Latency: 2.5s    Tokens: 1,934    Cost: $0.0081    │
│  [View Full Trace]                                                                │
└───────────────────────────────────────────────────────────────────────────────────┘
```

**Diff View (comparing two experiments):**

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  DIFF: eval-20260903-a vs eval-20260903-b                                                │
│                                                                                          │
│  ┌───────────────────────┬──────────────────────┬──────────────────────┬────────────────┐ │
│  │ Scenario              │ Run A (Sep 3 14:28)  │ Run B (Sep 3 18:15)  │ Change        │ │
│  ├───────────────────────┼──────────────────────┼──────────────────────┼────────────────┤ │
│  │ drift_testid_changed  │ ██ loc_drift  0.82   │ ░░ test_flake 0.71  │ ▼ REGRESSION  │ │
│  │ unknown_generic_to..  │ ░░ test_flake 0.50   │ ██ unknown    0.30  │ ▲ IMPROVEMENT │ │
│  │ flake_fill_timeout    │ ██ test_flake 0.70   │ ██ test_flake 0.72  │ ─ stable      │ │
│  │ ...                   │ (28 stable scenarios) │                     │ ─ stable      │ │
│  └───────────────────────┴──────────────────────┴──────────────────────┴────────────────┘ │
│                                                                                          │
│  Filter: [All] [▼ Regressions only] [▲ Improvements only] [─ Changed only]             │
│                                                                                          │
│  Summary: 1 regression, 1 improvement, 33 stable                                        │
│           Score: 85.7% → 82.9% (▼ 2.8%)                                                │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Cyberpunk Styling:**

- Dark glass background matching existing dashboard cards
- Heat map: neon green (1.0) → amber (0.5) → neon red (0.0)
- Expanded rows: darker inset background with monospace code blocks
- Regression cells: red glow border pulse
- Improvement cells: green glow
- Sortable column headers with cyan arrow indicators
- Sticky header row for scrolling through 35+ scenarios

**Mobile (iPhone):**

- Table scrolls horizontally with fixed first column (scenario name)
- Compact mode only (no Full/Diff on mobile)
- Tap row to expand details instead of click

### Pros
- No third-party dependency — all data stays local
- Integrated into our cyberpunk dashboard
- Works with our approval mechanism (Retrospective Agent)
- No additional cost beyond LLM API calls
- Full control over trace format and visualization
- Git-tracked traces for history

### Cons
- More engineering effort to build
- No LLM-as-judge built-in (would need to build)
- No dataset versioning UI (edit JSON files manually)
- Trace visualization less polished than LangSmith

### Files to Modify/Create (Option B)

| File | Change |
|------|--------|
| `qa_agent/eval/eval_runner.py` | Capture per-scenario traces during eval |
| `qa_agent/eval/tracer.py` | **New** — trace capture and storage |
| `qa_agent/eval/experiment_compare.py` | **New** — compare two eval runs |
| `qa_agent/dashboard/server.py` | Add experiment history + comparison API endpoints |
| `qa_agent/dashboard/static/app.js` | Experiment history table, comparison view, trace viewer |
| `qa_agent/dashboard/static/styles.css` | Experiment/trace viewer styling |
| `qa_agent/dashboard/static/index.html` | Experiment section |

---

## Recommendation

**Start with Option B (in-house)** for these reasons:

1. **We already have 80% of the infrastructure** — eval runner, audit trail, dashboard, WebSocket updates
2. **Tracing is the main gap** — just needs per-scenario LLM call capture, which is a small addition to `eval_runner.py`
3. **Experiment comparison is data diffing** — compare two JSON scorecards, highlight changes
4. **No vendor dependency** — stays in our control, integrates with Retrospective Agent
5. **Cost** — free vs LangSmith subscription

**Consider Option A later** if:
- We need LLM-as-judge evaluation (using Claude to evaluate Claude)
- We need dataset versioning UI (managing 68+ scenarios gets unwieldy)
- Team grows and multiple people need to review eval results
- We want production monitoring (online evaluation), not just offline eval

---

## Build Phases (Option B — In-House)

> Pre-mortem findings from [PRE_MORTEM_EVAL_OBSERVABILITY.md](PRE_MORTEM_EVAL_OBSERVABILITY.md) are integrated into each phase below. Each task that addresses a pre-mortem issue is marked with `[PM#N]`.

### Phase EO1 — Per-Scenario Tracing (~1 day)

**Critical architectural decision:** Do NOT hook into `AuditStore._current_node_llm_calls` — it's class-level shared state that cross-contaminates across concurrent scenarios. Build an independent per-scenario capture mechanism.

| # | Task | Pre-Mortem |
|---|------|-----------|
| 1 | Create `qa_agent/eval/tracer.py` using `contextvars.ContextVar` for per-asyncio-task trace isolation — each concurrent scenario gets its own trace buffer | [PM#1, PM#15] |
| 2 | Capture tokens directly from `response.usage_metadata` (including `cache_read_input_tokens` and `cache_creation_input_tokens` for accurate cost) — never rely on AuditStore's shared accumulators | [PM#2, PM#10] |
| 3 | Capture the FULL message list (SystemMessage + HumanMessage) in each trace, not just the human message — system prompt changes are often the cause of regressions | [PM#5] |
| 4 | Capture the prompt BEFORE making the LLM call, so timeout/error scenarios still have the input recorded. Record exception message + stack trace for failed calls. Differentiate: pre-call error, call timeout, post-call parse error | [PM#9] |
| 5 | Bypass the `AUDIT_RAW` environment gate — the tracer captures prompts/responses independently via its own path, not through `_consume_at3_context()` | [PM#4] |
| 6 | Add `qa_agent/eval/traces/` to `.gitignore` — NEVER git-track trace files. Implement retention policy: keep last 20 runs per agent, auto-delete older traces | [PM#3, PM#11] |
| 7 | Sanitize trace data before storing — run prompts through `sanitizer.py` to strip PII from DOM snapshots and error messages. Trace files are unencrypted on disk | [PM#12] |
| 8 | Store traces in `qa_agent/eval/traces/{agent}/{run_id}.json` with per-call `purpose` field for multi-call agents (generator: "pom_generation", "test_generation"; healer: "locator_fix", "timing_fix") | [PM#8] |
| 9 | Use `asyncio.Lock` around progress counter increments to prevent duplicate progress numbers on dashboard | [PM#14] |
| 10 | Handle interrupted evals: write traces in batch after all scenarios complete, OR mark partial runs with `"complete": false, "scenarios_expected": N, "scenarios_completed": M` metadata | [PM#18] |
| 11 | Each trace includes: scenario name, agent, run_id, model, full input prompt (system + human), full output response (raw + parsed), input_tokens, output_tokens, cache_read_tokens, latency_ms, cost_usd, purpose, error (if any) | — |
| 12 | Run full eval suite — verify traces captured for all 68 scenarios with no cross-contamination between concurrent scenarios | — |

### Phase EO2 — Experiment Comparison Engine (~0.5 day)

| # | Task | Pre-Mortem |
|---|------|-----------|
| 1 | Create `qa_agent/eval/experiment_compare.py` — diff two eval scorecards | — |
| 2 | Identify: regressions (pass→fail), improvements (fail→pass), stable, new (added scenario), removed (deleted scenario) | [PM#6] |
| 3 | Use stable scenario IDs (not just names) for matching. Warn when comparing runs with different scenario counts. Handle renames gracefully — fuzzy match on scenario name similarity | [PM#6] |
| 4 | Implement per-agent comparison strategies — triage: per-scenario class + confidence diff; generator: per-sub-metric diff (locator/POM/test/import); healer: per-scenario fix + per-metric diff. Don't use a single generic diff that misses sub-metric regressions | [PM#13] |
| 5 | For changed scenarios, show before/after: classification, confidence, confidence delta, token count, latency, cost | — |
| 6 | CLI command: `qa-agent eval compare {run-a} {run-b}` | — |
| 7 | Output as markdown table + JSON | — |
| 8 | Refuse to compare partial runs (incomplete traces) unless `--force` flag is passed | [PM#18] |

### Phase EO3 — Dashboard Experiment History (~0.5 day)

| # | Task | Pre-Mortem |
|---|------|-----------|
| 1 | `GET /api/eval/experiments` — list eval runs with scores, deltas, scenario counts. Cache results in memory with file-watcher invalidation. Add pagination (`?page=1&limit=20`) | [PM#16] |
| 2 | Experiment history table on dashboard (sortable, per-agent filter) | — |
| 3 | Select two runs → click COMPARE → show diff view with per-agent column templates (triage columns differ from generator columns) | [PM#17] |
| 4 | Highlight regressions in red, improvements in green. Filter: All / Regressions only / Improvements only / Changed only | — |
| 5 | LangSmith-style results table: per-scenario rows with heat map coloring (green→amber→red gradient), sortable columns, 3 view modes (Compact/Full/Diff) | — |
| 6 | Mobile: Compact mode only, horizontal scroll with fixed scenario column, disable `backdrop-filter` for performance. Paginate to 10 rows. Test on real iPhone hardware | [PM#7] |

### Phase EO4 — Dashboard Trace Viewer (~0.5 day)

| # | Task | Pre-Mortem |
|---|------|-----------|
| 1 | `GET /api/eval/trace/{run_id}/{scenario}` — serve trace JSON. Bind to localhost only for security | [PM#19] |
| 2 | Trace viewer panel: full system prompt + human message, full output response (raw + parsed), tokens (with cache breakdown), latency, cost, model, purpose | [PM#5] |
| 3 | For error scenarios: show the captured prompt (recorded before the call), exception type, error message, stack trace | [PM#9] |
| 4 | Click "View Trace" from comparison view or experiment history | — |
| 5 | Side-by-side trace comparison for two runs of the same scenario — highlight prompt differences | — |

### Phase EO5 — LangSmith Integration (Future — if needed)

| # | Task |
|---|------|
| 1 | Add `langsmith` dependency |
| 2 | Enable tracing with `LANGCHAIN_TRACING_V2=true` |
| 3 | Upload golden datasets to LangSmith |
| 4 | Run experiments through LangSmith evaluate() |
| 5 | Link LangSmith traces from our dashboard |

---

## Pre-Mortem Coverage Summary

All 19 pre-mortem issues from [PRE_MORTEM_EVAL_OBSERVABILITY.md](PRE_MORTEM_EVAL_OBSERVABILITY.md) are addressed in the build phases above:

| Issue | Severity | Addressed In |
|-------|----------|-------------|
| #1 Concurrent trace cross-contamination | HIGH | EO1 task 1 — `contextvars.ContextVar` |
| #2 No per-scenario token accumulators | HIGH | EO1 task 2 — capture from `response.usage_metadata` |
| #3 Git repo bloat | HIGH | EO1 task 6 — `.gitignore` + retention policy |
| #4 AUDIT_RAW blocks capture | HIGH | EO1 task 5 — independent capture path |
| #5 Missing system prompt | MEDIUM | EO1 task 3, EO4 task 2 — full message list |
| #6 Scenario rename breaks comparison | MEDIUM | EO2 tasks 2-3 — stable IDs + fuzzy match |
| #7 Mobile table performance | MEDIUM | EO3 task 6 — compact mode, pagination, no backdrop-filter |
| #8 Multi-agent trace format | MEDIUM | EO1 task 8 — `purpose` field per call |
| #9 Empty traces for errors | MEDIUM | EO1 task 4, EO4 task 3 — capture before call |
| #10 Cost inaccuracy with caching | MEDIUM | EO1 task 2 — cache token breakdown |
| #11 No trace cleanup | MEDIUM | EO1 task 6 — retention policy (last 20 runs) |
| #12 Privacy in traces | MEDIUM | EO1 task 7 — sanitize via `sanitizer.py` |
| #13 Scorecard structure variance | MEDIUM | EO2 task 4 — per-agent comparison strategies |
| #14 Progress counter race | LOW | EO1 task 9 — `asyncio.Lock` |
| #15 _consume_llm_calls conflict | HIGH | EO1 task 1 — independent capture, never use shared state |
| #16 No API pagination | LOW | EO3 task 1 — cache + pagination |
| #17 Asymmetric diff columns | LOW | EO3 task 3 — per-agent column templates |
| #18 Orphaned partial traces | LOW | EO1 task 10, EO2 task 8 — batch write or mark partial |
| #19 No auth on trace API | LOW | EO4 task 1 — localhost binding |

---

## Test Plan (Option B)

Every phase has dedicated tests that validate real behavior — not just "does it import" but "does it produce correct, useful output."

### Phase EO1 Tests — Per-Scenario Tracing

**File:** `tests/test_eval_tracer.py`

| Test | What It Validates | Why It Matters |
|------|------------------|----------------|
| `test_trace_captures_full_prompt` | After running a single triage scenario through the tracer, verify the trace JSON contains the complete input prompt (system prompt + human message) — not truncated, not empty | A truncated prompt is useless for debugging. If someone inspects why triage misclassified, they need the full prompt |
| `test_trace_captures_full_response` | Verify the trace contains the complete LLM response including `failure_class`, `confidence`, and `reasoning` — parsed from the raw response | Without the full response, you can't see what the LLM actually said vs what the parser extracted |
| `test_trace_records_accurate_token_count` | Compare trace's recorded `input_tokens` and `output_tokens` against `response.usage_metadata`. Must match exactly, not be 0 | Token counts drive cost calculation. If traces show 0 tokens, the cost data is worthless |
| `test_trace_records_latency` | Verify `latency_ms` is > 0 and < 60000 (reasonable range). Compare against wall-clock time of the LLM call ± 100ms | Latency is critical for identifying slow scenarios. A latency of 0 or -1 means the timer is broken |
| `test_trace_records_cost` | Verify `cost_usd` matches `estimate_cost(model, input_tokens, output_tokens)` from `config.py` | Cost must be calculated from real token counts with correct model pricing, not hardcoded |
| `test_trace_links_to_scenario` | Verify each trace contains `scenario_name`, `agent`, `run_id` and that `scenario_name` matches a real golden scenario | Unlinked traces are useless — you need to know which scenario produced which trace |
| `test_traces_written_for_all_scenarios` | Run full triage eval (35 scenarios), verify exactly 35 trace files exist with no duplicates and no missing | If only 30/35 scenarios have traces, 5 failures are invisible |
| `test_trace_file_is_valid_json` | Every trace file must parse as valid JSON. Corrupt files fail loudly, not silently | A corrupt trace file that silently fails wastes debugging time |
| `test_trace_includes_model_name` | Verify the trace records which model was used (`claude-sonnet-4-6` vs `claude-opus-4-6`) | When comparing experiments across model changes, you need to know which model produced each result |
| `test_traces_for_failed_scenarios_include_error` | For scenarios where the LLM call throws an exception, verify the trace captures the error message, not just an empty response | The most important traces to inspect are the failures — if they have no error context, debugging is blind |
| `test_concurrent_traces_no_cross_contamination` | Run 5 triage scenarios concurrently. Verify each trace contains ONLY its own LLM call data — Scenario A's tokens must not appear in Scenario B's trace. Compare each trace's `input_prompt` against its scenario's error message to confirm they match | [PM#1, PM#15] The entire tracer is worthless if concurrent scenarios bleed into each other. This is the most critical test |
| `test_concurrent_traces_each_have_own_token_count` | Run 5 scenarios concurrently. Sum all 5 traces' `input_tokens` — must equal the run-level total. Each individual trace must have `input_tokens > 0` (not 0 from a stolen consume) | [PM#2] If concurrent traces show 0 tokens for some scenarios, per-scenario cost tracking is broken |
| `test_trace_includes_system_prompt` | Verify the trace's `input_prompt` contains the TRIAGE.md system prompt content (check for key phrases like "locator_drift", "app_defect", "confidence scoring"), not just the human message | [PM#5] Without the system prompt, you can't debug classification logic changes. This was the #1 complaint about the old audit trail |
| `test_trace_captures_cache_token_breakdown` | Verify the trace includes `cache_read_input_tokens` and `cache_creation_input_tokens` fields from `response.usage_metadata`, not just `input_tokens` | [PM#10] Anthropic's prompt caching prices cached tokens at 10% — without this breakdown, per-scenario costs are overstated by up to 90% |
| `test_trace_captures_prompt_before_timeout` | Mock an LLM call that times out after recording the prompt but before returning a response. Verify the trace has the full `input_prompt` but `output_response` is null with `error: "TimeoutError"` | [PM#9] Timeout scenarios are the hardest to debug — if the trace has no prompt data, you can't see what was sent |
| `test_trace_captures_pre_call_error` | Mock a scenario where `MemoryStore()` throws an exception before the LLM call. Verify the trace has `error: "MemoryError: ..."`, `input_prompt: null`, `output_response: null` — not an empty trace file | [PM#9] Pre-call errors are different from LLM errors — the trace must distinguish them |
| `test_trace_captures_post_call_parse_error` | Mock a scenario where the LLM returns unparseable JSON. Verify the trace has the full `input_prompt`, the raw `output_response` (the bad JSON), and `error: "JSONDecodeError: ..."` | [PM#9] Parse errors mean the LLM responded but we couldn't extract the answer — the raw response is the clue |
| `test_trace_sanitizes_pii` | Create a scenario with a DOM snapshot containing an email address (test@example.com). Verify the stored trace has the email redacted or removed by `sanitizer.py` | [PM#12] Traces contain full prompts with DOM data — PII must be stripped before writing to disk |
| `test_trace_not_in_git` | Run an eval, verify `qa_agent/eval/traces/` is in `.gitignore`. Run `git status` and confirm no trace files appear as untracked | [PM#3] If traces accidentally get committed, 800KB per run bloats the repo permanently |
| `test_trace_retention_cleanup` | Create 25 fake trace runs for triage. Call the cleanup function. Verify only the 20 most recent remain — 5 oldest deleted | [PM#11] Without cleanup, traces accumulate indefinitely. After 3 months = 500MB on disk |
| `test_healer_trace_has_purpose_field` | Run a healer eval scenario. Verify each LLM call in the trace has a `purpose` field ("locator_fix" or "timing_fix") | [PM#8] Generator/healer make multiple calls per scenario — without `purpose`, you can't tell which call produced which artifact |
| `test_partial_run_trace_marked_incomplete` | Start an eval, cancel after 10/35 scenarios. Verify the trace metadata has `"complete": false, "scenarios_expected": 35, "scenarios_completed": 10` | [PM#18] Partial traces without metadata look like full runs with missing scenarios — confuses the comparison engine |

### Phase EO2 Tests — Experiment Comparison Engine

**File:** `tests/test_experiment_compare.py`

| Test | What It Validates | Why It Matters |
|------|------------------|----------------|
| `test_identifies_regression` | Given Run A (scenario X passes) and Run B (scenario X fails), comparison reports scenario X as a regression with before/after details | The entire point of comparison — catch when a change breaks something |
| `test_identifies_improvement` | Given Run A (scenario Y fails) and Run B (scenario Y passes), comparison reports scenario Y as an improvement | Improvements should be celebrated and tracked, not just regressions |
| `test_identifies_stable_scenarios` | Given Run A and Run B where scenario Z passes in both, comparison reports it as stable with no change | Stable scenarios shouldn't clutter the diff — only show what changed |
| `test_handles_new_scenarios_in_run_b` | Run B has 5 new scenarios that didn't exist in Run A. Comparison reports them as "new" not "regression" | Adding golden scenarios shouldn't trigger false regression alerts |
| `test_handles_removed_scenarios_in_run_b` | Run A has scenario W that's missing from Run B. Comparison reports it as "removed" not "improvement" | Removing a scenario isn't a fix — it's a coverage reduction |
| `test_confidence_delta_shown_for_regressions` | For a regression, comparison shows exact confidence values: "before: 0.85, after: 0.71, Δ: -0.14" | Knowing HOW MUCH worse a scenario got is critical — 0.85→0.84 is noise, 0.85→0.40 is catastrophic |
| `test_classification_change_shown` | For a regression where `failure_class` changed (e.g., `locator_drift` → `test_flake`), comparison shows both classes | The regression type matters — wrong class vs low confidence are different problems |
| `test_compare_different_agents` | Comparing triage Run A vs planner Run B returns an error or empty diff (different agents can't be compared) | Preventing nonsensical comparisons that would confuse users |
| `test_compare_identical_runs` | Comparing a run against itself returns zero regressions, zero improvements, all stable | Edge case — should produce a clean "no changes" result |
| `test_output_as_json_and_markdown` | Comparison produces both JSON (machine-readable) and markdown (human-readable) output | JSON feeds the dashboard API, markdown goes in reports |
| `test_generator_comparison_diffs_sub_metrics` | Compare two generator runs where `locator_quality` regressed but `pom_validity` improved. Verify comparison shows BOTH changes, not just the composite score delta | [PM#13] Generic diffs hide sub-metric regressions. A composite "improvement" could mask a locator quality drop |
| `test_healer_comparison_shows_fix_type_changes` | Compare two healer runs where a scenario changed from locator fix to timing fix. Verify comparison shows the fix type change | [PM#13] Different fix types have different implications — switching from locator to timing fix needs visibility |
| `test_compare_rejects_partial_runs` | Attempt to compare a partial run (10/35 scenarios) against a full run. Without `--force`, returns error "Cannot compare partial run" | [PM#18] Comparing partial runs produces misleading diffs — 25 scenarios show as "removed" when they just didn't run |
| `test_scenario_rename_fuzzy_match` | Run A has scenario "flake_scroll_timeout", Run B renamed it to "flake_scroll_into_view_timeout". Comparison matches them as the same scenario via fuzzy match, not as removed+new | [PM#6] Scenario renames are common during golden dataset maintenance — shouldn't trigger false regression alerts |

### Phase EO3 Tests — Dashboard Experiment History API

**File:** `tests/test_eval_experiments_api.py`

| Test | What It Validates | Why It Matters |
|------|------------------|----------------|
| `test_experiments_endpoint_returns_all_runs` | `GET /api/eval/experiments` returns a list of all eval runs sorted by timestamp descending | Users need to see all runs to pick which ones to compare |
| `test_each_experiment_has_score_and_delta` | Each experiment entry includes `score`, `previous_score`, `delta`, `agent`, `timestamp`, `passed` | Without delta, you can't see trend at a glance |
| `test_experiments_filterable_by_agent` | `GET /api/eval/experiments?agent=triage` returns only triage runs | With 4 agents × many runs, filtering is essential |
| `test_compare_endpoint_returns_diff` | `POST /api/eval/compare` with two run IDs returns the comparison JSON from Phase EO2 | The dashboard needs an API to drive the comparison view |
| `test_compare_endpoint_rejects_invalid_ids` | Comparing non-existent run IDs returns 404, not a crash | Bad input shouldn't crash the server |
| `test_experiments_include_scenario_count` | Each experiment entry shows how many scenarios passed/failed/total | "85.7% on 35 scenarios" is more meaningful than just "85.7%" |
| `test_experiments_endpoint_cached` | Call `GET /api/eval/experiments` twice within 1 second. Second call returns in < 50ms (cached). Add a new scorecard file, call again — returns updated list (cache invalidated) | [PM#16] Scanning 500+ files on every request makes the dashboard sluggish |
| `test_experiments_paginated` | Request `?page=1&limit=10` returns 10 results. Request `?page=2&limit=10` returns next 10. Total count header included | [PM#16] Without pagination, 1000 experiments loads all at once — slow and memory-heavy |

### Phase EO4 Tests — Trace Viewer API

**File:** `tests/test_eval_trace_api.py`

| Test | What It Validates | Why It Matters |
|------|------------------|----------------|
| `test_trace_endpoint_returns_full_trace` | `GET /api/eval/trace/{run_id}/{scenario}` returns the complete trace JSON with prompt, response, tokens, latency | The trace viewer needs the full data to display |
| `test_trace_endpoint_404_for_missing` | Request a trace for a non-existent run or scenario returns 404 | Clean error handling, not a crash with stack trace |
| `test_trace_prompt_not_truncated` | The returned trace's `input_prompt` field is complete — contains the full system prompt + human message, not cut off at 1000 chars | Truncated prompts defeat the purpose of tracing — you need to see what the LLM actually received |
| `test_trace_response_includes_raw_and_parsed` | The trace includes both the raw LLM response string and the parsed structured output (failure_class, confidence) | Raw response shows what the LLM said; parsed shows what we extracted. Mismatches between them reveal parser bugs |
| `test_side_by_side_trace_comparison` | Request traces for the same scenario from two different runs. Both return successfully and can be displayed side-by-side | The most powerful debugging view — see exactly what changed in the prompt/response between two runs |
| `test_trace_includes_memory_context` | If the agent injected memory context (calibration, similar failures, stability data) into the prompt, the trace captures it | Memory injection is invisible during eval — traces make it visible, so you can see if bad memory caused a misclassification |
| `test_trace_endpoint_localhost_only` | Attempt to access `/api/eval/trace/` from a non-localhost origin (or verify the endpoint checks `request.client.host`). Should reject or warn | [PM#19] Traces contain full prompts — shouldn't be accessible from the network |

---

## Success Criteria

1. Every eval scenario captures full LLM trace (input, output, tokens, latency, cost)
2. Traces stored as JSON, git-trackable, browsable from dashboard
3. Compare any two eval runs — see exactly which scenarios changed and why
4. Dashboard shows experiment history with score trend per agent
5. Trace viewer shows full prompt/response for debugging misclassifications
6. Zero external dependencies (Option B)
7. Works with existing EVAL ALL button and event-driven updates
8. All Phase EO1-EO4 tests pass (50 tests: 22 tracer, 14 comparison, 8 API, 7 trace viewer)
9. No test is trivial — every test validates behavior that would cause real debugging pain if broken
10. All 19 pre-mortem issues covered by at least one test (marked with [PM#N])
