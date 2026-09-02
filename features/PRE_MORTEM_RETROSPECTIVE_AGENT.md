# Pre-Mortem: Retrospective Agent

> 22 issues identified across data quality, Dreaming API, memory sync, auto-apply safety, cost, and UX. 6 HIGH severity, 14 MEDIUM, 2 LOW.

**Date:** 2026-09-02
**Scope:** Full Retrospective Agent including Dreaming integration (Phase RA1-RA7)

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| **HIGH** | 6 | Data quality, API stability, memory sync, rollback safety |
| **MEDIUM** | 14 | Cost, latency, race conditions, feedback loops, validation |
| **LOW** | 2 | UX polish, observability |

---

## HIGH Severity Issues

### 1. TIMING_FIXES.md Already Full of Duplicates

**What goes wrong:** The current `TIMING_FIXES.md` contains 30+ duplicate rows — all from the same day, all with `Success: no`. The Retrospective Agent will compute "Strategy A has 0% success rate" based on massively duplicated entries. If Dreaming also ingests this, it amplifies the noise.

**Mitigation:** Deduplicate TIMING_FIXES.md now. Add dedup logic to the Healer's write path. Data loaders should deduplicate on `(date, route, element, strategy)` tuples before computing statistics.

### 2. Triage Reports Missing C1-C5 Breakdown Data

**What goes wrong:** Older triage reports store only `failure_class` and scalar `confidence`. The Retrospective Agent's "Confidence Rubric Gaps" analysis (e.g., "C2 is 0.00 in 78% of runs") requires per-criterion scores that weren't persisted before our recent fix. Historical data can't be retroactively enriched.

**Mitigation:** We already fixed this (commit `21355f7` — triage now returns reasoning + breakdown). Going forward data is rich. For historical analysis, the Retrospective Agent should note "insufficient C1-C5 data for runs before 2026-08-31" rather than computing on empty fields.

### 3. Dreaming API Is Research Preview — May Change or Disappear

**What goes wrong:** Research preview APIs can change schemas, rate limits, billing, and availability without notice. Building a deep integration that breaks when the API changes.

**Mitigation:** Build a `DreamProvider` abstraction layer. Ensure Phase RA1 + RA2 (rule-based + local LLM) work as a fully functional standalone mode, not just a fallback. Treat Dreaming as an enhancement, not a dependency.

### 4. Memory Sync Creates Two-Source-of-Truth Problem

**What goes wrong:** Local `memory/` files and the remote Dreaming memory store can diverge. If an agent writes to `FAILURES.md` during a Dream cycle, those changes get silently overwritten when Dream writes back its "optimized" version.

**Mitigation:** Use a lock file to prevent memory writes during Dream cycles. On write-back, perform a three-way merge (pre-dream snapshot vs. current state vs. dream output). Show the diff on the dashboard before applying memory changes.

### 5. Eval Gate Doesn't Catch All Regression Types

**What goes wrong:** A surgical fix passes the agent's eval (35 scenarios) but introduces a regression for an edge case not in the eval suite. Example: adding a flake pattern that also matches real app defects.

**Mitigation:** Require "counter-example checks" — confirm that known app_defect errors are NOT matched by new patterns. Consider requiring N successful test runs (not just one eval) before confirming a fix.

### 6. `git reset --hard` + `--force-with-lease` in Rollback Is Dangerous

**What goes wrong:** Level 2 rollback rewrites public history. If someone else pushed commits between the original push and the rollback, `--force-with-lease` fails and the local repo diverges from remote.

**Mitigation:** Always use `git revert` instead of `git reset --hard`, even in catastrophic cases. The commit was already made — reverting is cleaner than rewriting history. Reserve hard reset only for truly corrupt working tree states.

---

## MEDIUM Severity Issues

### 7. Dreaming Latency Makes Dashboard UX Awkward

**What goes wrong:** Dreaming takes minutes to hours. User clicks RUN, nothing happens. If browser closes, no notification when Dream completes.

**Mitigation:** Persist job status to disk (survives server restarts). Add email/Slack notification on completion. Show estimated completion time. Consider running Dreams as background cron jobs.

### 8. Session Transcript Format Is Lossy

**What goes wrong:** Converting structured JSON to natural language prose loses precision. The LLM has to parse prose back into structured understanding.

**Mitigation:** Include raw JSON as code blocks within transcripts rather than converting to prose. Use the memory store for structured data, transcripts for narrative context only.

### 9. Feedback Loop Can Compound Bad Decisions

**What goes wrong:** Adding more flake patterns "improves" the unhealed count (fewer unhealed) but actually hides real defects. Each retrospective cycle reinforces the bad pattern.

**Mitigation:** Track "escape rate" — defects misclassified as non-defects. Add false-negative rate metric. Require periodic human audit. Add "confidence decay" — if a recommendation's benefit can't be confirmed after N runs, flag it for review.

### 10. HEALER_STATS Lacks Root Cause Data

**What goes wrong:** Shows 0 cache hits / 409 LLM calls. The Retrospective Agent recommends "redesign caching" when the real fix is "fix the cache key hash." Can't distinguish broken cache from unique-inputs-every-time.

**Mitigation:** Enrich HEALER_STATS.md with cache miss reasons (key not found, key found but stale, key computation error).

### 11. Suppression List Grows Unboundedly

**What goes wrong:** Rejected recommendations are permanently suppressed. Valid recommendations rejected in one context (page temporarily down) are blocked forever.

**Mitigation:** Add 30-day expiration to suppression entries. Use structured matching (file + line + change type). Allow users to view and clear suppression entries from dashboard.

### 12. Concurrent Operations Create Race Conditions

**What goes wrong:** Retrospective runs while tests run while healer modifies memory files. A surgical fix applied while Playwright is executing the same spec.

**Mitigation:** Add operation locks on critical resources. Dashboard shows "Retrospective in progress — some actions locked." Queue surgical fix applications until no test run is active.

### 13. Build Spec Generation Quality Is Unvalidated

**What goes wrong:** LLM generates a spec with hallucinated file paths, wrong module descriptions, or vague instructions. Auto-committed to git as noise.

**Mitigation:** Don't auto-commit generated specs. Save as drafts. Validate file paths exist. Add a "spec quality checklist" and surface warnings.

### 14. Dreaming Cost Is Unbounded

**What goes wrong:** 100 transcripts on Opus could cost $5-20 per Dream cycle. If retrospective runs every 10 test runs, costs exceed all other agent operations.

**Mitigation:** Add per-Dream cost cap ($5 max). Track Dreaming costs separately in audit trail. Add dashboard widget for cumulative Dream spend. Consider Sonnet for Dreaming given structured data.

### 15. "Any Amount" Eval Score Drop Is Too Strict

**What goes wrong:** Eval scores have natural variance (±1-2% between runs). A good fix gets reverted because the eval score dropped 0.1% due to LLM non-determinism.

**Mitigation:** Use a regression threshold (score drops > 2% or > 1 standard deviation). Run eval twice and average. Store historical eval variance.

### 16. Insufficient Data Produces Misleading Recommendations

**What goes wrong:** Only 1-2 days of data. "Strategy A has 0% success rate" based on 5 attempts on a single day is not meaningful.

**Mitigation:** Minimum data requirements before producing recommendations. Require N runs over M days. Show "low confidence — insufficient data" warnings. Skip dimensions below threshold.

### 17. File Allowlist Too Broad for Auto-Apply

**What goes wrong:** Allowlist permits modifications to any file in `qa_agent/`, including server.py, cli.py, eval infrastructure. A bad single-line change to server code takes down the dashboard.

**Mitigation:** Narrow to specific files: `confidence.py`, `memory.py`, `memory/*.md`, `tests_generated/*.spec.ts`, `playwright.config.ts`, prompt files. Explicitly exclude server, CLI, and eval infrastructure.

### 19. Dreaming Write-Back Could Corrupt Markdown Format

**What goes wrong:** Memory files use specific markdown table formats parsed by regex. If Dreaming's output uses different column order, headers, or date formats, downstream agents break silently.

**Mitigation:** Define strict schemas per memory file. Validate Dreaming output against schema before applying. If validation fails, reject the update.

### 21. WebSocket Single Point of Failure for Approval State

**What goes wrong:** Server restarts during an approval operation. Connection list wiped, status lost. Applied change committed but eval never runs, or eval fails but revert never triggers.

**Mitigation:** Persist approval operation state to disk (JSON). On reconnect, poll `/api/retro/status` to recover. Make approval flow idempotent.

### 22. Dreaming Cannot Produce File-Line Code Recommendations

**What goes wrong:** Dreaming processes transcripts and memory — it doesn't have access to actual source code. It can't know what line 92 of confidence.py contains.

**Mitigation:** Keep file/line-level recommendation generation in Phase RA2 (local LLM with source code access). Use Dreaming only for high-level pattern identification and memory optimization.

---

## LOW Severity Issues

### 18. MODIFY Flow Under-Specified

**What goes wrong:** User edits a code diff in a plain textarea, introduces syntax errors. No validation before committing.

**Mitigation:** Show file preview with change applied. Run syntax check (Python AST, TypeScript compiler). Use a code editor widget (Monaco) instead of textarea.

### 20. No Observability Into Recommendation Provenance

**What goes wrong:** User sees a recommendation but can't verify the chain of reasoning. No way to debug why it was generated.

**Mitigation:** Include full provenance trail per recommendation: which reports, which entries, exact filters, raw numbers. Add "Show Evidence" expandable section.

---

## Action Items Before Building

| Priority | Action | Addresses Issues |
|----------|--------|-----------------|
| **P0** | Deduplicate TIMING_FIXES.md + add dedup to write path | #1 |
| **P0** | Verify triage reports now include C1-C5 breakdown | #2 |
| **P0** | Change rollback from `git reset --hard` to `git revert` | #6 |
| **P1** | Build DreamProvider abstraction (not direct API calls) | #3 |
| **P1** | Design three-way merge for memory write-back | #4 |
| **P1** | Add counter-example checks to eval gate | #5 |
| **P1** | Narrow file allowlist for auto-apply | #17 |
| **P1** | Add regression threshold (not "any amount") | #15 |
| **P1** | Add minimum data requirements for recommendations | #16 |
| **P2** | Persist approval state to disk | #21 |
| **P2** | Add Dreaming cost cap | #14 |
| **P2** | Add suppression list expiration | #11 |
| **P2** | Add operation locks for concurrent access | #12 |
