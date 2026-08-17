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

### Phase M1 — Storage + Healer memory
**Goal:** Healer remembers past fixes and reuses them.

| # | Task | Status |
|---|------|--------|
| 1 | Create `memory/` directory structure + `.gitkeep` files | TODO |
| 2 | Implement `MemoryStore` class — markdown read/write, locator history methods | TODO |
| 3 | Implement `normalize_error()` and `extract_locator_from_error()` | TODO |
| 4 | Integrate into Healer — known-fix fast path **with guardrail validation** | TODO |
| 6 | Implement `mark_fix_failed()` for stale fix protection | TODO |
| 7 | Integrate into Healer prompt — inject locator history as context | TODO |
| 8 | Add `MEMORY_ENABLED` + `HEALER_MEMORY` kill switches to config | TODO |

**Tests:**
- Unit: `MemoryStore` round-trip — write locator change, read it back
- Unit: `normalize_error()` strips line numbers, paths, timestamps
- Unit: `extract_locator_from_error()` finds getByRole/getByTestId in Playwright errors
- Unit: known-fix fast path applies cached fix and passes guardrail
- Unit: known-fix fast path **rejected** when cached fix touches assertions
- Unit: `mark_fix_failed()` prevents reuse of a stale fix
- Unit: kill switch disables memory reads/writes
- Integration: second heal of same drift is instant (memory hit)
- Integration: stale fix fails → marked failed → LLM slow path runs

**Done when:** Healer reuses past fixes safely; stale fixes are caught; PII is scrubbed; kill switch works.

---

### Phase M2 — Triage calibration + Human Review storage
**Goal:** Triage learns from human corrections.

| # | Task | Status |
|---|------|--------|
| 1 | `MemoryStore` — `record_human_decision()` writes to `human_decisions.md` | TODO |
| 2 | `MemoryStore` — `get_triage_calibration(n=10)` reads last N decisions | TODO |
| 3 | Wire Human Review node to call `record_human_decision()` after each verdict | TODO |
| 4 | Inject calibration history into Triage prompt (with token cap) | TODO |
| 5 | `find_similar_failure()` using normalized signature substring matching | TODO |
| 6 | Add `TRIAGE_MEMORY` kill switch | TODO |

**Tests:**
- Unit: human decisions written and parsed from markdown table
- Unit: calibration returns last N entries in reverse chronological order
- Unit: Triage prompt includes calibration section
- Unit: `find_similar_failure()` matches on normalized signature
- Unit: kill switch disables Triage memory
- Integration: after 5 human overrides on the same pattern, Triage receives them as context

**Done when:** Human verdicts are stored in markdown; Triage prompt includes recent corrections; similar failures are found.

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

| Metric | How to measure | Target |
|--------|---------------|--------|
| Healer cache hit rate | known-fix reuses / total heal attempts | > 30% after 30 runs |
| Triage accuracy improvement | accuracy with memory vs without (A/B on golden set) | +10% accuracy |
| Mean heal time | wall-clock from failure to green | 50% reduction (skip LLM) |
| Flaky test detection precision | tests flagged as flaky that are actually flaky | > 80% precision |
| Stale fix rejection rate | stale fixes caught by guardrail or mark_fix_failed | 100% (zero stale fixes applied) |
