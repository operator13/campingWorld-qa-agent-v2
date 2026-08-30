# Feature: Per-Agent Audit Trail

> Every agent logs exactly what it received, what it decided, what it produced, how long it took, and how much it cost — creating a complete, queryable, replayable trail for debugging, compliance, evaluation, and optimization.

**Status:** PLANNED
**Priority:** High
**Depends on:** Core framework (Phases 0-4), Memory feature (for storage pattern)
**Depended on by:** Eval Agent (BUILD_SPEC_EVAL_AGENT.md)

---

## The Problem

Today when something goes wrong — a bad test generated, a wrong Triage call, a Healer fix that didn't work — there's no way to trace what happened. The metrics node records the *outcome* (pass/fail), and memory records *what was learned*, but neither captures the *decision process*:

- What inputs did the Planner receive?
- What prompt was sent to Claude?
- What was the raw LLM response before parsing?
- How long did the node take?
- How many tokens were consumed?
- Why did the router send it to Healer instead of Human Review?

Without this, debugging is guesswork, cost tracking is blind, evals can't compare runs, and you can't answer "what went wrong on run #47?"

## The Solution

A dual-format audit system that every agent node writes to automatically — markdown for human readability, JSON for machine consumption by the Eval Agent. No code changes to the agent logic itself — the logging wraps the existing node functions via a decorator.

---

## A. What Gets Logged Per Agent

| Field | Example | Why it matters |
|-------|---------|---------------|
| **Timestamp** | 2026-08-19 14:32:07 UTC | When it ran |
| **Run ID** | run-47 | Links to RUN_HISTORY.md |
| **Node** | triage | Which agent |
| **Duration** | 3.2s | Performance tracking |
| **Input tokens** | 1,847 | Cost tracking |
| **Output tokens** | 342 | Cost tracking |
| **Model** | claude-sonnet-4-6 | Which model was used |
| **Prompt version** | TRIAGE.md@abc1234 | Git hash of the prompt file used |
| **Input summary** | error: "TimeoutError...", route: /checkout | What the agent received (truncated) |
| **Full input** | (stored in JSON) | Complete input state for replay |
| **Raw prompt** | (stored in JSON) | Exact prompt sent to Claude |
| **Raw LLM response** | (stored in JSON) | Exact response from Claude before parsing |
| **Parsed output** | failure_class: locator_drift, confidence: 0.82 | Structured output after parsing |
| **Memory context** | 2 known fixes, 3 calibration examples | What memory was injected |
| **Routing decision** | → healer (confidence 0.82 >= 0.75) | Where the graph went next |
| **Errors** | None | Any exceptions or parse failures |
| **Cache hit** | false | Was the result from cache or LLM? |
| **Golden tag** | null or "golden-checkout-v2" | If this run is tagged as a golden reference |

---

## B. Storage Format

### Dual format: Markdown for humans, JSON for machines

#### `memory/AUDIT_TRAIL.md` — human-readable append-only log

```markdown
# Audit Trail

## Run run-47 — 2026-08-19 14:32

### design_reader (14:32:07 — 2.1s)
- **Model:** claude-sonnet-4-6
- **Prompt:** DESIGN_READER.md@abc1234
- **Tokens:** 1,204 in / 856 out ($0.003)
- **Input:** figma_ref=abc123/1:24, goal="Test checkout flow"
- **Output:** ExpectedUI with 5 elements, 2 flows, route=/checkout
- **Memory:** none (no prior history for this route)
- **Cache:** miss
- **Errors:** none

### planner (14:32:09 — 4.7s)
- **Model:** claude-sonnet-4-6
- **Prompt:** PLANNER.md@def5678
- **Tokens:** 2,891 in / 1,203 out ($0.018)
- **Input:** 5 UI elements, 4 acceptance criteria
- **Output:** 6 test cases (4 @checkout, 2 @validation)
- **Memory:** 1 volatile route (/checkout), 0 flaky tests
- **Lessons:** "Button text renames frequently — prefer testid"
- **Cache:** miss
- **Errors:** none

### triage (14:32:28 — 3.2s)
- **Model:** claude-sonnet-4-6
- **Prompt:** TRIAGE.md@ghi9012
- **Tokens:** 1,847 in / 342 out ($0.012)
- **Input:** error="TimeoutError on Submit button", 2 failed cases
- **Output:** failure_class=locator_drift, confidence=0.82
- **Rubric:** C1=0.2 C2=0.2 C3=0.1 C4=0.1 C5=0.1 raw=0.7 final=0.7
- **Memory:** 1 similar failure (FP-003), 2 calibration examples
- **Routing:** → healer (confidence 0.82 >= CONF_SURE 0.75)
- **Errors:** none

### healer (14:32:31 — 0.02s)
- **Tokens:** 0 (cache hit — no LLM call)
- **Input:** error on getByRole('button', {name: 'Submit'})
- **Output:** applied known fix → getByTestId('checkout-submit')
- **Memory:** cache HIT from locators/CHECKOUT.md
- **Cache:** hit
- **Errors:** none

### executor (14:32:31 — 7.8s) [retry]
- **Tokens:** 0
- **Input:** patched page object
- **Output:** passed=true, 0 failed cases
- **Fix verified:** locators/CHECKOUT.md success:no → success:yes
- **Errors:** none

### metrics (14:32:39 — 0.01s)
- **Tokens:** 0
- **Output:** recorded run #47 (outcome=healed)
- **Triage call recorded:** ID 23

### Run Summary
- **Total duration:** 35.4s
- **Total tokens:** 9,398 in / 5,292 out
- **Estimated cost:** $0.042
- **Outcome:** healed (locator drift on /checkout)
- **Memory writes:** 3 (locator fix, failure pattern, test stability)
```

#### `memory/audit_runs/<run-id>.json` — machine-readable per-run data

```json
{
  "run_id": "run-47",
  "timestamp": "2026-08-19T14:32:07Z",
  "golden_tag": null,
  "total_duration_ms": 35400,
  "total_input_tokens": 9398,
  "total_output_tokens": 5292,
  "estimated_cost_usd": 0.042,
  "outcome": "healed",
  "nodes": [
    {
      "node": "triage",
      "timestamp": "2026-08-19T14:32:28Z",
      "duration_ms": 3200,
      "model": "claude-sonnet-4-6",
      "prompt_version": "TRIAGE.md@ghi9012",
      "input_tokens": 1847,
      "output_tokens": 342,
      "cost_usd": 0.012,
      "cache_hit": false,
      "errors": [],
      "dom_snapshot": null,
      "input_state": {
        "goal": "Test checkout flow",
        "failed_cases": ["tc-checkout-01", "tc-checkout-04"],
        "error_message": "TimeoutError: locator.click: Timeout 10000ms exceeded...",
        "dom_snippet": "<button class='submit-btn'>..."
      },
      "raw_prompt": [
        {"role": "system", "content": "You are a QA failure triage agent..."},
        {"role": "human", "content": "## Failure Report\n..."}
      ],
      "raw_llm_response": "{\"failure_class\": \"locator_drift\", \"confidence\": 0.82, \"rubric\": {\"C1\": 0.2, \"C2\": 0.2, \"C3\": 0.1, \"C4\": 0.1, \"C5\": 0.1}}",
      "parsed_output": {
        "failure_class": "locator_drift",
        "confidence": 0.82,
        "rubric": {"C1": 0.2, "C2": 0.2, "C3": 0.1, "C4": 0.1, "C5": 0.1}
      },
      "memory_context": {
        "files_read": ["memory/FAILURES.md", "memory/HUMAN_DECISIONS.md"],
        "similar_failures_found": 1,
        "calibration_examples": 2,
        "context_tokens": 412
      },
      "routing_decision": {
        "next_node": "healer",
        "reason": "confidence 0.82 >= CONF_SURE 0.75, class=locator_drift"
      },
      "guardrail_result": null
    },
    {
      "node": "healer",
      "timestamp": "2026-08-19T14:32:31Z",
      "duration_ms": 20,
      "model": null,
      "prompt_version": null,
      "input_tokens": 0,
      "output_tokens": 0,
      "cost_usd": 0.0,
      "cache_hit": true,
      "errors": [],
      "dom_snapshot": null,
      "input_state": {
        "error": "TimeoutError on getByRole('button', {name: 'Submit'})"
      },
      "parsed_output": {
        "fix_applied": "getByTestId('checkout-submit')",
        "source": "cache"
      },
      "guardrail_result": {
        "guardrail_passed": true,
        "guardrail_rejected_diff": null
      }
    }
  ]
}
```

---

## C. Architecture

### Decorator-based logging — zero changes to agent logic

```python
from qa_agent.audit import audit_node

@audit_node
async def triage(state: QAState) -> dict:
    # existing code unchanged
    ...
```

The `@audit_node` decorator:
1. Records the timestamp + full input state before the node runs
2. Captures the prompt version (git hash of the prompt .md file)
3. Wraps the LLM call to capture raw prompt, raw response, and token usage
4. Records the parsed output + routing decision after the node returns
5. Writes both markdown entry to AUDIT_TRAIL.md and JSON to audit_runs/
6. If an exception occurs, records the error and re-raises

### Orchestrator audit (outside LangGraph)

> **Note:** The orchestrator (`qa_agent/orchestrator/orchestrator.py`) is a separate flow that does not use the LangGraph state machine. Its key functions — `generate_pom()` and `generate_tests()` — are standalone async functions, not graph nodes. To audit them, wrap these functions with the same `@audit_node` pattern adapted for standalone async functions (i.e., the decorator captures inputs/outputs/timing/tokens without requiring a `QAState` parameter). The popup dismissal, dynamic URL resolution, and crawl steps should also be instrumented.

### Token tracking integration

The decorator hooks into `langchain-anthropic`'s callback system to capture actual token counts and the raw prompt/response from Claude's response metadata.

```python
class AuditCallback(BaseCallbackHandler):
    def on_llm_start(self, serialized, prompts, **kwargs):
        self.raw_prompt = prompts

    def on_llm_end(self, response, **kwargs):
        self.input_tokens = response.llm_output["usage"]["input_tokens"]
        self.output_tokens = response.llm_output["usage"]["output_tokens"]
        self.raw_response = response.generations[0][0].text
```

### Prompt version tracking

Each prompt file gets a version stamp derived from its git hash:

```python
def get_prompt_version(prompt_path: Path) -> str:
    """Return 'FILENAME@short_hash' for the prompt file."""
    result = subprocess.run(
        ["git", "hash-object", str(prompt_path)],
        capture_output=True, text=True
    )
    short_hash = result.stdout.strip()[:7]
    return f"{prompt_path.name}@{short_hash}"
```

This means when you change a prompt, the audit trail shows exactly which version produced which results — enabling the Eval Agent to correlate prompt changes with metric shifts.

### Cost estimation

```python
COST_MAP = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
}
```

### Run ID generation

Each graph invocation gets a unique run ID (e.g. `run-47`) that links the audit trail to `RUN_HISTORY.md`. The run ID is stored in the graph config's `thread_id`.

---

## D. What Each Node Logs

| Node / System | Special fields |
|------|---------------|
| **Design Reader** | Figma ref, element count, flow count, raw Figma MCP response |
| **Planner** | AC count, test case count, tags generated, volatile routes injected |
| **Generator** | Page object count, spec file count, locator types used, known testids injected |
| **Executor** | Pass/fail per test, route changes, fix verifications, **dom_snapshot** (PREREQUISITE: currently returns None — must be implemented for triage C2 scoring) |
| **Triage** | Rubric breakdown (C1-C5), similar failure match, routing decision, raw classification |
| **Healer** | Cache hit/miss, fix applied, guardrail result, diff produced, guardrail_passed: true/false, guardrail_rejected_diff: (if rejected, the diff that was blocked) |
| **Human Review** | Decision (heal/defect), reasoning, time waiting for human |
| **Defect Report** | Jira ticket key, fingerprint, dedup result |
| **Metrics** | Run ID recorded, triage call ID recorded |
| **Orchestrator** | Pages crawled, snapshot sizes, POM/test validation results, LLM token usage for generate_pom/generate_tests, popup dismissal results, dynamic URL resolution results |
| **Intake (Jira)** | Jira ticket key, fields extracted (goal, ACs, app_url), API response time |
| **Intake (Figma)** | Figma file ref, node count, frames extracted, MCP response time |
| **Budget** | Budget checked, remaining budget, cost so far, budget exhausted flag |
| **PR Gate** | Gate decision (pass/block), test results summary, confidence threshold |

---

## E. Eval Agent Integration Points

The Eval Agent consumes audit data through these interfaces:

### 1. Replay — re-run a node with same inputs, different config

```python
from qa_agent.audit import replay_node

# Load the exact inputs from run-47's triage call
# Re-run with a different prompt or model
result = await replay_node(
    run_id="run-47",
    node="triage",
    overrides={"model": "claude-opus-4-6", "prompt": "TRIAGE_v2.md"}
)
```

The JSON audit stores the complete `input_state` and `raw_prompt`, making replay deterministic (same inputs, different agent config).

### 2. Golden tagging — mark a run as reference

```bash
qa-agent audit tag run-47 --golden "checkout-locator-drift-v1"
```

This sets the `golden_tag` field in the run's JSON. The Eval Agent uses golden runs as ground truth for regression detection.

### 3. Diff — compare two runs

```python
from qa_agent.audit import diff_runs

# Compare outputs between two runs
diff = diff_runs("run-47", "run-52", node="triage")
# Returns: {"field": "confidence", "before": 0.82, "after": 0.65, "delta": -0.17}
```

### 4. Batch query — aggregate across runs

```python
from qa_agent.audit import query_runs

# Get all triage calls with their accuracy
results = query_runs(
    node="triage",
    fields=["parsed_output.failure_class", "parsed_output.confidence"],
    since="2026-08-01"
)
```

### 5. Prompt A/B comparison

```python
from qa_agent.audit import compare_prompts

# Compare triage accuracy between two prompt versions
report = compare_prompts(
    node="triage",
    prompt_a="TRIAGE.md@abc1234",
    prompt_b="TRIAGE.md@def5678",
    metric="classification_accuracy"
)
```

The Eval Agent uses prompt versions from the audit trail to automatically detect when a prompt change caused a regression.

---

## F. Queryable Summaries

### Per-run queries

```bash
qa-agent audit run-47          # Show full audit trail for run 47
qa-agent audit run-47 --json   # Machine-readable output
qa-agent audit run-47 --node triage  # Just the triage entry
qa-agent audit run-47 --prompt       # Show raw prompt sent to Claude
qa-agent audit run-47 --response     # Show raw LLM response
```

### Aggregate queries

```bash
qa-agent audit cost            # Total cost this week
qa-agent audit cost --since 2026-08-01  # Cost since date
qa-agent audit slow            # Nodes that took >10s
qa-agent audit tokens          # Token usage by node
qa-agent audit errors          # All runs with parse errors or exceptions
```

### Golden management

```bash
qa-agent audit tag run-47 --golden "checkout-v1"  # Tag as golden
qa-agent audit golden --list   # List all golden runs
qa-agent audit diff run-47 run-52  # Compare two runs
```

### Aggregated insights (feeds into weekly review)

```
This week:
  Total runs: 7
  Total cost: $0.31
  Slowest node: generator (avg 6.1s)
  Most expensive node: planner (avg $0.018/run)
  Cache hit rate: 34% (healer)
  Parse errors: 2 (triage on run-44, run-46)
  Prompt changes: 1 (TRIAGE.md updated on 08/17)
  Metric shift: triage confidence dropped 12% after prompt change
```

---

## G. Build Phases

### Phase AT1 — Core audit decorator + dual-format logging
**Goal:** Every node automatically logs inputs, outputs, duration, and errors in both markdown and JSON.

| # | Task | Status |
|---|------|--------|
| 1 | `qa_agent/audit.py` — `@audit_node` decorator with timing + input/output capture | TODO |
| 2 | `memory/AUDIT_TRAIL.md` — append-only human-readable log | TODO |
| 3 | `memory/audit_runs/` — per-run JSON files | TODO |
| 4 | State summary helper — truncate large fields for markdown, keep full in JSON | TODO |
| 5 | Apply decorator to all 8 nodes (non-invasive, no logic changes) | TODO |
| 6 | Run ID generation from graph config thread_id | TODO |
| 7 | Error capture — log exceptions before re-raising | TODO |

**Tests:**
- Unit: decorator captures timing and writes to both AUDIT_TRAIL.md and JSON
- Unit: input/output summaries are truncated in markdown, complete in JSON
- Unit: errors are logged and re-raised (not swallowed)
- Unit: run ID links to RUN_HISTORY.md
- Integration: full graph run produces a complete audit trail in both formats

**Done when:** Every node invocation is logged with timestamp, duration, full inputs, full outputs, and errors in both markdown and JSON.

---

### Phase AT2 — Raw prompt/response capture + token tracking
**Goal:** Every LLM call logs the exact prompt sent, the raw response received, actual token usage, and estimated cost.

| # | Task | Status |
|---|------|--------|
| 1 | LangChain callback handler to capture raw prompt and raw response text | TODO |
| 2 | Token count capture from Claude response metadata | TODO |
| 3 | Cost estimation using per-model pricing table | TODO |
| 4 | Token/cost/prompt/response fields in JSON audit entries | TODO |
| 5 | Summarized token/cost in markdown entries | TODO |
| 6 | Run summary with total tokens and cost | TODO |
| 7 | Integration with `budget.py` — audit records whether budget was checked/exhausted | TODO |

**Tests:**
- Unit: callback captures raw prompt text and raw response text
- Unit: callback captures token counts from mocked LLM response
- Unit: cost estimation correct for all models in COST_MAP
- Unit: run summary totals are accurate
- Integration: full run audit shows raw prompt/response per LLM-calling node

**Done when:** Every LLM call's exact prompt, raw response, token counts, and cost are stored in JSON.

---

### Phase AT3 — Prompt versioning + memory context
**Goal:** Audit trail tracks which prompt version produced each result and what memory was injected.

| # | Task | Status |
|---|------|--------|
| 1 | `get_prompt_version()` — git hash-object for prompt .md files | TODO |
| 2 | Prompt version field in audit entries | TODO |
| 3 | Log memory context: files read, tokens injected, similar failures found | TODO |
| 4 | Log cache hit/miss for Healer known-fix path | TODO |
| 5 | Log routing decision with reasoning (which condition triggered) | TODO |
| 6 | Log rubric breakdown for Triage (C1-C5 scores, guards applied) | TODO |

**Tests:**
- Unit: prompt version changes when prompt file is modified
- Unit: memory context logged with source files listed
- Unit: cache hit/miss recorded correctly
- Unit: routing decision includes the condition that matched
- Unit: rubric breakdown appears in Triage audit entry

**Done when:** Audit trail shows the complete decision context — which prompt version, what memory influenced the agent, and why the router chose the next node.

---

### Phase AT4 — Replay + golden tagging + diff
**Goal:** Enable the Eval Agent to replay nodes, tag golden runs, and compare runs.

| # | Task | Status |
|---|------|--------|
| 1 | `replay_node()` — load input_state from JSON, re-invoke node with overrides | TODO |
| 2 | `tag_golden()` — set golden_tag on a run's JSON file | TODO |
| 3 | `diff_runs()` — compare parsed_output between two runs for a given node | TODO |
| 4 | `query_runs()` — aggregate query across audit JSON files | TODO |
| 5 | `compare_prompts()` — correlate prompt versions with metric outcomes | TODO |
| 6 | Index file for fast run lookup without scanning all JSON files | TODO |

**Tests:**
- Unit: replay_node produces output from stored inputs
- Unit: replay_node with overrides uses different model/prompt
- Unit: diff_runs detects field-level changes between runs
- Unit: query_runs filters by node, date range, and fields
- Unit: compare_prompts groups runs by prompt version
- Integration: tag a run as golden, then use it in eval comparison

**Done when:** The Eval Agent can replay any node, compare any two runs, and correlate prompt changes with metric shifts.

---

### Phase AT5 — CLI queries + weekly review integration
**Goal:** Queryable audit data + cost/performance insights in the weekly review.

| # | Task | Status |
|---|------|--------|
| 1 | `qa-agent audit <run-id>` — show full audit trail for a run | TODO |
| 2 | `qa-agent audit <run-id> --json` — machine-readable output | TODO |
| 3 | `qa-agent audit <run-id> --prompt` — show raw prompt | TODO |
| 4 | `qa-agent audit <run-id> --response` — show raw LLM response | TODO |
| 5 | `qa-agent audit cost` — total cost this week | TODO |
| 6 | `qa-agent audit slow` — nodes that exceeded time threshold | TODO |
| 7 | `qa-agent audit tokens` — token usage breakdown by node | TODO |
| 8 | `qa-agent audit errors` — runs with exceptions or parse errors | TODO |
| 9 | `qa-agent audit golden --list` — list golden-tagged runs | TODO |
| 10 | `qa-agent audit diff <run-a> <run-b>` — compare two runs | TODO |
| 11 | Weekly review integration — cost, duration, prompt changes, and error counts | TODO |
| 12 | AUDIT_TRAIL.md rotation — archive old entries to prevent unbounded growth | TODO |

**Tests:**
- Unit: CLI commands parse audit trail correctly
- Unit: cost aggregation across runs is accurate
- Unit: slow node detection uses configurable threshold
- Integration: weekly review includes audit-derived metrics

**Done when:** Audit data is queryable via CLI, supports golden management, and feeds into the weekly review.

---

## H. Assumptions

- Markdown log lives at `memory/AUDIT_TRAIL.md` — same convention as all other memory files.
- JSON logs live at `memory/audit_runs/<run-id>.json` — one file per run for fast lookup.
- The decorator is non-invasive — applied to existing node functions without changing their logic.
- Token counts come from Claude's response metadata (actual, not estimated).
- Raw prompts and responses are stored in full in JSON (may be large — rotation in Phase AT5).
- Cost estimation uses a static pricing table updated manually when Claude pricing changes.
- Markdown entries are truncated summaries; JSON entries are complete data.
- Both formats are git-tracked like all other memory files.
- Prompt versioning uses `git hash-object` — works even for uncommitted changes.

## I. Not in Scope

- Real-time streaming dashboard (CLI queries are sufficient for v1)
- Distributed tracing (single-process only — no microservices)
- LangSmith integration (this is a self-contained alternative)
- Billing/invoicing from audit data
- Automated cost alerts (use the existing observability module for alerts)
- Prompt auto-optimization (the Eval Agent may suggest changes, but the audit trail just records)

## J. Success Metrics

| Metric | How to measure | Target |
|--------|---------------|--------|
| Audit coverage | Nodes with audit decorator / total nodes | 100% (all 8 nodes) |
| Debugging time | Time to diagnose a bad run (before vs after) | 80% reduction |
| Cost visibility | Can answer "how much did run X cost?" | Yes, within $0.001 |
| Token accuracy | Audit token count vs Claude API dashboard | Within 1% |
| Performance overhead | Audit decorator latency | < 50ms per node (negligible) |
| Replay fidelity | Replayed node produces same output with same inputs | 100% (deterministic at temp=0) |
| Eval Agent utilization | Eval Agent queries that succeed against audit data | ≥95% |
| Prompt regression detection | Prompt changes correlated with metric shifts | ≥90% detection rate |
