# Pre-Mortem: Audit Trail + Eval Agent

> It's 8 weeks from now. The Audit Trail and Eval Agent are built but the project is considered a failure. What went wrong?

**Status:** Pre-build risk analysis
**Covers:** AGENT_AUDIT_TRAIL.md, BUILD_SPEC_EVAL_AGENT.md
**Date:** 2026-08-30

---

## Risk 1: Performance Overhead Kills Adoption

**What went wrong:** The audit trail adds 3-5s overhead per node (file writes, git hash lookups, callback hooks). With 6-8 nodes per run, that's 20-40s of pure audit overhead on a pipeline that currently takes ~35s. Runs feel sluggish. The team disables audit logging.

**Likelihood:** High
**Impact:** Fatal — no audit data means no evals

**Mitigations:**
1. Async file writes — audit entries queued and flushed after the node returns, not blocking the pipeline
2. Git hash caching — compute prompt hashes once at startup, not per-call
3. Lazy JSON serialization — only serialize raw prompt/response if the run fails or is tagged for eval
4. Performance budget: audit overhead must be <100ms per node (measured, not assumed)

**Build change:** Add a benchmark test in Phase AT1 that asserts audit overhead < 100ms. If it fails, the implementation approach is wrong.

---

## Risk 2: Audit Data Noise Drowns the Signal

**What went wrong:** Raw prompts and responses are massive (~2K tokens per LLM call). After 100 runs, `audit_runs/` has hundreds of MB of JSON. Git becomes slow. Diffs are unreadable. Developers grep through noise to find the one relevant entry.

**Likelihood:** High
**Impact:** High — audit exists but nobody reads it

**Mitigations:**
1. Tiered storage — summary always written (markdown + compact JSON), raw prompt/response only written when: (a) run fails, (b) run is tagged for eval, or (c) `AUDIT_RAW=true` env var is set
2. Don't git-track `audit_runs/` JSON files — add to `.gitignore`, store locally only. The markdown summary is git-tracked for history
3. Rotation from day 1 — `AUDIT_TRAIL.md` rotated weekly to `memory/audit_archive/`. Only current week in the main file
4. Index file — `audit_runs/INDEX.json` with run_id, timestamp, outcome, node list. No need to open each run file for queries

**Build change:** Phase AT1 implements tiered storage from the start. No "add rotation later" — it's core.

---

## Risk 3: Golden Datasets Rot Within Weeks

**What went wrong:** Campingworld.com changes constantly. The `/financing` page disappeared during our build session. Product URLs expire. DOM structures shift. Golden datasets referencing specific pages, URLs, or DOM snapshots are invalid within 2-3 weeks. The eval suite shows 40% failure rate but it's all stale golden data, not real regressions.

**Likelihood:** Very High
**Impact:** High — eval results are untrustworthy, team ignores them

**Mitigations:**
1. Golden data must be abstract — test failure patterns, not specific URLs or DOM selectors. "A TimeoutError on a button locator" not "TimeoutError on /checkout Submit button"
2. Expiry dates on every golden entry — `valid_until: 2026-10-01`. The eval runner warns on expired goldens, skips them after 2 weeks past expiry
3. Golden refresh pipeline — monthly CLI command `eval-agent refresh-golden` that re-validates golden entries against the live site
4. Separate site-dependent goldens from logic-only goldens. Triage classification logic doesn't depend on the site; DOM snapshot tests do

**Build change:** Golden dataset schema includes `valid_until`, `site_dependent: bool`, and `abstract: bool` fields. Phase 2 golden creation includes expiry dates.

---

## Risk 4: Prompt Version Correlation Is Misleading

**What went wrong:** A prompt change and a site change happen on the same day. The eval shows triage accuracy dropped 15%. The team blames the prompt and reverts it. But the real cause was a site redesign that changed error patterns. The prompt was actually an improvement.

**Likelihood:** Medium
**Impact:** High — wrong decisions based on false correlations

**Mitigations:**
1. Site fingerprint — capture a hash of key page DOMs alongside each run. When the fingerprint changes, flag all metric shifts as "site change may be a factor"
2. Controlled experiments — prompt A/B comparisons must use the same golden inputs (replay), not live site runs, to isolate prompt impact from site variability
3. Require 3+ runs before calling a regression. Single-run drops are noise

**Build change:** Add `site_fingerprint` field to audit JSON. Phase AT1 captures it. Eval Agent's regression detector checks fingerprint stability before blaming a prompt change.

---

## Risk 5: Replay Isn't Deterministic

**What went wrong:** You replay a triage call with identical inputs and get a different confidence score (0.82 vs 0.71). The eval says "regression" but it's just LLM variance. Temperature=0 doesn't guarantee identical output — it only guarantees the most likely token at each step, which can shift with model updates.

**Likelihood:** High
**Impact:** Medium — noisy eval results, false regressions

**Mitigations:**
1. Variance bands — accept ±5% on any LLM-dependent metric. Only flag regressions outside the band
2. Multiple replay — replay N=3 times and use the median. If variance across replays exceeds 10%, flag the metric as "high variance" rather than "regression"
3. Freeze memory state during replay — replay must load the memory snapshot from the original run's timestamp, not current memory. Otherwise memory growth changes results
4. Pin model version — replay uses the exact model from the audit entry, not the current default

**Build change:** `replay_node()` in Phase AT4 takes a `runs=3` parameter and returns median + variance. Memory snapshot capture added to audit JSON (or a pointer to the memory state at that timestamp).

---

## Risk 6: Thresholds Are Arbitrary

**What went wrong:** We set AC Coverage ≥90% and Triage Accuracy ≥85% before measuring baseline performance. Actual baseline is 65% and 70%. Everything fails. The team either (a) lowers thresholds to make things green, making the eval meaningless, or (b) spends weeks fixing agents before they can use the eval, killing momentum.

**Likelihood:** Very High
**Impact:** High — eval is either meaningless or blocking

**Mitigations:**
1. Phase 1 is baseline measurement only — no pass/fail. Run evals, record results, observe distributions
2. Set thresholds at p25 of baseline (bottom quartile). This means 75% of current runs pass immediately, and the eval catches genuine regressions
3. Thresholds are config, not code — stored in `eval/config.py` and tuned after 2 weeks of baseline data
4. Two threshold levels: WARN (p25) and FAIL (p10). WARN logs, FAIL blocks

**Build change:** Add a `--baseline` mode to the eval runner that records metrics without pass/fail judgment. Phase 2 runs in baseline mode for 2 weeks before setting thresholds.

---

## Risk 7: Markdown Storage Doesn't Scale

**What went wrong:** `memory/AUDIT_TRAIL.md` grows unbounded. After 500 runs with 8 nodes each, it's 4000+ entries. The MemoryStore's `fcntl` file locking causes contention with 4 parallel workers writing audit entries simultaneously. Markdown parsing becomes a bottleneck for the Eval Agent's `query_runs()`.

**Likelihood:** Medium
**Impact:** Medium — slow queries, occasional lock contention

**Mitigations:**
1. Markdown is human summary only — kept small via weekly rotation. The actual data store is JSON files (one per run)
2. JSON files are independent — no locking needed since each run writes its own file
3. Index file (`audit_runs/INDEX.json`) for fast queries without scanning all run files. Updated with append (not read-modify-write) to avoid lock contention
4. Cap: if `audit_runs/` exceeds 1000 files, archive old runs to `audit_runs/archive/YYYY-MM/`

**Build change:** JSON-per-run is the primary store. Markdown is a secondary view generated from JSON, not the source of truth. This is a reversal from the current spec where markdown is the primary format.

---

## Risk 8: Can't Eval What We Can't Observe

**What went wrong:** Half the eval metrics require data that doesn't exist in the code:
- DOM snapshots are `None` (executor doesn't capture them)
- Memory recall is single-result (no ranked retrieval)
- Orchestrator has zero instrumentation
- Healer guardrail results aren't recorded
- No timing on any node

The eval runs but 40% of metrics return "N/A — data not available."

**Likelihood:** Very High
**Impact:** High — partial eval gives false confidence

**Mitigations:**
1. Hard prerequisites list — these code changes MUST be done before the eval can measure them. No "we'll add it later"
2. Scope v1 eval to what's observable TODAY. Don't promise metrics we can't deliver
3. The Audit Trail decorator itself adds timing (duration_ms). That's one prerequisite solved by the audit build

**Prerequisites (must build before or alongside the eval):**

| Prerequisite | Where | Effort |
|---|---|---|
| DOM snapshot capture | executor.py | Small — capture snapshot after test run |
| Ranked memory retrieval | memory.py | Medium — change find_similar_failure to return top-N |
| Healer guardrail recording | healer.py | Small — log pass/fail to state |
| Orchestrator LLM tracking | orchestrator/ | Medium — wrap generate_pom/generate_tests |
| Node timing | audit.py | Free — comes with audit decorator |

**Build change:** Prerequisites are Phase 0 — built before Phase AT1. The eval spec's Prerequisites section becomes the first sprint.

---

## Risk 9: The Eval Agent Evaluates Itself (No Safety Net)

**What went wrong:** The eval produces a false negative — says triage regressed when it didn't. The team spends 2 days debugging a phantom regression. Or worse: a false positive — says everything is fine when triage accuracy actually dropped. A real bug ships.

**Likelihood:** Medium
**Impact:** High — trust in the eval system erodes

**Mitigations:**
1. Manual spot-checks for the first month — randomly sample 5 eval results per week and verify by hand
2. Eval-of-eval canaries — include 3 "known-good" and 3 "known-bad" runs in every eval suite. If a known-good fails or a known-bad passes, the eval itself is broken
3. Separate eval reliability metric — track "eval result flipped on re-run" rate. If >10%, the eval is too noisy

**Build change:** Phase 3 includes canary runs. The eval suite always runs canaries first; if canaries fail, the rest of the suite is skipped and an alert fires.

---

## Risk 10: Build Order Creates a Multi-Week Blocker

**What went wrong:** The Audit Trail is a prerequisite for the Eval Agent. The Eval Agent is a prerequisite for measuring the system. The prerequisites (DOM snapshots, ranked retrieval) are prerequisites for the Audit Trail to be useful. That's 3 dependency layers. Nothing delivers value until everything is done.

**Likelihood:** High
**Impact:** High — no incremental value, project dies mid-build

**Mitigations:**
1. Vertical slices, not horizontal layers. Don't build "all of audit trail" then "all of eval." Build "audit + eval for triage" end-to-end first (1 week), then expand to other agents
2. Start with the existing `run_eval.py` — it already has 3 metrics. Expand it incrementally rather than replacing it
3. The orchestrator tests (our 127 Playwright tests) are already a form of eval for the generator + orchestrator. Use them as-is while building the formal eval

**Revised build order:**
1. **Week 1:** Prerequisites (DOM snapshot, guardrail recording) + Audit decorator (timing + I/O only, no raw prompts)
2. **Week 2:** Audit for triage + triage eval (end-to-end for one agent)
3. **Week 3:** Expand audit + eval to healer and planner
4. **Week 4:** Expand to remaining agents + golden dataset creation
5. **Week 5:** Regression detection, dashboard, CI integration

**Build change:** Replace the current 5-week plan in both specs with the vertical slice approach above.

---

## Summary: Top 5 Actions Before Building

| # | Action | Addresses Risk |
|---|--------|---------------|
| 1 | Build prerequisites first (DOM snapshots, guardrail recording) | Risk 8 |
| 2 | Use vertical slices (triage end-to-end first) not horizontal layers | Risk 10 |
| 3 | Run baseline metrics for 2 weeks before setting thresholds | Risk 6 |
| 4 | Tiered storage from day 1 (summary always, raw on failure only) | Risk 2 |
| 5 | Golden data with expiry dates and abstract patterns, not specific URLs | Risk 3 |

---

## What This Pre-Mortem Does NOT Cover

- Security risks (audit data may contain API keys in prompts — need redaction)
- Cost of running evals (LLM calls for replay aren't free)
- Team adoption (who maintains golden data? who triages eval failures?)
- Integration with external CI/CD systems
