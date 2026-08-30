# Feature: Healer Agent — Flaky Test Auto-Fix

> Expand the Healer agent to detect and fix timing/race condition failures in tests, not just locator drift.

**Status:** PLANNED
**Priority:** High
**Depends on:** Triage Agent, Healer Agent, Confidence Rubric

---

## The Problem

The Healer agent today only fixes **locator drift** — when a CSS selector or test ID changes on the site. But a large category of test failures are **timing/race conditions**: the test interacts with an element before it's loaded, scrolls before it's visible, or clicks before a dynamic API response renders the UI.

These failures get classified as `unknown` by the Triage agent and fall through to manual fix, even though the pattern is predictable and the fix is mechanical:

```
# The problem (flaky)
await button.scrollIntoViewIfNeeded();     // fails — button not in DOM yet
await expect(button).toBeVisible();

# The fix (stable)
await button.waitFor({ state: 'visible', timeout: 20_000 });
await button.scrollIntoViewIfNeeded();
await expect(button).toBeVisible();
```

### Real Example

`product.spec.ts:44` — "add to cart button is enabled"
- Button renders after an async inventory API call
- `scrollIntoViewIfNeeded()` fires before the button exists in the DOM
- TimeoutError at 10s — passes on retry 2 minutes later
- Triage classifies as `unknown` (confidence 0.55) → Healer never invoked

---

## The Solution

### 1. New Triage Classification: `test_flake`

Add a fourth failure class alongside `locator_drift`, `app_defect`, and `unknown`.

```python
# Current
failure_class: "locator_drift" | "app_defect" | "unknown"

# Proposed
failure_class: "locator_drift" | "app_defect" | "test_flake" | "unknown"
```

**`test_flake` signals:**
- TimeoutError on `scrollIntoViewIfNeeded`, `click`, `fill`, `type` — but the locator is valid (element exists in DOM on retry)
- Test passes intermittently (history shows pass/fail oscillation)
- Error occurs in interaction step, not in assertion
- No DOM changes detected (locator is correct, element just loads late)

### 2. New Error Patterns in Confidence Rubric

Add flaky-specific patterns to `confidence.py` for C1 scoring:

```python
FLAKE_PATTERNS = [
    r"scrollIntoViewIfNeeded.*Timeout",
    r"locator\.(click|fill|type).*Timeout.*exceeded",
    r"waiting for.*visible",
    r"element is not visible",
    r"element is not stable",
    r"element is outside of the viewport",
    r"beforeEach.*Timeout",
]
```

**C1 scoring for `test_flake`:**
- 0.3: Strong flake signal (interaction timeout + element exists in DOM snapshot)
- 0.15: Moderate (timeout without DOM evidence)
- 0.0: No flake patterns

**New C3 enhancement — flakiness history:**
- Check `TEST_STABILITY.md` for pass/fail oscillation on this test
- If flakiness score > 0.3 → boost C3 by 0.1 (strong historical flake signal)

### 3. Healer Expansion: Timing Fix Strategies

Expand the Healer prompt and logic to handle `test_flake` classification with specific fix strategies:

#### Strategy A: Add `waitFor` Before Interaction

```typescript
// Before (flaky)
await element.scrollIntoViewIfNeeded();

// After (stable)
await element.waitFor({ state: 'visible', timeout: 20_000 });
await element.scrollIntoViewIfNeeded();
```

**When:** TimeoutError on `scrollIntoViewIfNeeded`, `click`, `fill` — element loads asynchronously.

#### Strategy B: Add `waitFor` Before Assertion

```typescript
// Before (flaky)
await expect(element).toBeVisible();

// After (stable)
await element.waitFor({ state: 'attached', timeout: 20_000 });
await expect(element).toBeVisible();
```

**When:** Element assertion fails intermittently — DOM hasn't updated yet.

#### Strategy C: Replace `scrollIntoViewIfNeeded` With Safer Pattern

```typescript
// Before (flaky)
await element.scrollIntoViewIfNeeded();
await expect(element).toBeEnabled({ timeout: 15_000 });

// After (stable)
await element.waitFor({ state: 'visible', timeout: 20_000 });
await element.scrollIntoViewIfNeeded();
await expect(element).toBeEnabled();
```

**When:** Scroll + assert pattern where the scroll is the failure point.

#### Strategy D: Add Network Idle Wait

```typescript
// Before (flaky — data loads from API)
await page.goto(url);
await expect(dataTable).toHaveCount(10);

// After (stable)
await page.goto(url, { waitUntil: 'networkidle' });
await expect(dataTable).toHaveCount(10);
```

**When:** Page content depends on XHR/fetch calls that haven't completed.

### 4. Guardrail Updates

The assertion guardrail must be updated to:

| Action | Allowed | Blocked |
|--------|---------|---------|
| Add `waitFor()` before existing line | Yes | — |
| Add `waitFor()` after existing line | Yes | — |
| Modify `expect()` statements | — | Yes (unchanged) |
| Modify assertion values/matchers | — | Yes (unchanged) |
| Change `timeout` in `waitFor` | Yes | — |
| Change `timeout` in `expect()` | — | Yes |
| Remove test lines | — | Yes |
| Add `page.waitForTimeout()` (hard wait) | — | Yes (anti-pattern) |

Key rule: **The Healer can add synchronization before interactions but never modify the assertion itself.**

### 5. Triage Runner Routing Update

```python
# Current routing
if failure_class == "locator_drift" and confidence >= CONF_SURE:
    → healer()

# Proposed routing
if failure_class in ("locator_drift", "test_flake") and confidence >= CONF_SURE:
    → healer()
```

The Healer receives the `failure_class` in state so it knows which fix strategy to apply:
- `locator_drift` → fix the selector (existing behavior)
- `test_flake` → add synchronization waits (new behavior)

### 6. Healer Prompt Update

Add to `HEALER.md`:

```markdown
## Timing Fix Rules

When `failure_class` is `test_flake`:

1. DO NOT change any locators — they are correct
2. ADD a `waitFor({ state: 'visible', timeout: 20_000 })` before the failing interaction
3. Never add `page.waitForTimeout()` — this is a hard wait anti-pattern
4. Never modify `expect()` assertions or their timeouts
5. Only add waits in the SPEC FILE, not the page object
6. Prefer `waitFor` on the specific element, not `page.waitForLoadState()`

Output format is the same as locator fixes — return the patched spec file source.
```

### 7. Memory Enhancement

Track timing fixes in memory for fast-path resolution:

```markdown
<!-- memory/TIMING_FIXES.md -->
## Known Timing Fixes

| Route | Element | Error Pattern | Fix Applied | Success |
|-------|---------|--------------|-------------|---------|
| product | addToCartButton | scrollIntoViewIfNeeded Timeout | waitFor visible 20s | true |
```

The Healer checks this before calling the LLM — if a known timing fix exists for the same route + element + error pattern, apply it directly (same fast-path as locator known fixes).

---

## Architecture Changes

### Files to Modify

| File | Change |
|------|--------|
| `qa_agent/nodes/triage.py` | Add `test_flake` to classification output |
| `qa_agent/prompts/TRIAGE.md` | Add `test_flake` category with examples |
| `qa_agent/confidence.py` | Add `FLAKE_PATTERNS`, C1 flake scoring, C3 stability boost |
| `qa_agent/nodes/healer.py` | Add timing fix strategies, spec file patching (not just POM) |
| `qa_agent/prompts/HEALER.md` | Add timing fix rules and examples |
| `qa_agent/triage_runner.py` | Route `test_flake` to healer |
| `qa_agent/memory.py` | Add `get_known_timing_fix()`, `record_timing_fix()` |

### Files to Create

| File | Purpose |
|------|---------|
| `memory/TIMING_FIXES.md` | Known timing fix cache |

### State Changes

```python
# QAState — no new fields needed
# failure_class already accepts string, just add "test_flake" as valid value
# Healer already returns page_objects dict — extend to include spec files
```

---

## Scope Boundary

### In Scope
- Timing/race condition fixes (add `waitFor`, adjust wait strategies)
- Flaky test detection via error pattern + test stability history
- Known timing fix fast-path (memory-backed)
- Spec file patching (not just POM files)

### Out of Scope
- Rewriting test logic or flow
- Adding retry logic inside tests
- Fixing tests that fail due to test data issues
- Fixing tests that depend on external service availability
- Modifying `playwright.config.ts` global timeouts

---

## Build Phases

### Phase HF1 — Triage Classification (~0.5 day)

| # | Task |
|---|------|
| 1 | Add `test_flake` to Triage output schema |
| 2 | Add `FLAKE_PATTERNS` to `confidence.py` with C1 scoring |
| 3 | Add C3 stability boost from `TEST_STABILITY.md` flakiness scores |
| 4 | Update `TRIAGE.md` prompt with `test_flake` examples |
| 5 | Update triage eval golden scenarios with flake test cases |

### Phase HF2 — Healer Timing Fix (~1 day)

| # | Task |
|---|------|
| 1 | Add timing fix strategies (A-D) to Healer |
| 2 | Extend Healer to patch spec files (not just POMs) |
| 3 | Update guardrail: allow `waitFor` additions, block `waitForTimeout` |
| 4 | Update `HEALER.md` prompt with timing fix rules |
| 5 | Add `get_known_timing_fix()` / `record_timing_fix()` to memory |
| 6 | Create `memory/TIMING_FIXES.md` |

### Phase HF3 — Routing + Integration (~0.5 day)

| # | Task |
|---|------|
| 1 | Update `triage_runner.py` to route `test_flake` to healer |
| 2 | Pass `failure_class` through state so healer knows which strategy |
| 3 | Test end-to-end: inject timing failure → triage → heal → re-run |
| 4 | Update healer eval golden scenarios with timing fix cases |

### Phase HF4 — Audit + Observability (~0.5 day)

| # | Task |
|---|------|
| 1 | Log every `test_flake` triage decision to `AUDIT_TRAIL.md` with classification, confidence, error pattern |
| 2 | Log every timing fix attempt to audit: spec file, element, strategy used (A/B/C/D), success/fail |
| 3 | Track timing fix metrics in `memory/TIMING_FIXES.md`: total attempts, success rate, avg time saved |
| 4 | Add per-run flake stats to audit JSON: `flakes_detected`, `flakes_healed`, `flakes_unhealed` |
| 5 | Surface flake healing rate in `/api/audit/summary` response |

### Phase HF5 — Eval Agent Integration (~0.5 day)

| # | Task |
|---|------|
| 1 | Add `timing_fix_correctness` metric to Healer eval (separate from locator fix scoring) |
| 2 | Add golden scenarios for timing fixes: 5 flake failures with expected fix strategies |
| 3 | Eval scoring: does the fix use `waitFor` (not `waitForTimeout`)? Does it target the right element? Does it preserve assertions? |
| 4 | Add `flake_detection_accuracy` metric to Triage eval (separate from drift/defect accuracy) |
| 5 | Add golden scenarios for flake detection: 5 timing failures that should classify as `test_flake` |
| 6 | Composite Healer score = `(locator_accuracy * 0.6) + (timing_fix_accuracy * 0.4)` — weighted since locator drift is more common |
| 7 | Regression detection: alert if timing fix accuracy drops below 75% between eval runs |

### Phase HF6 — Dashboard (~0.5 day)

| # | Task |
|---|------|
| 1 | Show `test_flake` as distinct purple category in Run History (separate from SELF-HEAL) |
| 2 | Add flake healing stats to Healer eval card: "Locator: 100% / Timing: 85%" |
| 3 | Add flake trend to health gauge tooltip: "3 flakes auto-fixed this run" |

---

## Audit Trail Schema

Every timing fix attempt produces an audit record:

```json
{
  "event": "timing_fix",
  "timestamp": "2026-08-30T20:15:00Z",
  "spec_file": "product.spec.ts",
  "test_title": "add to cart button is enabled",
  "element": "addToCartButton",
  "error_pattern": "scrollIntoViewIfNeeded Timeout",
  "triage_confidence": 0.82,
  "strategy": "A",
  "fix_applied": "waitFor({ state: 'visible', timeout: 20000 })",
  "source": "llm",
  "success": true,
  "tokens_used": 1200,
  "cost_usd": 0.004
}
```

Aggregated metrics in `memory/TIMING_FIXES.md`:

```markdown
## Timing Fix Performance

| Metric | Value |
|--------|-------|
| Total flakes detected | 12 |
| Auto-healed | 10 |
| Success rate | 83.3% |
| Cache hits (known fix) | 6 |
| LLM calls | 4 |
| Avg tokens per fix | 1,400 |
| Avg cost per fix | $0.005 |

## Strategy Breakdown

| Strategy | Used | Success | Rate |
|----------|------|---------|------|
| A: waitFor before interaction | 7 | 6 | 85.7% |
| B: waitFor before assertion | 3 | 3 | 100% |
| C: safer scroll pattern | 1 | 1 | 100% |
| D: network idle wait | 1 | 0 | 0% |
```

---

## Eval Agent Metrics

### Healer Eval (expanded)

```json
{
  "healer_accuracy": {
    "locator_fix": { "score": 1.0, "total": 5, "passed": 5 },
    "timing_fix": { "score": 0.8, "total": 5, "passed": 4 },
    "composite": 0.92
  },
  "timing_fix_details": [
    {
      "scenario": "scrollIntoViewIfNeeded timeout on async button",
      "expected_strategy": "A",
      "actual_strategy": "A",
      "assertion_preserved": true,
      "no_hard_waits": true,
      "correct": true
    }
  ]
}
```

### Triage Eval (expanded)

```json
{
  "triage_accuracy": {
    "locator_drift": { "correct": 5, "total": 5 },
    "app_defect": { "correct": 3, "total": 3 },
    "test_flake": { "correct": 4, "total": 5 },
    "overall": 0.923
  }
}
```

---

## Success Criteria

1. Triage correctly classifies timing failures as `test_flake` with confidence >= 0.75
2. Healer adds appropriate `waitFor` without modifying assertions
3. Fixed tests pass on re-run
4. Known timing fixes are cached and reused (no repeated LLM calls)
5. Triage accuracy stays >= 85% (no regression on existing categories)
6. Guardrail blocks any `page.waitForTimeout()` additions (hard wait anti-pattern)
7. Every timing fix attempt is logged to audit trail with strategy, tokens, cost, success
8. Eval Agent reports separate `timing_fix_correctness` score alongside locator accuracy
9. Dashboard shows flake healing stats on Healer eval card
10. Flake detection accuracy >= 75% on golden scenarios
