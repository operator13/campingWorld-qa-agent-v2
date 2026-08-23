# Feature: Per-Agent Audit Trail

> Every agent logs exactly what it received, what it decided, what it produced, how long it took, and how much it cost — creating a complete, queryable trail for debugging, compliance, and optimization.

**Status:** PLANNED
**Priority:** High
**Depends on:** Core framework (Phases 0-4), Memory feature (for storage pattern)

---

## The Problem

Today when something goes wrong — a bad test generated, a wrong Triage call, a Healer fix that didn't work — there's no way to trace what happened. The metrics node records the *outcome* (pass/fail), and memory records *what was learned*, but neither captures the *decision process*:

- What inputs did the Planner receive?
- What prompt was sent to Claude?
- What was the raw LLM response before parsing?
- How long did the node take?
- How many tokens were consumed?
- Why did the router send it to Healer instead of Human Review?

Without this, debugging is guesswork, cost tracking is blind, and you can't answer "what went wrong on run #47?"

## The Solution

A markdown-backed audit log that every agent node writes to automatically — one entry per node invocation with structured fields. No code changes to the agent logic itself — the logging wraps the existing node functions.

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
| **Model** | claude-opus-4-20250514 | Which model was used |
| **Input summary** | error: "TimeoutError...", route: /checkout | What the agent received (truncated) |
| **Output summary** | failure_class: locator_drift, confidence: 0.82 | What the agent decided |
| **Memory context** | 2 known fixes, 3 calibration examples | What memory was injected |
| **Routing decision** | → healer (confidence 0.82 >= 0.75) | Where the graph went next |
| **Errors** | None | Any exceptions or parse failures |
| **Cache hit** | false | Was the result from cache or LLM? |

---

## B. Storage Format

### `memory/AUDIT_TRAIL.md` — append-only log

```markdown
# Audit Trail

## Run run-47 — 2026-08-19 14:32

### design_reader (14:32:07 — 2.1s)
- **Model:** claude-sonnet-4-20250514
- **Tokens:** 1,204 in / 856 out ($0.003)
- **Input:** figma_ref=abc123/1:24, goal="Test checkout flow"
- **Output:** ExpectedUI with 5 elements, 2 flows, route=/checkout
- **Memory:** none (no prior history for this route)
- **Cache:** miss
- **Errors:** none

### planner (14:32:09 — 4.7s)
- **Model:** claude-opus-4-20250514
- **Tokens:** 2,891 in / 1,203 out ($0.018)
- **Input:** 5 UI elements, 4 acceptance criteria
- **Output:** 6 test cases (4 @checkout, 2 @validation)
- **Memory:** 1 volatile route (/checkout), 0 flaky tests
- **Lessons:** "Button text renames frequently — prefer testid"
- **Cache:** miss
- **Errors:** none

### generator (14:32:14 — 6.3s)
- **Model:** claude-sonnet-4-20250514
- **Tokens:** 3,456 in / 2,891 out ($0.009)
- **Input:** 6 test cases, route map for /checkout
- **Output:** 1 page object (CheckoutPage), 1 spec file (checkout.spec.ts)
- **Memory:** known testids [checkout-submit, checkout-email]
- **Cache:** miss
- **Errors:** none

### executor (14:32:20 — 8.1s)
- **Tokens:** 0 (no LLM call — runs subprocess)
- **Input:** 1 page object, 1 spec file
- **Output:** passed=false, 2 failed cases [tc-checkout-01, tc-checkout-04]
- **Route changes:** /checkout +1
- **Test results recorded:** 6 tests (4 pass, 2 fail)
- **Errors:** none

### triage (14:32:28 — 3.2s)
- **Model:** claude-opus-4-20250514
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
1. Records the timestamp + input state summary before the node runs
2. Wraps the LLM call to capture token usage and duration
3. Records the output + routing decision after the node returns
4. Appends the entry to AUDIT_TRAIL.md
5. If an exception occurs, records the error and re-raises

### Token tracking integration

The decorator hooks into `langchain-anthropic`'s callback system to capture actual token counts from Claude's response metadata — not estimates.

```python
class AuditCallback(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs):
        self.input_tokens = response.llm_output["usage"]["input_tokens"]
        self.output_tokens = response.llm_output["usage"]["output_tokens"]
```

### Cost estimation

```python
# Claude pricing (per 1M tokens)
COST_MAP = {
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
}
```

### Run ID generation

Each graph invocation gets a unique run ID (e.g. `run-47`) that links the audit trail to `RUN_HISTORY.md`. The run ID is stored in the graph config's `thread_id`.

---

## D. What Each Node Logs

| Node | Special fields |
|------|---------------|
| **Design Reader** | Figma ref, element count, flow count |
| **Planner** | AC count, test case count, tags generated |
| **Generator** | Page object count, spec file count, locator types used |
| **Executor** | Pass/fail per test, route changes, fix verifications |
| **Triage** | Rubric breakdown (C1-C5), similar failure match, routing decision |
| **Healer** | Cache hit/miss, fix applied, guardrail result |
| **Human Review** | Decision (heal/defect), reasoning, time waiting for human |
| **Defect Report** | Jira ticket key, fingerprint, dedup result |
| **Metrics** | Run ID recorded, triage call ID recorded |

---

## E. Queryable Summaries

### Per-run cost report

```bash
qa-agent audit run-47          # Show full audit trail for run 47
qa-agent audit cost            # Total cost this week
qa-agent audit slow            # Nodes that took >10s
qa-agent audit tokens          # Token usage by node
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
```

---

## F. Build Phases

### Phase AT1 — Core audit decorator + logging
**Goal:** Every node automatically logs inputs, outputs, duration, and errors.

| # | Task | Status |
|---|------|--------|
| 1 | `qa_agent/audit.py` — `@audit_node` decorator with timing + input/output capture | TODO |
| 2 | `memory/AUDIT_TRAIL.md` — append-only log file | TODO |
| 3 | State summary helper — truncate large fields for readable logging | TODO |
| 4 | Apply decorator to all 8 nodes (non-invasive, no logic changes) | TODO |
| 5 | Run ID generation from graph config thread_id | TODO |
| 6 | Error capture — log exceptions before re-raising | TODO |

**Tests:**
- Unit: decorator captures timing and writes to AUDIT_TRAIL.md
- Unit: input/output summaries are truncated to readable length
- Unit: errors are logged and re-raised (not swallowed)
- Unit: run ID links to RUN_HISTORY.md
- Integration: full graph run produces a complete audit trail

**Done when:** Every node invocation is logged with timestamp, duration, inputs, outputs, and errors.

---

### Phase AT2 — Token tracking + cost estimation
**Goal:** Every LLM call logs actual token usage and estimated cost.

| # | Task | Status |
|---|------|--------|
| 1 | LangChain callback handler to capture token counts from Claude response metadata | TODO |
| 2 | Cost estimation using per-model pricing table | TODO |
| 3 | Token/cost fields in audit entries | TODO |
| 4 | Run summary with total tokens and cost | TODO |
| 5 | Integration with `budget.py` — audit records whether budget was checked/exhausted | TODO |

**Tests:**
- Unit: callback captures token counts from mocked LLM response
- Unit: cost estimation correct for Opus and Sonnet
- Unit: run summary totals are accurate
- Integration: full run audit shows token usage per node

**Done when:** Every LLM call logs actual token counts and estimated cost.

---

### Phase AT3 — Memory + routing context
**Goal:** Audit trail shows what memory was injected and why the router made its decision.

| # | Task | Status |
|---|------|--------|
| 1 | Log memory context size (tokens) injected into each node | TODO |
| 2 | Log which memory files were read (locators, failures, human decisions, lessons) | TODO |
| 3 | Log cache hit/miss for Healer known-fix path | TODO |
| 4 | Log routing decision with reasoning (which condition triggered) | TODO |
| 5 | Log rubric breakdown for Triage (C1-C5 scores, guards applied) | TODO |

**Tests:**
- Unit: memory context logged with source files listed
- Unit: cache hit/miss recorded correctly
- Unit: routing decision includes the condition that matched
- Unit: rubric breakdown appears in Triage audit entry

**Done when:** Audit trail shows the complete decision context — what memory influenced the agent and why the router chose the next node.

---

### Phase AT4 — CLI queries + weekly review integration
**Goal:** Queryable audit data + cost/performance insights in the weekly review.

| # | Task | Status |
|---|------|--------|
| 1 | `qa-agent audit <run-id>` — show full audit trail for a run | TODO |
| 2 | `qa-agent audit cost` — total cost this week | TODO |
| 3 | `qa-agent audit slow` — nodes that exceeded time threshold | TODO |
| 4 | `qa-agent audit tokens` — token usage breakdown by node | TODO |
| 5 | Weekly review integration — cost, duration, and error counts in the review | TODO |
| 6 | AUDIT_TRAIL.md rotation — archive old entries to prevent unbounded growth | TODO |

**Tests:**
- Unit: CLI commands parse audit trail correctly
- Unit: cost aggregation across runs is accurate
- Unit: slow node detection uses configurable threshold
- Integration: weekly review includes audit-derived metrics

**Done when:** Audit data is queryable via CLI and feeds into the weekly review.

---

## G. Assumptions

- Storage is `memory/AUDIT_TRAIL.md` — same markdown convention as all other memory files.
- The decorator is non-invasive — applied to existing node functions without changing their logic.
- Token counts come from Claude's response metadata (actual, not estimated).
- Cost estimation uses a static pricing table updated manually when Claude pricing changes.
- Audit entries are append-only. Rotation/archival handled in Phase AT4.
- The audit trail is git-tracked like all other memory files.

## H. Not in Scope

- Real-time streaming dashboard (CLI queries are sufficient for v1)
- Distributed tracing (single-process only — no microservices)
- LangSmith integration (this is a self-contained alternative)
- Billing/invoicing from audit data
- Automated cost alerts (use the existing observability module for alerts)

## I. Success Metrics

| Metric | How to measure | Target |
|--------|---------------|--------|
| Audit coverage | Nodes with audit decorator / total nodes | 100% (all 8 nodes) |
| Debugging time | Time to diagnose a bad run (before vs after) | 80% reduction |
| Cost visibility | Can answer "how much did run X cost?" | Yes, within $0.001 |
| Token accuracy | Audit token count vs Claude API dashboard | Within 1% |
| Performance overhead | Audit decorator latency | < 50ms per node (negligible) |
