# Pre-Mortem: Eval Observability (Option B — In-House)

> 19 issues identified across concurrency, storage, accuracy, privacy, and UX. 5 HIGH, 9 MEDIUM, 5 LOW.

**Date:** 2026-09-04
**Scope:** Full Option B implementation (Phases EO1-EO4)

---

## Critical Theme

**The fundamental architectural mismatch between AuditStore's class-level shared state and the eval runner's concurrent execution model.** Issues #1, #2, and #15 all stem from this root cause. The tracer cannot simply "hook into" AuditStore — it needs an entirely separate per-scenario capture mechanism using `contextvars.ContextVar`.

---

## HIGH Severity (5)

### 1. Concurrent Trace Cross-Contamination via Shared AuditStore

`AuditStore._current_node_llm_calls` is a class-level list. With 5 concurrent scenarios, LLM calls from Scenario A appear in Scenario B's trace. Whichever scenario calls `_consume_llm_calls()` first gets all accumulated calls; subsequent scenarios get empty lists.

**Mitigation:** Use `contextvars.ContextVar` for per-asyncio-task trace buffers. Intercept `record_llm_call` and copy data to context-local buffer keyed by scenario ID.

### 2. Run-Level Token Accumulators Are Not Per-Scenario

`_run_total_input_tokens` etc. are class-level accumulators. No per-scenario token tracking exists. Even capturing from `response.usage_metadata` directly, the shared counters create race conditions.

**Mitigation:** Capture token data directly from `response.usage_metadata` at point of interception, independent of class-level accumulators.

### 3. Trace Files Will Bloat the Git Repository

Each scenario trace is 8-12KB. A full EVAL ALL produces ~800KB of traces. After 50 runs = 40MB in git history that can never be removed. Auto-commit mechanism would push traces to GitHub.

**Mitigation:** Do NOT git-track traces. Add `qa_agent/eval/traces/` to `.gitignore`. Implement retention policy (last 20 runs). Archive old traces as compressed files.

### 4. AUDIT_RAW Environment Gate Blocks Trace Capture by Default

`record_prompt_data()` only includes raw prompt/response when `AUDIT_RAW=true` env var is set. Without it, traces have null prompt data — defeating the entire purpose.

**Mitigation:** Tracer captures prompt/response independently via separate path, bypassing the `AUDIT_RAW` gate. Or force `AUDIT_RAW=true` during eval runs.

### 15. `_consume_llm_calls()` Clears State That the Tracer Needs

In eval mode, `_consume_llm_calls()` is never called (no `audit_node` decorator), so `_current_node_llm_calls` grows unbounded with 35 undifferentiated entries. Per-scenario attribution is impossible from this list.

**Mitigation:** Tracer must implement own per-scenario capture, completely independent of `_current_node_llm_calls`. Use `contextvars.ContextVar`.

---

## MEDIUM Severity (9)

### 5. Missing System Prompt in Traces

`record_prompt_data()` only captures the HumanMessage content, not the SystemMessage (TRIAGE.md). Without the system prompt, you can't debug classification logic changes.

**Mitigation:** Capture full message list (system + human) in trace, or capture system prompt hash + content separately.

### 6. Experiment Comparison Breaks on Scenario Renames

If a scenario is renamed between runs, comparison reports it as "removed" + "new" instead of tracking continuity.

**Mitigation:** Include stable scenario IDs separate from names. Or implement fuzzy matching. Warn when comparing runs with different scenario counts.

### 7. Dashboard Performance with Large Tables on Mobile

35+ rows with heat map coloring, expandable details, `backdrop-filter: blur()` causes jank on iPhone. Horizontal scroll with sticky columns + glass effects = dropped frames.

**Mitigation:** Virtual scrolling (render visible rows only). Disable `backdrop-filter` on mobile. Paginate table (10 rows/page). Test on real iPhone hardware early.

### 8. Healer/Generator Traces Have Different Structure Than Triage

Generator may make multiple LLM calls per scenario. Healer may retry. Single-call trace format doesn't capture which call produced which artifact.

**Mitigation:** Annotate each call with `purpose` field ("pom_generation", "test_generation"). Accept per-agent rendering logic in trace viewer.

### 9. Empty Traces for Error Scenarios

If exception occurs before LLM call (e.g., corrupt memory file), trace has empty `calls[]`, no prompt, no response. Trace viewer shows blank panel.

**Mitigation:** Capture prompt BEFORE the LLM call. Record exception message + stack trace. Differentiate pre-call, call timeout, and post-call parse errors.

### 10. Per-Scenario Cost Inaccuracy with Prompt Caching

`estimate_cost()` uses single input price, but Anthropic's `cache_read_input_tokens` are priced at 10% of regular rate. Per-scenario costs are systematically overstated.

**Mitigation:** Capture `cache_read_input_tokens` and `cache_creation_input_tokens` from `response.usage_metadata`. Use differentiated pricing.

### 11. No Trace Cleanup / Retention Policy

Traces accumulate indefinitely. After 3 months = 500+ files, 500MB on disk. Experiments endpoint scans all files, getting slower.

**Mitigation:** Keep last 20 runs per agent (or last 30 days). Add `qa-agent eval cleanup` CLI command. Make retention configurable.

### 12. Privacy of Full Prompts in Traces

Prompts contain error messages with server URLs, DOM snapshots with potential PII, memory context with internal decisions. Served unencrypted via unauthenticated API endpoint.

**Mitigation:** Sanitize PII via `sanitizer.py` before storing. Don't git-track traces. Ensure trace API is localhost-only.

### 13. Scorecard Structure Varies by Agent

Comparison engine needs to diff per-scenario for triage, per-sub-metric for generator, per-fix for healer. A single generic diff misses sub-metric regressions.

**Mitigation:** Per-agent comparison strategies. Triage: per-scenario class diff. Generator: per-sub-metric diff. Healer: per-scenario fix + per-metric diff.

---

## LOW Severity (5)

### 14. Progress Counter Race Condition

`_triage_done[0] += 1` is not atomic with 5 concurrent tasks. Dashboard may show duplicate progress numbers.

**Mitigation:** Use `asyncio.Lock` around increment. Cosmetic but undermines confidence in tracing accuracy.

### 16. No API Pagination or Caching

Scanning 500+ scorecard files on every `/api/eval/experiments` request. Gets slow over time.

**Mitigation:** Cache experiments list in memory with file-watcher invalidation. Add pagination. Maintain index file.

### 17. Diff View Can't Handle Asymmetric Agent Columns

Triage columns (Class/Confidence) are meaningless for generator comparison (Locator/POM/Test/Import). Diff view needs per-agent templates.

**Mitigation:** Return agent-typed comparison data from API. Frontend renders per-agent column layout.

### 18. Interrupted Eval Leaves Orphaned Partial Traces

If eval is stopped mid-run, some traces exist without a scorecard. Experiments list shows a run with no score.

**Mitigation:** Write traces only after all scenarios complete (batch), or mark partial runs with `"complete": false` metadata.

### 19. No Authentication on Trace API Endpoints

`GET /api/eval/trace/{run_id}/{scenario}` serves full prompts over HTTP with no auth. Accessible to any process on localhost or network.

**Mitigation:** Add warning to spec. Consider API key or localhost-only binding for trace endpoints.

---

## Pre-Mortem Tracker

| # | Issue | Severity | Status | When |
|---|-------|----------|--------|------|
| 1 | Concurrent trace cross-contamination | HIGH | OPEN | P0 — fix before Phase EO1 (use contextvars) |
| 2 | No per-scenario token accumulators | HIGH | OPEN | P0 — fix in Phase EO1 (capture from response directly) |
| 3 | Git repo bloat from trace files | HIGH | OPEN | P0 — add to .gitignore before first trace |
| 4 | AUDIT_RAW blocks trace capture | HIGH | OPEN | P0 — bypass gate in tracer |
| 5 | Missing system prompt in traces | MEDIUM | OPEN | Phase EO1 — capture full message list |
| 6 | Scenario rename breaks comparison | MEDIUM | OPEN | Phase EO2 — add stable IDs |
| 7 | Mobile table performance | MEDIUM | OPEN | Phase EO3 — virtual scrolling, test on iPhone |
| 8 | Multi-agent trace format | MEDIUM | OPEN | Phase EO1 — add purpose field per call |
| 9 | Empty traces for errors | MEDIUM | OPEN | Phase EO1 — capture prompt before call |
| 10 | Cost inaccuracy with caching | MEDIUM | OPEN | Phase EO1 — capture cache tokens |
| 11 | No trace cleanup | MEDIUM | OPEN | Phase EO1 — retention policy |
| 12 | Privacy in traces | MEDIUM | OPEN | Phase EO1 — sanitize before storing |
| 13 | Scorecard structure variance | MEDIUM | OPEN | Phase EO2 — per-agent comparison |
| 14 | Progress counter race | LOW | OPEN | Phase EO1 — asyncio.Lock |
| 15 | _consume_llm_calls conflict | HIGH | OPEN | P0 — independent capture mechanism |
| 16 | No API pagination | LOW | OPEN | Phase EO3 — cache + paginate |
| 17 | Asymmetric diff columns | LOW | OPEN | Phase EO3 — per-agent templates |
| 18 | Orphaned partial traces | LOW | OPEN | Phase EO1 — batch write or mark partial |
| 19 | No auth on trace API | LOW | OPEN | Phase EO4 — localhost binding |

**P0 items — architectural decisions to address during build (no code exists yet):**
- #1, #2, #15: Build the tracer with `contextvars.ContextVar` from the start — never use AuditStore's shared class-level state for per-scenario capture
- #3: Add `qa_agent/eval/traces/` to `.gitignore` on day one — never git-track traces
- #4: Design the tracer to capture prompts/responses independently of the `AUDIT_RAW` gate

**Progress: 0/19 addressed (0%) — all items are design constraints for the build, not fixes to existing code**

---

## Lessons Applied from Retrospective Agent Pre-Mortem

The [Retrospective Agent pre-mortem](PRE_MORTEM_RETROSPECTIVE_AGENT.md) identified 22 issues, 6 of which were fixed before building. Key lessons that apply to this feature:

### Shared State Concurrency (Retrospective #4 → Eval Obs #1, #2, #15)

The Retrospective Agent pre-mortem found a **two-source-of-truth problem** when syncing local memory files with the Dreaming memory store (#4). The same pattern appears here — AuditStore's class-level shared state creates a single-source-of-truth problem when 5 concurrent scenarios try to use it simultaneously. The mitigation is the same principle: **isolate state per operation** (three-way merge for Retrospective, `contextvars` for Eval Observability).

### Git Repo Bloat (Retrospective #1 → Eval Obs #3)

The Retrospective pre-mortem found TIMING_FIXES.md had 100 duplicate rows bloating the repo (#1). The same risk exists here at much larger scale — full LLM traces at 8-12KB per scenario would add ~800KB per eval run. The fix is the same principle: **don't git-track high-volume generated data**. TIMING_FIXES.md was deduped; traces should be `.gitignore`'d entirely.

### Data Quality Before Analysis (Retrospective #1, #2 → Eval Obs #9, #10)

The Retrospective pre-mortem emphasized that analysis on bad data produces bad recommendations (duplicated TIMING_FIXES poisoned statistics). The same applies here — empty traces (#9) and inaccurate costs (#10) would undermine the experiment comparison's value. Fix: **validate trace completeness before storing**, same as dedup was added to memory writes.

### Regression Threshold Sensitivity (Retrospective #15 → Eval Obs #6)

The Retrospective pre-mortem found the "any amount" eval drop threshold was too strict (#15, fixed by changing to 2%). The experiment comparison engine faces a similar sensitivity — scenario renames (#6) could trigger false regression alerts. Fix: **use stable IDs and fuzzy matching**, same principle as adding tolerance to regression detection.

### Rollback Safety (Retrospective #6 → Eval Obs #18)

The Retrospective pre-mortem found `git reset --hard` was dangerous for rollbacks (#6, fixed by using `git revert`). The Eval Observability feature has a similar orphaned-state problem — interrupted evals leave partial traces (#18). Fix: **batch write traces or mark as partial**, same principle as clean rollback without data loss.

### Privacy / Sensitivity (Retrospective #12 → Eval Obs #12)

Not explicitly in the Retrospective pre-mortem, but the enriched triage reports (#2) contain full error messages, C1-C5 breakdowns, and reasoning. Eval Observability traces contain even more sensitive data — full LLM prompts with DOM snapshots and memory context. Fix: **sanitize before storing**, use existing `sanitizer.py`.

### Stale State Auto-Recovery (Dashboard eval stuck → Eval Obs #18)

We already hit the problem of eval state getting stuck at "running" when a CLI eval was interrupted (fixed with 5-minute auto-reset). The same pattern applies to partial traces — the system must self-recover from interrupted operations, not leave zombie state.
