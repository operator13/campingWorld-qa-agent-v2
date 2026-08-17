# Feature: Agent Memory

> Cross-run learning — agents remember past failures, fixes, and app patterns so they get better over time instead of starting cold every run.

**Status:** PLANNED
**Priority:** High
**Depends on:** Core framework (Phases 0-4) complete

---

## The Problem

Today every run starts from zero. The Healer doesn't know that `#checkout-submit` drifted to `[data-testid="place-order"]` last week. The Planner doesn't know which routes break most often. Triage doesn't learn from human corrections. Each run pays the same discovery cost as the first.

## The Solution

A persistent memory layer stored as **git-tracked markdown files** — human-readable, editable, reviewable in PRs, and portable across environments. Every agent node can read from and write to memory, scoped by app, route, and element.

### Why markdown, not SQLite

Memory is a small knowledge base (hundreds of entries), not a transactional store. Markdown gives us:
- **Git history** — see how memory evolves over time
- **Human-editable** — fix a bad entry by editing a file
- **PR-reviewable** — memory changes show up in diffs
- **Inspectable** — no tools needed, just read it
- **Portable** — copy files between environments

SQLite remains the right choice for **metrics** (escape rate, triage accuracy, run aggregates) where volume and queries demand it. Memory and metrics are separate concerns.

---

## A. Memory Types

| Type | What it stores | Who writes | Who reads | File |
|------|---------------|------------|-----------|------|
| **Locator History** | Old → new selector mappings with timestamps | Healer | Healer, Generator | `memory/locators/{route}.md` |
| **Failure Patterns** | Recurring error signatures + what resolved them | Triage, Healer | Triage, Healer | `memory/failures.md` |
| **Human Decisions** | Every Human Review verdict + reasoning | Human Review | Triage (calibration) | `memory/human_decisions.md` |
| **App Structure** | Known routes, components, testid conventions | Generator, Executor | Planner, Generator | `memory/app_structure.md` |
| **Test Stability** | Per-test pass/fail history, flakiness scores | Metrics | Planner (prioritization) | `memory/test_stability.md` |

---

## B. File Formats

### `memory/locators/{route}.md` (one file per route)

```markdown
# Locator History: /checkout

## submitBtn
- 2026-07-18: `getByRole('button', {name: 'Submit'})` → `getByRole('button', {name: 'Place Order'})` | reason: button text changed | success: yes
- 2026-07-25: `getByRole('button', {name: 'Place Order'})` → `getByTestId('checkout-submit')` | reason: name keeps changing, switched to testid | success: yes
- 2026-08-10: `getByTestId('checkout-submit')` → `getByTestId('order-submit')` | reason: testid renamed | success: yes

**Pattern:** This button's name changes frequently. Prefer testid over name.

## emailInput
- 2026-08-01: `getByTestId('email')` → `getByTestId('checkout-email')` | reason: testid prefix added | success: yes
```

### `memory/failures.md`

```markdown
# Failure Patterns

## FP-001: Timeout on renamed button
- **Signature:** `TimeoutError.*getByRole\('button'.*name:.*\)`
- **Class:** locator_drift
- **Resolution:** healed — update button name in page object
- **Routes:** /checkout, /login
- **Occurrences:** 7
- **Last seen:** 2026-08-10
- **Stale after:** 2026-11-10

## FP-002: 500 on checkout submit
- **Signature:** `net::ERR_FAILED 500.*\/api\/checkout`
- **Class:** app_defect
- **Resolution:** defect filed — QA-456
- **Routes:** /checkout
- **Occurrences:** 2
- **Last seen:** 2026-08-05
- **Stale after:** 2026-11-05
```

### `memory/human_decisions.md`

```markdown
# Human Review Decisions

| Date | Error (summary) | Triage guess | Confidence | Human verdict | Reasoning |
|------|----------------|--------------|------------|---------------|-----------|
| 2026-08-12 | Timeout on 'Submit' button | locator_drift | 0.60 | heal | Button was renamed, not removed |
| 2026-08-11 | Assertion: expected 'OK' got '' | app_defect | 0.55 | defect | API returning empty response |
| 2026-08-09 | Element not found: cart-total | locator_drift | 0.45 | heal | Testid changed to order-total |
```

### `memory/app_structure.md`

```markdown
# App Structure

## /checkout
- **Last seen:** 2026-08-14
- **Change frequency:** 2.3/week (high)
- **Known testids:** checkout-submit, checkout-email, checkout-total
- **Components:** CartSummary, PaymentForm, OrderButton

## /login
- **Last seen:** 2026-08-14
- **Change frequency:** 0.1/week (stable)
- **Known testids:** login-email, login-password, login-submit
- **Components:** LoginForm, SocialAuth
```

### `memory/test_stability.md`

```markdown
# Test Stability

| Test ID | Route | Runs | Passes | Fails | Flakiness | Last run | Last failure |
|---------|-------|------|--------|-------|-----------|----------|-------------|
| tc-checkout-01 | /checkout | 30 | 27 | 3 | 0.10 | 2026-08-14 | locator_drift |
| tc-checkout-02 | /checkout | 30 | 30 | 0 | 0.00 | 2026-08-14 | — |
| tc-login-01 | /login | 30 | 22 | 8 | 0.27 | 2026-08-14 | locator_drift |
```

---

## C. Access Layer: `MemoryStore` class

Reads and writes the markdown files. Parses on read, formats on write.

```python
class MemoryStore:
    """Unified read/write interface for agent memory (markdown-backed)."""

    def __init__(self, memory_dir: str | Path = "memory/"): ...

    # --- Locator History ---
    def record_locator_change(self, route, element, old, new, reason, success): ...
    def get_locator_history(self, route, element_name=None) -> list[dict]: ...
    def get_known_fix(self, route, element, old_locator) -> str | None: ...
    def mark_fix_failed(self, route, element, old_locator): ...

    # --- Failure Patterns ---
    def record_failure(self, error_sig, failure_class, resolution, route): ...
    def find_similar_failure(self, error_sig) -> dict | None: ...

    # --- Human Decisions ---
    def record_human_decision(self, triage_guess, confidence, verdict, error_summary, reasoning=""): ...
    def get_triage_calibration(self, n=10) -> list[dict]: ...

    # --- App Structure ---
    def update_route(self, route, testids, components): ...
    def get_route_info(self, route) -> dict | None: ...
    def get_volatile_routes(self, threshold=1.0) -> list[str]: ...

    # --- Test Stability ---
    def record_test_result(self, test_id, route, passed, failure_class=None): ...
    def get_flaky_tests(self, threshold=0.2) -> list[dict]: ...

    # --- Maintenance ---
    def prune_stale(self, max_age_days=90) -> int: ...
    def stats(self) -> dict: ...
```

### Error signature normalization

`find_similar_failure()` needs to match error messages that vary in line numbers, file paths, and timestamps. The normalization algorithm:

```python
def normalize_error(error: str) -> str:
    """Strip volatile parts from an error message for pattern matching."""
    s = error
    s = re.sub(r"line \d+", "line N", s)
    s = re.sub(r"column \d+", "column N", s)
    s = re.sub(r"/[\w./\-]+\.(ts|js|py)", "FILE", s)
    s = re.sub(r"Timeout \d+ms", "Timeout Nms", s)
    s = re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", s)
    s = re.sub(r"\d+\.\d+\.\d+\.\d+", "IP", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
```

Matching uses substring containment on the normalized signature — not exact match.

### Locator extraction from errors

`get_known_fix()` needs to extract the locator from a Playwright error. The extraction:

```python
def extract_locator_from_error(error: str) -> str | None:
    """Extract the locator string from a Playwright timeout/not-found error."""
    patterns = [
        r"getByRole\([^)]+\)",
        r"getByTestId\([^)]+\)",
        r"getByText\([^)]+\)",
        r"getByLabel\([^)]+\)",
        r"locator\([^)]+\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, error)
        if match:
            return match.group(0)
    return None
```

---

## D. How Each Node Uses Memory

### Healer (biggest win)

**Before:** Tries to figure out the fix from scratch every time.
**After:**
1. Extracts the broken locator from the error message.
2. Checks `get_known_fix(route, element, old_locator)` — if this exact drift was fixed before, reuse it (no LLM call).
3. **Validates the known fix through the assertion guardrail** before applying.
4. If no known fix, checks `get_locator_history(route, element)` — shows the LLM how this element has evolved.
5. After a successful fix, calls `record_locator_change()`.
6. **After a failed fix, calls `mark_fix_failed()`** so stale fixes aren't reused.

```python
async def healer(state: QAState) -> dict:
    memory = MemoryStore()

    # Extract what broke
    old_locator = extract_locator_from_error(state.error)
    route = state.plan[0].route if state.plan else "/"
    element = _identify_element(old_locator)

    # Fast path: known fix from memory
    if old_locator:
        known_new = memory.get_known_fix(route, element, old_locator)
        if known_new:
            patched = apply_known_fix(known_new, old_locator, state.page_objects)
            # MUST validate through guardrail
            try:
                for r, src in patched.items():
                    validate_healer_diff(state.page_objects.get(r, ""), src)
                logger.info("Healer: applying known fix from memory")
                return {"page_objects": patched, "attempts": 1}
            except AssertionGuardError:
                logger.warning("Healer: known fix touches assertions — discarding")
                memory.mark_fix_failed(route, element, old_locator)

    # Slow path: ask LLM, with history context
    history = memory.get_locator_history(route, element)
    prompt = _build_prompt(state, locator_history=history)
    ...
    # After success:
    memory.record_locator_change(route, element, old_locator, new_locator, reason, success=True)
```

### Triage (calibration)

**Before:** Rates confidence based on rubric alone.
**After:**
1. Normalizes the error and calls `find_similar_failure()` — has this pattern been seen before?
2. Loads `get_triage_calibration(n=10)` — recent human corrections as few-shot examples.
3. If humans keep overriding Triage on a certain pattern, the examples naturally push confidence down.

### Planner (prioritization)

**Before:** Treats all routes equally.
**After:**
1. Checks `get_volatile_routes()` — routes that change >1x/week get `@smoke` priority.
2. Checks `get_flaky_tests()` — known flaky tests are flagged in the plan.
3. Uses `get_route_info()` for known testid conventions.

### Generator (selector grounding)

**Before:** Picks selectors based on the current DOM only.
**After:**
1. Checks `get_locator_history(route)` — avoids selectors that have drifted repeatedly.
2. Uses `get_route_info()` for known testid prefixes.

### Human Review (feedback storage)

**Before:** Decision is used once and forgotten.
**After:** Every verdict is stored via `record_human_decision()` with the error summary and reasoning.

### Metrics (stability tracking)

**Before:** Records pass/fail per run.
**After:** Also calls `record_test_result()` per test case, building a flakiness profile.

---

## E. Memory Injection into Prompts

Memory context is injected as a structured section, **capped at ~500 tokens**. When there's more relevant history than fits:

**Selection priority (most useful first):**
1. Known fixes for the exact element that broke (Healer)
2. Human corrections for similar errors (Triage)
3. Most recent entries over older entries
4. High-occurrence patterns over rare ones

**Truncation:** If selected memories exceed 500 tokens, drop the lowest-priority entries until it fits. Never inject partial entries.

Example for the Healer:

```
## Memory: Locator History for /checkout → submitBtn
This element has drifted 3 times in the past 30 days:
  2026-07-18: getByRole('button', {name: 'Submit'}) → getByRole('button', {name: 'Place Order'})
  2026-07-25: getByRole('button', {name: 'Place Order'}) → getByTestId('checkout-submit')
  2026-08-10: getByTestId('checkout-submit') → getByTestId('order-submit')

Pattern: this button's name changes frequently. Prefer testid over name.
```

---

## F. Safety & Controls

### Kill switch

```env
# .env — disable memory globally or per-node
MEMORY_ENABLED=true
HEALER_MEMORY=true
TRIAGE_MEMORY=true
PLANNER_MEMORY=true
GENERATOR_MEMORY=true
```

When disabled, the node skips all memory reads/writes and runs exactly as it did before memory existed. No code path changes — just an early return in `MemoryStore`.

### Known-fix validation

The Healer fast path **always** runs through `validate_healer_diff()`. If a cached fix now touches an assertion (because the page object was manually edited), it's rejected and marked as failed.

### Stale fix protection

Every locator history entry has a `success` flag. When a cached fix fails:
1. `mark_fix_failed()` sets `success: no` on that entry
2. `get_known_fix()` skips entries where `success: no`
3. The Healer falls through to the LLM slow path
4. If the LLM produces a different fix, it's recorded as a new entry

### Concurrent write safety

Markdown files use **append-only writes** within a single run. If parallel CI jobs share the same repo, memory updates arrive as separate git commits — git merge handles conflicts at the file level. For true concurrent access to the same file, writes are protected by a file lock (`fcntl.flock`).


---

## G. Build Phases

### Phase M1 — Storage + Healer memory [DONE]
**Goal:** Healer remembers past fixes and reuses them.

| # | Task | Status |
|---|------|--------|
| 1 | Create `memory/` directory structure + `.gitkeep` files | DONE |
| 2 | Implement `MemoryStore` class — markdown read/write, locator history methods | DONE |
| 3 | Implement `normalize_error()` and `extract_locator_from_error()` | DONE |
| 4 | Integrate into Healer — known-fix fast path **with guardrail validation** | DONE |
| 5 | Implement `mark_fix_failed()` for stale fix protection | DONE |
| 6 | Integrate into Healer prompt — inject locator history as context | DONE |
| 7 | Add `MEMORY_ENABLED` + `HEALER_MEMORY` kill switches to config | DONE |

**Tests:** 39/39 passing (commit `171be18`)

**Done when:** Healer reuses past fixes safely; stale fixes are caught; kill switch works. — **MET**

---

### Phase M2 — Triage calibration + Human Review storage [DONE]
**Goal:** Triage learns from human corrections.

| # | Task | Status |
|---|------|--------|
| 1 | `MemoryStore` — `record_human_decision()` writes to `HUMAN_DECISIONS.md` | DONE |
| 2 | `MemoryStore` — `get_triage_calibration(n=10)` reads last N decisions | DONE |
| 3 | Wire Human Review node to call `record_human_decision()` after each verdict | DONE |
| 4 | Inject calibration history into Triage prompt (with token cap) | DONE |
| 5 | `find_similar_failure()` using normalized signature substring matching | DONE |
| 6 | Add `TRIAGE_MEMORY` kill switch | DONE |

**Tests:** 14 new tests passing (commit `4d85764`)

**Done when:** Human verdicts are stored in markdown; Triage prompt includes recent corrections; similar failures are found. — **MET**

**Note:** This phase provides the *data storage* for Triage calibration. The *automatic threshold adjustment* (raising/lowering `CONF_SURE`) is owned by the [AUTO_THRESHOLD_TUNING](./AUTO_THRESHOLD_TUNING.md) feature — no overlap.

---

### Phase M3 — App structure + Planner intelligence
**Goal:** Planner knows which routes are volatile and which testids exist.

| # | Task | Status |
|---|------|--------|
| 1 | `MemoryStore` — `update_route()` writes/updates `app_structure.md` | TODO |
| 2 | `MemoryStore` — `get_volatile_routes(threshold)` filters by change frequency | TODO |
| 3 | `MemoryStore` — `record_test_result()` + `get_flaky_tests()` for `test_stability.md` | TODO |
| 4 | Define "change" for frequency calculation: a locator drift or test failure on that route | TODO |
| 5 | Executor calls `update_route()` after each run with discovered testids | TODO |
| 6 | Generator uses `get_route_info()` for known testid prefixes | TODO |
| 7 | Planner receives volatile routes + flaky tests in prompt | TODO |
| 8 | Add `PLANNER_MEMORY` + `GENERATOR_MEMORY` kill switches | TODO |

**Tests:**
- Unit: route info written and parsed from markdown
- Unit: change frequency calculated correctly (changes / weeks since first seen)
- Unit: flakiness score = fails / total_runs
- Unit: `get_volatile_routes()` returns routes above threshold
- Unit: `get_flaky_tests()` returns tests above threshold
- Unit: Planner prompt includes volatile routes section
- Integration: after 10 runs with 3 failures on /checkout, it's marked volatile

**Done when:** Routes have change-frequency scores; flaky tests identified; Planner prioritizes accordingly.

---

### Phase M4 — Memory maintenance
**Goal:** Memory stays useful — doesn't grow unbounded or go stale.

| # | Task | Status |
|---|------|--------|
| 1 | `prune_stale(max_age_days=90)` — remove entries older than TTL | TODO |
| 2 | Dedup — merge duplicate failure patterns (same normalized signature) | TODO |
| 3 | `stats()` — count entries per file, total size, oldest/newest entry | TODO |
| 4 | CLI commands: `qa-agent memory stats` / `qa-agent memory prune` | TODO |
| 5 | Memory stats in the observability dashboard | TODO |
| 6 | File lock for concurrent write safety (`fcntl.flock`) | TODO |

**Tests:**
- Unit: entries older than TTL are pruned
- Unit: duplicate failure patterns are merged (occurrences summed)
- Unit: stats returns correct counts
- Unit: file lock prevents corruption under concurrent writes
- Integration: memory size stays bounded after 100 simulated runs

**Done when:** Memory self-maintains; CLI can inspect and prune; concurrent writes are safe.

---

### Phase M5 — Lessons learned (inspired by trading_bot/LESSONS.md)
**Goal:** Agents synthesize strategic lessons from accumulated data — not just raw logs, but actionable insights.

**Why:** The trading bot tracks a **pattern scoreboard** (which strategies win most) and **per-trade reflections** (what was decided, why, what to do differently). Our system stores raw data (locator drifts, failure counts) but never asks "what did we learn?" The difference between "this element drifted 6 times" and "buttons on /checkout rename every deploy — always use testid" is the difference between data and wisdom.

| # | Task | Status |
|---|------|--------|
| 1 | Create `memory/LESSONS.md` — agent-generated insights from accumulated data | TODO |
| 2 | `MemoryStore` — `record_lesson()` writes structured lesson entries | TODO |
| 3 | `MemoryStore` — `get_lessons(route=None, node=None)` reads relevant lessons | TODO |
| 4 | Lesson generation: after every N runs (configurable), LLM reads raw memory and extracts patterns | TODO |
| 5 | **Pattern scoreboard**: track which failure types are most common, which fixes work best, which routes are most stable/unstable | TODO |
| 6 | **Decision reflections**: after each Triage + Healer cycle, record what was tried, whether it worked, and what to do differently | TODO |
| 7 | Inject relevant lessons into Healer, Triage, Planner, and Generator prompts | TODO |
| 8 | Add `LESSONS_MEMORY` kill switch | TODO |

**File format — `memory/LESSONS.md`:**
```markdown
# Lessons Learned

## Pattern Scoreboard
| Pattern | Occurrences | Success rate | Best strategy |
|---------|-------------|-------------|---------------|
| Button text rename | 12 | 100% heal | Use getByTestId, never getByRole name |
| Testid prefix change | 4 | 75% heal | Check if parent testid is stable |
| Element removed entirely | 3 | 0% heal (always defect) | Don't attempt heal — file immediately |
| HTTP 500 on submit | 5 | 0% heal (always defect) | High confidence app_defect |

## Route Insights
### /checkout
- **Stability:** LOW — locators change ~2x/week
- **Best locator strategy:** getByTestId (button names change constantly)
- **Common failure:** submit button renamed every deploy
- **Lesson:** Never use getByRole('button', {name: ...}) on this route

### /login
- **Stability:** HIGH — unchanged for 30+ runs
- **Best locator strategy:** getByRole works fine (names are stable)
- **Lesson:** No special handling needed

## Decision Reflections
### 2026-08-14 — /checkout submit button
- **Error:** Timeout on getByRole('button', {name: 'Submit'})
- **Triage said:** locator_drift (0.82) ✓ correct
- **Healer fix:** Changed to getByTestId('checkout-submit')
- **Outcome:** Passed on retry
- **Lesson recorded:** Submit button on /checkout uses changing labels — prefer testid
```

**Tests:**
- Unit: lesson entries written and parsed from markdown
- Unit: pattern scoreboard correctly aggregates from failure/locator history
- Unit: relevant lessons injected into prompts by route
- Unit: kill switch disables lesson reads/writes
- Integration: after 10 runs, meaningful lessons are generated

**Done when:** System produces actionable, synthesized insights — not just raw data — and injects them into agent prompts.

---

### Phase M6 — Weekly review (inspired by trading_bot/WEEKLY-REVIEW.md)
**Goal:** Automated periodic reviews that grade the system's performance and prescribe concrete adjustments.

**Why:** The trading bot does Friday reviews with stats tables, letter grades (C- to A-), and explicit prescriptions ("tighten stops on sector X"). Our system accumulates metrics but never steps back to ask "how did we do this week?" The weekly review closes the loop between measurement and action.

| # | Task | Status |
|---|------|--------|
| 1 | Create `memory/WEEKLY_REVIEW.md` — append-only weekly review entries | TODO |
| 2 | `MemoryStore` — `generate_weekly_review()` reads metrics + memory and produces a review | TODO |
| 3 | Review template: stats table, grades, open issues, prescriptions | TODO |
| 4 | **Grading rubric**: A (escape rate <5%, Triage >90%) through F (escape rate >20%, Triage <60%) | TODO |
| 5 | **Prescriptions**: concrete actions derived from grades ("raise CONF_SURE", "add tests for /dashboard") | TODO |
| 6 | CLI command: `qa-agent review weekly` | TODO |
| 7 | Auto-trigger: run after every 7th nightly run (or on cron) | TODO |
| 8 | Feed prescriptions into TPM agent as input for gap analysis | TODO |

**File format — `memory/WEEKLY_REVIEW.md`:**
```markdown
# Weekly Reviews

## Week of 2026-08-11

### Stats
| Metric | This week | Last week | Trend |
|--------|-----------|-----------|-------|
| Total runs | 7 | 7 | — |
| Pass rate | 71% (5/7) | 86% (6/7) | ↓ |
| Escape rate | 8% | 3% | ↑ BAD |
| Triage accuracy | 83% | 90% | ↓ |
| Healer cache hit | 40% | 25% | ↑ GOOD |
| Mean heal time | 12s | 28s | ↑ GOOD |

### Grade: B-
- Pass rate down, escape rate up — two bugs slipped through on /search
- Triage accuracy declining — 2 misclassifications on timeout errors
- Memory is working well — cache hits up, heal time halved

### Prescriptions
1. **Add test coverage for /search** — 2 escapes this week, 0 tests exist
2. **Refine Triage timeout rubric** — 2 misclassifications, both on ambiguous timeouts
3. **Keep current CONF_SURE (0.75)** — accuracy still above 0.70 threshold
4. **Review /checkout stability** — 3 locator drifts this week, consider notifying dev team
```

**Tests:**
- Unit: review generation produces all required sections (stats, grade, prescriptions)
- Unit: grading rubric maps metrics to correct letter grade
- Unit: prescriptions are concrete and data-backed
- Unit: trend comparison works (this week vs last week)
- Integration: after 7 simulated runs, a coherent weekly review is generated

**Done when:** System produces weekly self-assessments with grades and actionable prescriptions.

---

### Phase M7 — Confidence rubric (inspired by trading_bot/CONFIDENCE-SCORING.md)
**Goal:** Formalize Triage's confidence scoring with a multi-criteria rubric, worked examples, and anti-gaming guards.

**Why:** The trading bot uses a rigorous 5-criterion scoring system (0-5 scale) with worked examples, anti-loophole guards, and a kill switch. Our Triage just says "rate your confidence 0-1" — vague, uncalibrated, and inconsistent. Two identical errors could score 0.6 or 0.8 depending on the LLM's mood.

| # | Task | Status |
|---|------|--------|
| 1 | Create `memory/CONFIDENCE_RUBRIC.md` — the formal scoring rubric | TODO |
| 2 | Define 5 scoring criteria, each worth 0.0–0.2 (total 0.0–1.0) | TODO |
| 3 | Write worked examples for each confidence band (high, medium, low) | TODO |
| 4 | Add **anti-inflation guards**: rules that cap confidence in specific scenarios | TODO |
| 5 | Add **calibration feedback**: when humans override, adjust the rubric guidance | TODO |
| 6 | Inject the rubric into Triage's system prompt (replaces the current loose guidance) | TODO |
| 7 | Track rubric accuracy over time — does the formal rubric improve Triage vs the loose prompt? | TODO |

**File format — `memory/CONFIDENCE_RUBRIC.md`:**
```markdown
# Triage Confidence Rubric

## Scoring Criteria (each 0.0–0.2, total 0.0–1.0)

### C1: Error type signal (0.0–0.2)
- 0.2 — Clear signal: `selector-not-found` (drift) or `AssertionError: wrong value` (defect)
- 0.1 — Moderate signal: `TimeoutError` (could be either)
- 0.0 — No signal: generic error, no pattern match

### C2: DOM evidence (0.0–0.2)
- 0.2 — Element exists in DOM but with different selector/name (drift)
- 0.2 — Element completely absent AND no similar element (defect)
- 0.1 — Element partially matches (renamed but similar structure)
- 0.0 — No DOM snapshot available

### C3: Historical pattern match (0.0–0.2)
- 0.2 — Identical error signature seen before with known resolution
- 0.1 — Similar error on same route, different element
- 0.0 — No matching history

### C4: Human calibration alignment (0.0–0.2)
- 0.2 — Past human decisions agree with this classification
- 0.1 — Mixed human decisions on similar errors
- 0.0 — Humans have overridden this pattern before (reduce confidence)

### C5: Consistency check (0.0–0.2)
- 0.2 — Multiple independent signals agree (error type + DOM + history)
- 0.1 — Two signals agree, one contradicts
- 0.0 — Signals conflict or only one signal available

## Anti-Inflation Guards
- **Guard 1:** If this is the first time seeing this error pattern, cap at 0.7 regardless of criteria scores
- **Guard 2:** If humans have overridden this classification 2+ times, cap at 0.6
- **Guard 3:** If the DOM snapshot is unavailable, cap at 0.5
- **Guard 4:** TimeoutError alone (no DOM evidence) is never above 0.6

## Worked Examples

### Example A: High confidence locator_drift (0.90)
- Error: "selector-not-found: getByRole('button', {name: 'Submit'})" → C1: 0.2
- DOM: button exists with name "Place Order" → C2: 0.2
- History: same drift fixed 3 times before → C3: 0.2
- Humans confirmed locator_drift twice → C4: 0.2
- All signals agree → C5: 0.1 (not 0.2 because name change could be intentional removal)
- **Total: 0.9 → locator_drift, auto-heal**

### Example B: Low confidence (0.45)
- Error: "TimeoutError waiting for navigation" → C1: 0.1
- DOM: page loaded but different content than expected → C2: 0.1
- History: no similar error → C3: 0.0
- No human decisions on this pattern → C4: 0.05
- Conflicting signals → C5: 0.0
- Guard 4 applies (timeout, ambiguous) → capped at 0.6, but raw score is 0.25
- **Total: 0.25 → unknown, route to human review**
```

**Tests:**
- Unit: rubric criteria produce correct scores for known scenarios
- Unit: anti-inflation guards enforce caps correctly
- Unit: worked examples score correctly when run through the rubric
- Unit: Triage prompt includes the full rubric
- Integration: Triage accuracy improves with rubric vs without (A/B on golden set)

**Done when:** Triage uses a formal, auditable rubric; confidence scores are consistent and calibrated; anti-inflation guards prevent overconfidence.

---

## H. Assumptions

- Storage is **git-tracked markdown files** in `memory/` — human-readable, no database.
- Metrics (run history, escape rate, triage accuracy aggregates) stay in **SQLite** — different concern, different tool.
- Memory is per-project (one `memory/` directory per repo).
- All memory writes happen inside existing node functions — no new graph nodes.
- Memory reads are injected into prompts as structured context, capped at ~500 tokens.
- The Healer known-fix fast path is deterministic but **still validated by the assertion guardrail**.
- Memory files use append-only writes within a run; git merge handles cross-run conflicts.

---

## I. Not in Scope

- Cross-project memory sharing (e.g. "login drifts are common across all apps")
- Embedding-based semantic search (normalized substring matching is enough for v1)
- LLM-generated memory summaries (raw structured records are sufficient)
- Vector database (markdown files cover the retrieval patterns needed)
- Schema migrations (markdown is schema-free — add fields by editing the format)

---

## J. Success Metrics

| Metric | How to measure | Target | Phase |
|--------|---------------|--------|-------|
| Healer cache hit rate | known-fix reuses / total heal attempts | > 30% after 30 runs | M1 |
| Triage accuracy improvement | accuracy with memory vs without (A/B on golden set) | +10% accuracy | M2 |
| Mean heal time | wall-clock from failure to green | 50% reduction (skip LLM) | M1 |
| Flaky test detection precision | tests flagged as flaky that are actually flaky | > 80% precision | M3 |
| Stale fix rejection rate | stale fixes caught by guardrail or mark_fix_failed | 100% (zero stale fixes applied) | M1 |
| Lesson actionability | lessons that lead to a prompt/config change within 7 days | > 50% of generated lessons | M5 |
| Weekly review grade accuracy | grade correlates with actual escape rate trend | > 80% agreement | M6 |
| Confidence calibration | rubric-scored confidence vs actual outcome (Brier score) | < 0.15 Brier score | M7 |
| Confidence consistency | same error twice → scores within 0.1 of each other | > 90% of pairs | M7 |
