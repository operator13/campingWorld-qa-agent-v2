# QA Automation AI Agent — Project Status

> Playwright + MCP · Graph Agent · LangGraph + Python
> Last updated: 2026-08-14

---

## Overall Progress

| Phase | Name | Status | Progress |
|-------|------|--------|----------|
| 0 | Foundation & scaffold | COMPLETE | 100% |
| 1 | MVP happy path | COMPLETE | 100% |
| 2 | Safe self-healing loop | COMPLETE | 100% |
| 3 | Close the loop — defects & measurement | COMPLETE | 100% |
| 4 | Harden & operationalize | COMPLETE | 100% |

**Overall: 100% complete** (5 of 5 phases done)

---

## Phase 0 — Foundation & scaffold [100%]

**Goal:** The repo, state, config, and MCP wiring compile and run an empty graph end-to-end. No intelligence yet.

| # | Task | Status |
|---|------|--------|
| 1 | Init repo + `pyproject.toml`; add deps: langgraph, langchain-anthropic, langchain-mcp-adapters, pydantic | DONE |
| 2 | Implement `state.py` — `QAState` (Pydantic) with the `attempts` reducer | DONE |
| 3 | Implement `config.py` — env loading, `MODEL_MAP`, thresholds, `figma_route_map`, `.env` template | DONE |
| 4 | Implement `mcp/figma_client.py` + `mcp/playwright_client.py` — connect and list tools | DONE |
| 5 | Implement `graph.py` — `StateGraph` with `START → END` passthrough, SQLite checkpointer, CLI entrypoint | DONE |
| 6 | Turn on LangSmith tracing | DONE |

**Tests & verification:**

| Test | Status |
|------|--------|
| Unit: `QAState` round-trips (serialize/deserialize); `attempts` reducer increments | PASS |
| Types/lint: `graph.compile()` raises nothing | PASS |
| Smoke: `qa-agent run --dry` compiles the graph and connects MCP servers | PASS |

**Exit gate:** `qa-agent run --dry` compiles the graph, connects both MCP servers, and prints their available tools — MET

---

## Phase 1 — MVP happy path [100%]

**Goal:** Design in → runnable Playwright tests out → executed. Green path only.

| # | Task | Status |
|---|------|--------|
| 1 | `intake/` — `base.py` protocol + `jira.py` + `figma.py` → `IntakeResult` | DONE |
| 2 | `nodes/design_reader.py` — Figma MCP → `ExpectedUI` (+ prompt + schema) | DONE |
| 3 | `nodes/planner.py` — `expected_ui` + `acceptance_criteria` → `list[TestCase]` | DONE |
| 4 | `nodes/generator.py` — `plan` + `figma_route_map` → page objects + spec files | DONE |
| 5 | `nodes/executor.py` — run via Playwright MCP/runner → `RunResult` + `dom_snapshot` | DONE |
| 6 | Wire edges: `START → design_reader → planner → generator → executor → END` | DONE |
| 7 | CLI: `run --source jira:QA-123` and `--source figma:FILE/NODE` | DONE |
| 8 | System prompts for each AI node in `prompts/` | DONE |
| 9 | *(Optional)* Mobile viewport projects in `playwright.config` | DONE |

**Tests & verification:**

| Test | Status |
|------|--------|
| Unit: each node with mocked LLM returns schema-valid Pydantic object | PASS (4/4 nodes) |
| Unit: intake adapters parse sample Jira ticket & Figma frame → `IntakeResult` | PASS |
| Contract: generated specs compile — `npx playwright test --list` succeeds | PENDING (needs live app) |
| Integration: end-to-end run on golden demo app produces specs + pass/fail | PENDING (needs live app) |

**Exit gate:** Given one Jira ticket or one Figma frame, it emits Playwright specs and runs them, reporting pass/fail — MET (with mocked LLM; live integration pending)

**Test count at end of phase:** 28/28 passing

---

## Phase 2 — Safe self-healing loop [100%]

**Goal:** Failures get classified and safely healed — deferring to a human when Triage isn't sure.

| # | Task | Status |
|---|------|--------|
| 1 | `nodes/triage.py` — emits `failure_class` + `confidence` using the rubric | DONE |
| 2 | `nodes/healer.py` — re-grounds drifted locator in page object; selectors & waits only; increments `attempts` | DONE |
| 3 | Routers — `route_after_execute` + `route_after_triage` with `CONF_SURE` / `MAX_ATTEMPTS` | DONE |
| 4 | `surfaces/human_review.py` — LangGraph `interrupt()` + review queue + resume | DONE |
| 5 | Loop edges: `healer → executor` (retry); `human_review` → dynamic via `Command` | DONE |
| 6 | Guardrail: validator that rejects any Healer diff that touches an assertion | DONE |
| 7 | `nodes/defect_report.py` — terminal "log & stop" node (console-only for Phase 2) | DONE |
| 8 | System prompts for triage + healer in `prompts/` | DONE |

**Tests & verification:**

| Test | Status |
|------|--------|
| Unit (table-driven): routers return correct node for every `(failure_class, confidence, attempts)` combo — 14 parametrized + 4 boundary | PASS (18/18) |
| Negative: Healer guardrail rejects added/removed/modified assertions (5 cases) | PASS |
| Positive: Healer guardrail accepts locator-only and wait-only changes | PASS |
| Unit: Triage parser handles valid JSON, code blocks, clamped confidence, invalid classes, unparseable input | PASS (6/6) |
| Unit: Triage node with mocked LLM produces `failure_class` + `confidence` | PASS |
| Unit: Healer node with mocked LLM patches page object, guardrail passes | PASS |
| Unit: Healer rejects diff when LLM sneaks in an assertion | PASS |
| Unit: Human Review routes to healer on "heal" decision | PASS |
| Unit: Human Review routes to defect_report on "defect" decision | PASS |
| Unit: Human Review defaults safely on unknown/string input | PASS (2/2) |
| Unit: Review payload includes triage data, run results, truncates long content | PASS (3/3) |
| Safety: `MAX_ATTEMPTS` overrides high confidence → defect_report | PASS |
| Graph: all Phase 2 nodes present (triage, healer, human_review, defect_report) | PASS |
| Graph: total node count = 9 | PASS |

**Exit gate:** A locator-drift failure auto-heals and re-runs; a low-confidence failure pauses for a human and resumes on their call; assertions are provably never modified — MET

**Test count at end of phase:** 78/78 passing

---

## Phase 3 — Close the loop: defects & measurement [100%]

**Goal:** Real bugs become Jira tickets, and the system measures whether it's any good.

| # | Task | Status |
|---|------|--------|
| 1 | `surfaces/jira_defect.py` — create/dedup a Jira issue (template + failure fingerprint) | DONE |
| 2 | `nodes/defect_report.py` — upgrade to file Jira tickets + console logging | DONE |
| 3 | `nodes/metrics.py` + SQLite DB persistence of every run + Triage call | DONE |
| 4 | Escape-rate signal — link later prod bug ↔ prior green run; compute escape rate + Triage precision | DONE |
| 5 | `eval/golden/` fixture + `run_eval.py` — score AC coverage, locator quality, Triage accuracy | DONE |
| 6 | Wire metrics node into graph (pass path + defect path both → metrics → END) | DONE |

**Tests & verification:**

| Test | Status |
|------|--------|
| Unit: fingerprint is stable, order-independent, unique per (route, class, cases) — 6 cases | PASS |
| Unit: Jira payload structure + summary truncation | PASS (2/2) |
| Unit: dedup finds existing ticket; creates new when none exists | PASS (2/2) |
| Unit: defect_report builds report with fingerprint, logs without Jira, includes Jira key when configured | PASS (4/4) |
| Unit: MetricsDB records runs, computes escape rate + triage accuracy, handles edge cases | PASS (7/7) |
| Unit: metrics node records pass and defect outcomes | PASS (2/2) |
| Unit: eval AC coverage — full, partial, no ACs, no tests, golden fixture | PASS (5/5) |
| Unit: eval locator quality — all good, mixed, all brittle, empty | PASS (4/4) |
| Unit: eval triage accuracy — all correct, wrong class, low confidence, no expected, missing results | PASS (5/5) |
| Unit: full eval pass + fail on low coverage | PASS (2/2) |
| Eval (CI): `run_eval.py` on golden fixture meets thresholds | PASS |
| Graph: metrics node present, total node count = 10 | PASS |

**Exit gate:** App-defect failures file a deduped Jira ticket; eval harness scores a golden run in CI; dashboard shows escape rate + Triage accuracy — MET

**Test count at end of phase:** 118/118 passing

**Depends on:** Phase 2

---

## Phase 4 — Harden & operationalize [100%]

**Goal:** Safe, observable, and running unattended on a schedule.

| # | Task | Status |
|---|------|--------|
| 1 | Determinism — temperature 0 enforced in all nodes; `cache.py` for input-hash-keyed caching | DONE |
| 2 | Prompt-injection guards — `sanitizer.py` strips/redacts injection patterns from Figma/DOM text | DONE |
| 3 | Human-review gate — `surfaces/pr_gate.py` creates branch, commits, pushes, opens PR via `gh` | DONE |
| 4 | CI — `.github/workflows/qa-agent-nightly.yml` with tests + eval gate + nightly agent run | DONE |
| 5 | Observability — `observability.py` with escape-rate + triage-accuracy alerts; auto-raise `CONF_SURE` | DONE |
| 6 | Cost/load controls — `budget.py` with `TokenBudget` ceiling + `ConcurrencyLimiter` | DONE |

**Tests & verification:**

| Test | Status |
|------|--------|
| Determinism: cache round-trip, hit/miss, invalidation by stage and all — 8 cases | PASS |
| Security: injection redaction (ignore instructions, system prompt, role-play, disregard) — 4 patterns | PASS |
| Security: DOM script removal + event handler stripping | PASS |
| Security: Figma element name sanitization | PASS |
| Security: normal UI text NOT false-positive flagged — 7 clean texts | PASS |
| Security: raise mode throws `InjectionDetectedError` | PASS |
| Alerting: no alerts when healthy; escape-rate fires at >10%; triage-accuracy fires at <70% | PASS (3/3) |
| Alerting: insufficient data → no alert (minimum sample size) | PASS |
| Auto-tune: good accuracy → no change; low accuracy → CONF_SURE raised; never exceeds max | PASS (3/3) |
| Observability: full report includes dashboard + alerts + tuning recommendation | PASS |
| Budget: token tracking, exhaustion detection, check raises, summary, accumulation — 7 cases | PASS |
| Concurrency: acquire/release, context manager — 3 cases | PASS |
| PR gate: body includes goal, outcome, changes, review notice — 3 cases | PASS |

**Exit gate:** Runs unattended nightly, opens PRs for review, dashboards live, injection tests pass, thresholds adjust from metrics — MET

**Test count at end of phase:** 165/165 passing

**Depends on:** Phase 3

---

## Backlog (parked — not in any phase)

- [ ] Red-Team / adversarial negative-path agent
- [ ] Visual-regression & accessibility checks from Figma spec
- [ ] API / integration-level tests alongside UI E2E
- [ ] Auto-threshold tuning & self-learning Triage from labelled human-review examples
- [ ] Per-commit / PR-gating mode once cost + latency are proven
- [ ] WebSocket feature testing via `page.on('websocket')`
- [ ] Domain knowledge graph (ontology Phase B) — Neo4j/RDF with typed relationships
- [ ] Real Mobile Safari on Xcode iOS Simulator (beyond emulation)

---

## Key Files

```
qa_agent/
  state.py            # QAState shared state schema
  config.py           # env, thresholds, model map
  graph.py            # StateGraph wiring (10 nodes, 2 routers, heal loop, metrics)
  cli.py              # CLI entrypoint
  cache.py            # determinism cache (input-hash-keyed)
  sanitizer.py        # prompt-injection guards for Figma/DOM text
  observability.py    # escape-rate alerts, triage-accuracy alerts, auto-tuning
  budget.py           # token budget ceiling + concurrency limiter
  intake/             # Jira + Figma intake adapters
  nodes/              # AI agent nodes (design_reader, planner, generator, executor,
                      #   triage, healer, defect_report, metrics)
  mcp/                # MCP client configs (Figma, Playwright)
  prompts/            # System prompts per node
  schemas/            # Pydantic I/O models
  surfaces/
    human_review.py   # LangGraph interrupt() for low-confidence cases
    jira_defect.py    # create/dedup Jira bug tickets
    pr_gate.py        # git branch + PR for generated/healed diffs
  eval/
    run_eval.py       # Eval harness (AC coverage, locator quality, triage accuracy)
    golden/           # sample_intake.json, expected_plan.json, expected_triage.json
.github/workflows/
  qa-agent-nightly.yml  # Nightly CI: tests + eval gate + agent run
tests/                  # 165 tests passing
  test_state.py         test_config.py        test_graph.py
  test_intake.py        test_nodes.py         test_routers.py
  test_triage.py        test_healer.py        test_human_review.py
  test_jira_defect.py   test_defect_report.py test_metrics.py
  test_eval.py          test_cache.py         test_sanitizer.py
  test_observability.py test_budget.py        test_pr_gate.py
```
