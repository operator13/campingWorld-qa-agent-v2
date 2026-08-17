# Changelog

All notable changes to the QA Automation AI Agent are documented here.

Format: each entry includes the date, what changed, which files were affected, and the commit hash (once committed). Entries are grouped by phase so any phase can be understood or rolled back independently.

---

## [Phase 0] — Foundation & scaffold — 2026-08-14

**Goal:** Repo, state, config, and MCP wiring compile and run an empty graph end-to-end.

### Added
- `pyproject.toml` — project config with deps: langgraph, langchain-anthropic, langchain-mcp-adapters, pydantic
- `qa_agent/state.py` — `QAState` Pydantic model with `attempts` reducer (`operator.add`)
- `qa_agent/config.py` — env loading, `MODEL_MAP`, thresholds (`CONF_SURE=0.75`, `MAX_ATTEMPTS=3`), `figma_route_map`
- `qa_agent/schemas/models.py` — `TestCase`, `ExpectedUI`, `RunResult` Pydantic models
- `qa_agent/mcp/figma_client.py` — Figma MCP server config
- `qa_agent/mcp/playwright_client.py` — Playwright MCP server config
- `qa_agent/graph.py` — `StateGraph` with `START → passthrough → END`, `MemorySaver` checkpointer
- `qa_agent/cli.py` — CLI entrypoint (`qa-agent run --dry`)
- `.env.template` — environment variable template
- `.gitignore`
- `tests/test_state.py` — 5 tests (round-trip, JSON, reducer, schemas)
- `tests/test_config.py` — 5 tests (constants, model map, env, route map)
- `tests/test_graph.py` — 3 tests (build, compile, passthrough)

**Tests:** 13/13 passing

---

## [Phase 1] — MVP happy path — 2026-08-14

**Goal:** Design in → runnable Playwright tests out → executed. Green path only.

### Added
- `qa_agent/intake/base.py` — `Intake` protocol, `IntakeResult` model, `parse_source()` CLI parser
- `qa_agent/intake/jira.py` — Jira ticket reader (summary, ADF descriptions, AC fields, Figma URL detection)
- `qa_agent/intake/figma.py` — Figma frame reader (URL parsing, short refs, goal/AC derivation)
- `qa_agent/nodes/design_reader.py` — Figma MCP → `ExpectedUI` (skips when no figma_ref)
- `qa_agent/nodes/planner.py` — UI spec + AC → categorized `list[TestCase]` (Opus model)
- `qa_agent/nodes/generator.py` — plan → page objects + test specs (Sonnet model)
- `qa_agent/nodes/executor.py` — writes files, runs `npx playwright test`, captures `RunResult`
- `qa_agent/prompts/design_reader.py` — system prompt for Design Reader
- `qa_agent/prompts/planner.py` — system prompt for Planner
- `qa_agent/prompts/generator.py` — system prompt for Generator with POM examples
- `qa_agent/prompts/executor.py` — system prompt for Executor
- `tests/test_intake.py` — 10 tests (parsing, Jira payload, ADF, Figma URLs)
- `tests/test_nodes.py` — 5 tests (each node with mocked LLM)

### Changed
- `qa_agent/graph.py` — replaced passthrough with `design_reader → planner → generator → executor → END`
- `qa_agent/cli.py` — added `--source jira:QA-123` / `--source figma:FILE/NODE` with merge policy

**Tests:** 28/28 passing

---

## [Phase 2] — Safe self-healing loop — 2026-08-14

**Goal:** Failures get classified and safely healed, deferring to a human when Triage isn't sure.

### Added
- `qa_agent/nodes/triage.py` — classifies failures (`locator_drift`/`app_defect`/`unknown`) + confidence 0–1
- `qa_agent/nodes/healer.py` — patches drifted locators in page objects (selectors & waits only, never assertions)
- `qa_agent/nodes/healer.py::AssertionGuardError` — guardrail that rejects any diff touching assertions
- `qa_agent/nodes/defect_report.py` — terminal node, logs bug to console (Jira integration in Phase 3)
- `qa_agent/surfaces/human_review.py` — LangGraph `interrupt()` for low-confidence cases, resumes via `Command`
- `qa_agent/prompts/triage.py` — Triage rubric + confidence scoring rules
- `qa_agent/prompts/healer.py` — Healer rules (what to change, what never to change)
- `tests/test_routers.py` — 18 table-driven router tests + 4 boundary tests
- `tests/test_healer.py` — 13 tests (guardrail accepts/rejects, mocked LLM, assertion rejection)
- `tests/test_triage.py` — 7 tests (parser, clamping, code blocks, mocked LLM)
- `tests/test_human_review.py` — 7 tests (routing decisions, defaults, payload)

### Changed
- `qa_agent/graph.py` — added triage, healer, human_review, defect_report nodes; `route_after_execute` + `route_after_triage` routers; healer → executor loop

**Tests:** 78/78 passing

---

## [Phase 3] — Close the loop: defects & measurement — 2026-08-14

**Goal:** Real bugs become Jira tickets, and the system measures whether it's any good.

### Added
- `qa_agent/surfaces/jira_defect.py` — create/dedup Jira tickets via REST API with failure fingerprinting
- `qa_agent/nodes/metrics.py` — `MetricsDB` SQLite store, records runs + Triage calls, computes escape rate + accuracy
- `qa_agent/eval/run_eval.py` — eval harness scoring AC coverage, locator quality, Triage accuracy
- `qa_agent/eval/golden/sample_intake.json` — golden fixture: intake data
- `qa_agent/eval/golden/expected_plan.json` — golden fixture: expected test plan
- `qa_agent/eval/golden/expected_triage.json` — golden fixture: expected Triage classifications
- `tests/test_jira_defect.py` — 10 tests (fingerprint, dedup, payload)
- `tests/test_metrics.py` — 9 tests (MetricsDB CRUD, escape rate, accuracy, node)
- `tests/test_eval.py` — 13 tests (AC coverage, locator quality, Triage accuracy, full eval)
- `tests/test_defect_report.py` — 4 tests (report builder, Jira integration)

### Changed
- `qa_agent/nodes/defect_report.py` — upgraded from console-only to Jira ticket filing with dedup
- `qa_agent/graph.py` — added metrics node; both terminal paths (pass + defect) route through metrics → END; node count 9 → 10

**Tests:** 118/118 passing

---

## [Phase 4] — Harden & operationalize — 2026-08-14

**Goal:** Safe, observable, and running unattended on a schedule.

### Added
- `qa_agent/cache.py` — determinism cache (input-hash-keyed, stage-scoped, invalidation)
- `qa_agent/sanitizer.py` — prompt-injection guards (12 regex patterns, DOM script removal, element sanitization)
- `qa_agent/observability.py` — escape-rate + triage-accuracy alerts, auto-tuning of `CONF_SURE`
- `qa_agent/budget.py` — `TokenBudget` (500K token ceiling) + `ConcurrencyLimiter` (semaphore)
- `qa_agent/surfaces/pr_gate.py` — git branch + commit + push + PR via `gh` CLI
- `.github/workflows/qa-agent-nightly.yml` — nightly CI: tests → eval gate → agent run → artifact upload
- `tests/test_cache.py` — 8 tests
- `tests/test_sanitizer.py` — 18 tests (injection patterns, DOM, Figma elements, false positives)
- `tests/test_observability.py` — 8 tests (alerts, auto-tuning, report)
- `tests/test_budget.py` — 10 tests (token tracking, concurrency)
- `tests/test_pr_gate.py` — 3 tests (PR body)

**Tests:** 165/165 passing

---

## [Post-Phase] — MCP migration & bug fixes — 2026-08-14 to 2026-08-17

### Fixed
- `qa_agent/cli.py` — fixed `MultiServerMCPClient` usage (removed broken `async with` context manager, use `await client.get_tools()`)
- `qa_agent/mcp/figma_client.py` — switched from stdio to `streamable_http` transport (Figma MCP runs as HTTP server on port 3333)
- `qa_agent/mcp/playwright_client.py` — removed `--browser chromium` arg (not needed), fixed `get_tools()` to async
- `qa_agent/cli.py` — connect MCP servers independently (not all-at-once) with per-server error handling

### Changed — Jira: REST API → Atlassian MCP
- `qa_agent/intake/jira.py` — **rewritten** to use Atlassian MCP (`getJiraIssue` tool) instead of httpx REST API + Basic Auth
- `qa_agent/surfaces/jira_defect.py` — **rewritten** to use Atlassian MCP (`searchJiraIssuesUsingJql`, `createJiraIssue`) instead of REST API
- `qa_agent/mcp/atlassian_client.py` — **new** MCP client config for `@anthropic-ai/atlassian-mcp-server`
- `qa_agent/config.py` — removed `jira_base_url`, `jira_token`, `jira_user_email`; added `jira_project_key`
- `qa_agent/nodes/defect_report.py` — removed API key check (MCP handles auth)
- `.env.template` — removed Jira API credentials, added `JIRA_PROJECT_KEY`
- `.env` — updated to match

### Added
- `features/` directory for future feature build specs
- `features/MEMORY.md` — Agent Memory build spec
- `features/RED_TEAM_NEGATIVE_PATH.md` — Adversarial test generation build spec
- `features/VISUAL_REGRESSION_ACCESSIBILITY.md` — Screenshot diffs + a11y audits build spec
- `features/API_INTEGRATION_TESTING.md` — API-level tests build spec
- `features/AUTO_THRESHOLD_TUNING.md` — Self-learning Triage build spec
- `features/PER_COMMIT_PR_GATING.md` — PR-blocking QA runs build spec
- `features/WEBSOCKET_TESTING.md` — WebSocket feature testing build spec
- `features/DOMAIN_KNOWLEDGE_GRAPH.md` — Property graph for coverage queries build spec
- `features/MOBILE_WEB_TESTING.md` — Mobile viewport testing build spec
- `CHANGELOG.md` — this file

**Tests:** 166/166 passing

---

## How to use this changelog

**Understand what was built:** Read the phase that interests you — each lists every file added/changed.

**Roll back a phase:** Revert all commits in that phase's group. Phases are independent layers:
- Phase 4 can be removed without affecting Phases 0–3
- Phase 3 can be removed if you also remove Phase 4
- Phase 2 can be removed if you also remove Phases 3–4
- Phases 0–1 are the foundation and can't be removed independently

**Track a specific change:** Search for the filename to find which phase introduced or modified it.
