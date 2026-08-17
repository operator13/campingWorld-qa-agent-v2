# Feature: Red-Team / Adversarial Negative-Path Agent

> A dedicated agent that deliberately tries to break the app — generating edge-case, boundary, and adversarial test scenarios that the happy-path Planner would never think of.

**Status:** PLANNED
**Priority:** Medium
**Depends on:** Core framework (Phases 0-4), Memory feature (recommended)

---

## The Problem

The Planner generates tests from acceptance criteria — what the app *should* do. It never asks "what happens if the user does something unexpected?" Missing negative paths means real bugs in error handling, input validation, and edge cases go untested.

## The Solution

A new AI agent node — the **Red Team** — that runs after the Planner and generates adversarial test cases designed to find failures the happy-path tests miss.

---

## A. What the Red Team Tests

| Category | Examples |
|----------|---------|
| **Boundary values** | Empty strings, max-length inputs, zero, negative numbers, Unicode, emoji |
| **Invalid state transitions** | Submit before filling required fields, double-click submit, back-button after submit |
| **Injection / XSS** | `<script>alert(1)</script>` in text fields, SQL-like strings, format string attacks |
| **Concurrency / race conditions** | Rapid repeated clicks, multiple tabs, expired sessions |
| **Error recovery** | Network offline mid-flow, slow responses, server 500s |
| **Authorization boundaries** | Access pages without login, manipulate URLs to access other users' data |

---

## B. Architecture

### New node: `nodes/red_team.py`

Sits between Planner and Generator as an optional enrichment step:

```
Planner → Red Team (optional) → Generator → Executor
```

The Red Team reads the Planner's test cases and the UI spec, then generates *additional* negative-path cases. It does not replace the Planner's output — it appends to it.

### Prompt strategy

The Red Team agent uses a dedicated adversarial system prompt:

```
You are a security-minded QA engineer. Your job is to break the app.
Given the happy-path test cases and UI spec, generate test cases that:
1. Test every input with boundary/invalid values
2. Try actions in the wrong order
3. Attempt to bypass validation
4. Test error states and recovery
...
```

### Output

Same `list[TestCase]` schema as the Planner, with tags like `@negative`, `@boundary`, `@security` for filtering.

---

## C. Build Phases

### Phase RT1 — Core Red Team agent
| # | Task | Status |
|---|------|--------|
| 1 | `nodes/red_team.py` — AI node that generates negative-path test cases | TODO |
| 2 | `prompts/red_team.py` — adversarial system prompt with category rubric | TODO |
| 3 | Config flag: `ENABLE_RED_TEAM=true/false` to toggle the node | TODO |
| 4 | Wire into graph: Planner → Red Team → Generator (conditional on flag) | TODO |
| 5 | Merge logic: append Red Team cases to Planner cases, dedup by scenario | TODO |

**Tests:**
- Unit: Red Team with mocked LLM produces schema-valid negative test cases
- Unit: cases are tagged with `@negative`, `@boundary`, etc.
- Unit: Red Team is skipped when `ENABLE_RED_TEAM=false`
- Integration: end-to-end run with Red Team enabled produces more test cases than without

**Done when:** Red Team generates adversarial cases that compile and run alongside happy-path tests.

### Phase RT2 — Category coverage + reporting
| # | Task | Status |
|---|------|--------|
| 1 | Category coverage report: which negative categories were tested per route | TODO |
| 2 | Severity scoring: rank generated negatives by likely impact | TODO |
| 3 | Integration with eval harness: score negative-path coverage | TODO |

**Done when:** Dashboard shows negative-path coverage by category; eval harness scores it.

---

## D. Assumptions

- Red Team is optional and off by default (cost/latency concern).
- Uses the same `TestCase` schema — no new output types.
- Generated negative tests go through the same Executor → Triage → Healer pipeline.
- A failing negative test is *expected* to fail (the app should handle it gracefully) — Triage needs to understand that a validation error shown to the user is a *pass*, not a defect.

## E. Not in Scope

- Automated penetration testing or actual exploitation
- Fuzzing (random input generation at scale)
- Performance/load testing
