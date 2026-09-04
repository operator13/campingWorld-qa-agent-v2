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

### Phase EO1 — Per-Scenario Tracing (~0.5 day)

| # | Task |
|---|------|
| 1 | Create `qa_agent/eval/tracer.py` — capture LLM input/output/tokens/latency per call |
| 2 | Hook tracer into `AuditStore.record_llm_call()` to capture full prompt/response |
| 3 | Store traces in `qa_agent/eval/traces/{agent}/{run_id}.json` |
| 4 | Each trace includes: scenario name, model, input prompt, output response, tokens, latency, cost |
| 5 | Run eval suite — verify traces are captured for all 68 scenarios |

### Phase EO2 — Experiment Comparison Engine (~0.5 day)

| # | Task |
|---|------|
| 1 | Create `qa_agent/eval/experiment_compare.py` — diff two eval scorecards |
| 2 | Identify: regressions (pass→fail), improvements (fail→pass), stable |
| 3 | For changed scenarios, show before/after classification + confidence |
| 4 | CLI command: `qa-agent eval compare {run-a} {run-b}` |
| 5 | Output as markdown table + JSON |

### Phase EO3 — Dashboard Experiment History (~0.5 day)

| # | Task |
|---|------|
| 1 | `GET /api/eval/experiments` — list all eval runs with scores and deltas |
| 2 | Experiment history table on dashboard (sortable, per-agent filter) |
| 3 | Select two runs → click COMPARE → show diff view |
| 4 | Highlight regressions in red, improvements in green |

### Phase EO4 — Dashboard Trace Viewer (~0.5 day)

| # | Task |
|---|------|
| 1 | `GET /api/eval/trace/{run_id}/{scenario}` — serve trace JSON |
| 2 | Trace viewer panel: input prompt, output response, tokens, latency |
| 3 | Click "View Trace" from comparison view or experiment history |
| 4 | Side-by-side trace comparison for two runs of the same scenario |

### Phase EO5 — LangSmith Integration (Future — if needed)

| # | Task |
|---|------|
| 1 | Add `langsmith` dependency |
| 2 | Enable tracing with `LANGCHAIN_TRACING_V2=true` |
| 3 | Upload golden datasets to LangSmith |
| 4 | Run experiments through LangSmith evaluate() |
| 5 | Link LangSmith traces from our dashboard |

---

## Success Criteria

1. Every eval scenario captures full LLM trace (input, output, tokens, latency, cost)
2. Traces stored as JSON, git-trackable, browsable from dashboard
3. Compare any two eval runs — see exactly which scenarios changed and why
4. Dashboard shows experiment history with score trend per agent
5. Trace viewer shows full prompt/response for debugging misclassifications
6. Zero external dependencies (Option B)
7. Works with existing EVAL ALL button and event-driven updates
