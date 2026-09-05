# QA Automation AI Agent

[![Tests](https://img.shields.io/badge/Playwright-127%20tests%20%C2%B7%2014%20domains-2EAD33?logo=playwright)](https://playwright.dev/)
[![Health](https://img.shields.io/badge/health%20score-live%20dashboard-00ffc8)](https://github.com)
[![Agents](https://img.shields.io/badge/agents-16%20evaluated-4f46e5)](https://github.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-4f46e5?logo=python)](https://langchain-ai.github.io/langgraph/)
[![Claude](https://img.shields.io/badge/Claude-Opus%20%2B%20Sonnet-d97706?logo=anthropic)](https://anthropic.com/)
[![Docker](https://img.shields.io/badge/Docker-dashboard-2496ED?logo=docker)](https://docker.com/)

An **AI-powered QA automation framework** that generates Playwright tests, runs them against [campingworld.com](https://www.campingworld.com), self-heals when locators drift or tests flake, and serves a real-time cyberpunk dashboard for monitoring health scores, triggering test runs and agent evaluations, and tracking agent performance — all from your browser or phone. Built with **LangGraph**, **Claude**, **FastAPI**, and **WebSocket**.

---

## What It Does

```
                    ┌──────────────┐
                    │  DASHBOARD   │  Real-time health, test runner, eval runner
                    │  (Browser)   │  WebSocket-synced across devices
                    └──────┬───────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌─────────────┐  ┌───────────┐  ┌─────────────┐
   │  RUN TESTS  │  │  MONITOR  │  │  SELF-HEAL  │
   │  127 tests  │  │  Health   │  │  Triage →   │
   │  14 domains │  │  Scores   │  │  Healer     │
   └─────────────┘  └───────────┘  └─────────────┘
```

1. **Generate** — AI creates Playwright tests with Page Object Models from Figma designs and Jira tickets
2. **Execute** — Runs 127 tests across 14 domains of campingworld.com
3. **Score** — Computes weighted health scores per domain with critical path weighting
4. **Heal** — Triages failures, auto-fixes locator drift AND timing flakes, defers to humans when unsure
5. **Evaluate** — Benchmarks 16 AI agents (4 pipeline + 12 development) against 201 golden scenarios with cumulative token/cost tracking
6. **Secure** — 9 security vulnerabilities patched across dashboard (path traversal, code injection, auth, XSS, WebSocket relay)
7. **Monitor** — Live dashboard with event-driven WebSocket push, accessible from desktop and mobile

---

## QA Command Center Dashboard

A real-time cyberpunk-themed dashboard for monitoring and controlling the entire QA pipeline from any device. **Zero polling** — all updates are event-driven via WebSocket push.

```
┌──────────────────────────────────────────────────────────────────────┐
│  QA COMMAND CENTER                                    ● LIVE        │
├──────────────────────────┬───────────────────────────────────────────┤
│   SYSTEM HEALTH          │  DOMAIN STATUS                           │
│     ┌───────┐            │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐   │
│     │ 98.7% │            │  │Cart  │ │Chkout│ │SignIn│ │Search│   │
│     │HEALTHY│            │  │100%  │ │100%  │ │100%  │ │100%  │   │
│     └───────┘            │  └──────┘ └──────┘ └──────┘ └──────┘   │
├──────────────────────────┼───────────────────────────────────────────┤
│  AGENT EVALUATION                               [▶ EVAL ALL]       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │
│  │TRIAGE    │ │PLANNER   │ │GENERATOR │ │HEALER    │              │
│  │85.7% [▶] │ │100%  [▶] │ │100%  [▶] │ │96%   [▶] │              │
│  │271K $1.31│ │79K $0.90 │ │24K $0.18 │ │122K $0.66│              │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘              │
├──────────────────────────┼───────────────────────────────────────────┤
│  TEST RUNNER             │  RUN HISTORY                             │
│  Workers [1][2][●3][4]   │  2026-09-05 03:08  127  127  0 100.0%  │
│  Retries [●0][1]         │  2026-09-05 02:03  127  127  0 100.0%  │
│  Self-Heal [OFF][●ON]    │  2026-09-04 19:56  127  127  0 100.0%  │
│  [▶ RUN SELECTED][▶ ALL] │  ← Click any row to view HTML report    │
│  [CLEAR]                 │                                         │
├──────────────────────────┴───────────────────────────────────────────┤
│  DEVELOPMENT AGENT EVALS                   [▶ EVAL ECC AGENTS]      │
│  DETECTION AGENTS                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │
│  │SECURITY- │ │CODE-     │ │SILENT-   │ │PYTHON-   │              │
│  │REVIEWER  │ │REVIEWER  │ │FAILURE-  │ │REVIEWER  │              │
│  │100% PASS │ │75%  PASS │ │HUNTER    │ │100% PASS │              │
│  │Recall 21 │ │Recall 12 │ │100% PASS │ │Recall 10 │              │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘              │
│  GENERATIVE AGENTS                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐│
│  │PLANNER   │ │TDD-GUIDE │ │BUILD-ERR │ │E2E-      │ │REFACTOR- ││
│  │(ECC)     │ │79% PASS  │ │97% PASS  │ │RUNNER    │ │CLEANER   ││
│  │12% FAIL  │ │Quality   │ │Quality   │ │97% PASS  │ │100% PASS ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘│
└──────────────────────────────────────────────────────────────────────┘
```

### Dashboard Features

| Feature | Description |
|---------|-------------|
| **Health Gauge** | SVG circular gauge with weighted overall score |
| **Domain Cards** | 14 cards showing per-domain pass rate, test counts, status |
| **Pipeline Eval Cards** | 4 cards with accuracy, cumulative tokens/cost, hover tooltips with agent details |
| **ECC Dev Agent Evals** | 12 cards (7 detection + 5 generative) with recall/precision/FP rate, quality dimensions, tokens/cost, tooltips |
| **Eval Runner** | Trigger per-agent or all evals from browser with progress bars |
| **ECC Eval Runner** | Trigger individual or all 12 ECC agent evals with parallel execution and live progress |
| **Test Runner** | Select domains, configure workers/retries, trigger from browser |
| **Self-Heal Toggle** | Auto-triage and fix failures after test run completes |
| **Run History** | Clickable rows open Playwright HTML reports; Self-Heal rows show triage stats |
| **Console Output** | Live streaming test output via WebSocket with smooth collapse |
| **Cross-Device Sync** | Start tests on iPhone, watch results on desktop (and vice versa) |
| **Late-Join Replay** | New clients see last run's results without needing to be connected during the run |
| **Domain Locking** | Domain list locked during/after test runs, unlocked on CLEAR |
| **Agent Tooltips** | Hover any eval card for agent role, description, model, capabilities |
| **Event-Driven Updates** | Zero polling — health, eval, and test data push via WebSocket |
| **Mobile Responsive** | 2-column grids on iPhone, optimized for touch |

### Run the Dashboard

```bash
# Direct
uvicorn qa_agent.dashboard.server:app --host 0.0.0.0 --port 8080

# Via Docker
cd qa_agent/dashboard
docker-compose up -d

# Access
open http://localhost:8080                    # Desktop
open http://<your-local-ip>:8080             # iPhone/iPad on same WiFi
```

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/health/latest` | Latest health with partial run merging |
| `GET` | `/api/health/history` | Last 20 runs (test + self-heal) |
| `POST` | `/api/health/notify` | Event-driven health update broadcast |
| `GET` | `/api/eval/summary` | All 4 agent scores + cumulative token/cost |
| `GET` | `/api/eval/{agent}/latest` | Latest eval for specific agent |
| `POST` | `/api/eval/run` | Trigger agent evals (per-agent or all, parallel) |
| `GET` | `/api/eval/run/status` | Current eval runner state |
| `POST` | `/api/eval/stop` | Stop running evals |
| `POST` | `/api/eval/notify` | Event-driven eval update broadcast |
| `GET` | `/api/audit/summary` | Total tokens, cost, per-run breakdown |
| `POST` | `/api/tests/run` | Start test run with specs/workers/retries/heal |
| `POST` | `/api/tests/stop` | Kill running subprocess |
| `POST` | `/api/tests/clear` | Clear runner state (syncs across devices) |
| `GET` | `/api/tests/status` | Current runner state |
| `GET` | `/api/tests/lastrun` | Last run's log for late-joining clients |
| `GET` | `/api/eval/ecc/scores` | All 12 ECC agent scores + metrics |
| `GET` | `/api/eval/ecc/scores/{agent}` | Specific ECC agent scorecard |
| `POST` | `/api/eval/ecc/run` | Trigger ECC evals (per-agent, per-tier, or all) |
| `GET` | `/api/eval/ecc/status` | Current ECC eval running state |
| `GET` | `/api/eval/ecc/history/{agent}` | Historical ECC eval data for trends |
| `POST` | `/api/eval/ecc/broadcast` | CLI-to-dashboard event relay |
| `GET` | `/report/{run_id}` | Serve Playwright HTML report |
| `WS` | `/ws/dashboard` | Browser live updates |
| `WS` | `/ws/tests` | Test output streaming |

---

## Test Suite — 127 Tests, 14 Domains

All tests run against the live [campingworld.com](https://www.campingworld.com) site with Page Object Model architecture.

| Domain | Spec File | Tests | Critical | Weight |
|--------|-----------|-------|----------|--------|
| **Cart** | `cart.spec.ts` | 8 | ★ | 2.0x |
| **Checkout** | `checkout.spec.ts` | 4 | ★ | 2.0x |
| **Sign In** | `sign-in.spec.ts` | 10 | ★ | 1.5x |
| **Search** | `search.spec.ts` | 9 | | 1.5x |
| **Product** | `product.spec.ts` | 9 | | 1.5x |
| **Homepage** | `homepage.spec.ts` | 13 | | 1.0x |
| **Nav** | `nav.spec.ts` | 14 | | 1.0x |
| **Register** | `register.spec.ts` | 6 | | 1.0x |
| **Store Locator** | `store-locator.spec.ts` | 10 | | 1.0x |
| **Good Sam** | `good-sam.spec.ts` | 6 | | 1.0x |
| **RV Parts** | `rv-parts.spec.ts` | 5 | | 1.0x |
| **RVs For Sale** | `rvs-for-sale.spec.ts` | 10 | | 1.0x |
| **RV Detail** | `rvs-for-sale-detail.spec.ts` | 10 | | 1.5x |
| **Footer** | `footer.spec.ts` | 13 | | 0.5x |

### Running Tests

```bash
# All tests
./run-tests.sh

# Specific domain
./run-tests.sh cart.spec.ts

# From the dashboard
# Open http://localhost:8080, select domains, click RUN
```

Each run automatically:
1. Executes tests with Playwright
2. Saves results to `test-results/{timestamp}/`
3. Computes health score → `health-reports/{timestamp}.json`
4. Triggers self-healing on failures (if enabled)
5. Commits and pushes health report to GitHub
6. Pushes real-time updates to all connected dashboards

---

## Site Health Score

Weighted scoring system that prioritizes revenue-critical paths.

```
Overall Health = Σ(domain_score × weight) / Σ(weight)

Thresholds:
  HEALTHY  ≥ 95%    (green)
  DEGRADED   80-94%   (amber)
  CRITICAL   < 80%    (red)
```

**Partial run merging** — Run just "Cart" from the dashboard and its domain card updates immediately while other domains keep their scores from the last full run.

**Trend tracking** — Each report compares vs. previous score (improving/declining/stable).

---

## Self-Healing Pipeline

```
Test Failure → Triage Agent → Classification
                                  │
                    ┌─────────────┼──────────────┐
                    ▼             ▼              ▼
              locator_drift   test_flake      app_defect
                    │             │              │
                    ▼             ▼              ▼
               Healer Agent   Healer Agent   Defect Report
               (fix locator)  (add waitFor)  (file Jira)
                    │             │
                    ▼             ▼
               Re-run fixed test
```

The Healer handles **two types** of failures:
- **Locator drift** — patches drifted selectors in Page Object files
- **Timing flakes** — adds `waitFor()` synchronization in spec files (e.g., `scrollIntoViewIfNeeded` before element is in DOM)

The triage agent uses a **5-criteria confidence rubric** (C1-C5) with anti-inflation guards and **historical test stability analysis**:

| Criterion | What it measures |
|-----------|-----------------|
| **C1** Error type signal | Is the error clearly drift, flake, or defect? |
| **C2** DOM evidence | Does the DOM show the element renamed or absent? |
| **C3** Historical pattern | Has this error been seen before? |
| **C4** Human calibration | Do past human decisions agree? |
| **C5** Consistency check | Do multiple signals agree? |

**Historical awareness** — Triage checks `TEST_STABILITY.md` and health report history. If a test passed 8/8 yesterday and fails today, that's strong evidence of a flake, not a defect.

**Triage reports** now include full context: LLM reasoning, C1-C5 confidence breakdown, error message, and human-readable explanation of why a failure wasn't healed.

---

## Agent Evaluation System

16 agents benchmarked against 201 golden scenarios with regression detection.

### Pipeline Agent Evals (4 agents, 63 scenarios)

```bash
qa-agent eval --agent all                      # All 4 pipeline agents
qa-agent eval --agent triage --threshold 0.75  # Single agent
```

| Agent | Metrics | Golden Scenarios |
|-------|---------|-----------------|
| **Triage** | Classification accuracy (drift/flake/defect) | 35 labeled failure cases |
| **Planner** | AC coverage, test case quality | 8 planning scenarios |
| **Generator** | Locator quality, POM validity, test validity | 5+ generation scenarios |
| **Healer** | Locator fix + timing fix accuracy (60/40 weighted) | 10 locator + 5 timing scenarios |

### ECC Development Agent Evals (12 agents, 138 scenarios)

```bash
qa-agent eval --ecc                            # All 12 ECC agents (parallel)
qa-agent eval --ecc --agent security-reviewer  # Single agent
qa-agent eval --ecc --tier detection           # 7 detection agents only
qa-agent eval --ecc --tier generative          # 5 generative agents only
qa-agent eval --ecc --dry                      # Validate golden datasets only
```

**Detection Agents** — scored on recall (did it find planted issues?) with data-driven thresholds from baseline runs:

| Agent | Recall Threshold | Golden Scenarios | What It Detects |
|-------|-----------------|-----------------|-----------------|
| **security-reviewer** | 90% | 20 (15 vulns + 5 clean) | SQL injection, XSS, secrets, path traversal, SSRF |
| **code-reviewer** | 70% | 15 (10 issues + 5 clean) | Large functions, deep nesting, mutation, dead code |
| **silent-failure-hunter** | 95% | 15 (12 issues + 3 clean) | Empty catches, lost traces, log-and-forget |
| **python-reviewer** | 95% | 12 (9 issues + 3 clean) | PEP 8, type hints, eval/pickle, mutable defaults |
| **typescript-reviewer** | 95% | 12 (9 issues + 3 clean) | any types, missing await, React hooks, eval |
| **fastapi-reviewer** | 66% | 10 (7 issues + 3 clean) | Sync-in-async, Pydantic misuse, missing middleware |
| **performance-optimizer** | 81% | 10 (7 issues + 3 clean) | O(n²) loops, memory leaks, N+1 queries |

**Generative Agents** — scored by LLM judge (Claude Haiku) on 5 quality dimensions:

| Agent | Quality Threshold | Golden Scenarios | What It Produces |
|-------|------------------|-----------------|-----------------|
| **planner-ecc** | 70% | 8 scenarios | Implementation plans with phases, risks, file paths |
| **tdd-guide** | 70% | 8 scenarios | TDD workflow: test-first, AAA pattern, edge cases |
| **build-error-resolver** | 70% | 10 (8 errors + 2 clean) | Minimal-diff fixes for type/import/config errors |
| **e2e-runner** | 70% | 8 (6 tasks + 2 clean) | Playwright tests, flaky fixes, locator updates |
| **refactor-cleaner** | 70% | 10 (7 dead code + 3 live) | Dead code detection, duplicate consolidation |

Quality dimensions: Completeness, Actionability, Correctness, Risk Awareness, Convention Adherence.

### Eval Infrastructure

- **Parallel execution** — All agents run concurrently via `asyncio.gather`
- **Per-card progress bars** — Live `[X/N]` scenario progress during eval runs
- **CLI-to-dashboard sync** — CLI evals broadcast progress to dashboard via `/api/eval/ecc/broadcast`
- **Persistent running state** — Dashboard shows eval progress even after page refresh
- **Cumulative token/cost tracking** — Odometer-style per-agent totals
- **Anti-overfitting safeguards** — File backfill tracked separately from extractor recall
- **Data-driven thresholds** — Set from 3-run baselines using worst - 5% formula

Reports: `qa_agent/eval/reports/{agent}/` (pipeline) and `qa_agent/eval/ecc/reports/{agent}/` (ECC).

---

## Audit Trail

Every agent invocation is tracked with token counts and costs.

| Tracked Data | Description |
|-------------|-------------|
| Node execution | Name, inputs, outputs, duration |
| LLM calls | Input/output tokens, cost (USD) |
| Prompt versions | SHA256 hash of system prompts |
| Memory context | Files read, similar failures found |
| Routing decisions | Which path the agent took and why |
| Timing fixes | Strategy used, element, error pattern, success/failure |

Storage: `memory/AUDIT_TRAIL.md` (human-readable) + `memory/audit_runs/*.json` (machine-readable)

---

## Architecture

### 10-Node LangGraph Agent

| Node | Type | Model | Purpose |
|------|------|-------|---------|
| **Design Reader** | AI | Sonnet | Figma MCP → structured UI spec |
| **Planner** | AI | Sonnet | UI spec + AC → categorized test cases |
| **Generator** | AI | Sonnet | Test plan → page objects + Playwright specs |
| **Executor** | Runner | — | Runs `npx playwright test`, captures results |
| **Triage** | AI | Sonnet | Classifies failure (drift/flake/defect) + confidence rubric |
| **Healer** | AI | Sonnet | Patches locators OR adds timing waits (never assertions) |
| **Human Review** | Human | — | LangGraph `interrupt()` for low-confidence cases |
| **Defect Report** | System | — | Files deduped Jira ticket via Atlassian MCP |
| **Metrics** | System | — | Records runs + triage calls to markdown |

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Orchestration** | LangGraph StateGraph, Python 3.11+ |
| **LLM** | Claude Opus + Sonnet via `langchain-anthropic` |
| **Browser** | Playwright (127 tests, 14 domains) |
| **Dashboard** | FastAPI + WebSocket + Vanilla JS (event-driven, zero polling) |
| **Design** | Figma MCP |
| **Tickets** | Atlassian MCP (Jira) |
| **Containerization** | Docker + docker-compose |
| **Generated Tests** | TypeScript `@playwright/test` with POM |
| **Memory** | Git-tracked markdown (14 files, zero databases) |
| **Eval** | Custom harness: 16 agents, 201 golden scenarios, LLM judge, parallel execution |
| **Audit** | Dual-format (Markdown + JSON) with token tracking |

---

## Safety Guardrails

| Guardrail | What it prevents |
|-----------|-----------------|
| **Assertion guardrail** | Healer can never modify `expect()`, `toBeVisible()`, etc. |
| **Hard wait guardrail** | Healer can never add `page.waitForTimeout()` (anti-pattern) |
| **Confidence gate** | Triage defers to humans when unsure (< 0.75) |
| **MAX_ATTEMPTS** | Heal loop bounded to 3 attempts |
| **Anti-inflation guards** | First-seen capped at 0.8, no DOM capped at 0.5 |
| **Token budget** | Per-run ceiling (500K tokens) |
| **Prompt-injection guards** | 12 regex patterns strip injections from Figma/DOM text |
| **File locking** | `fcntl.flock` on all memory writes |

---

## Agent Memory (7 Phases)

Git-tracked markdown files in `memory/` — human-readable, PR-reviewable, zero databases.

```
memory/
├── locators/              # Per-route locator drift history
├── audit_runs/            # JSON audit trail per run
├── retrospectives/        # Retrospective report history
├── APP_STRUCTURE.md       # Known routes, testids, change frequency
├── AUDIT_TRAIL.md         # Human-readable execution timeline
├── CONFIDENCE_RUBRIC.md   # 5-criteria Triage scoring rubric
├── ESCAPES.md             # Bugs that slipped past green runs
├── FAILURES.md            # Recurring error patterns + resolutions
├── HEALER_STATS.md        # Cache hit vs LLM call counts
├── HUMAN_DECISIONS.md     # Every Human Review verdict + reasoning
├── LESSONS.md             # Pattern scoreboard + route insights
├── RUN_HISTORY.md         # Every run: passed/failed, outcome
├── TEST_STABILITY.md      # Per-test flakiness scores
├── TIMING_FIXES.md        # Known timing fix cache (waitFor patterns)
├── TRIAGE_CALLS.md        # Every Triage classification for audit
└── WEEKLY_REVIEW.md       # Periodic self-grading with prescriptions
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+ (for Playwright)
- Anthropic API key

### Setup

```bash
git clone https://github.com/operator13/qa-automation-agent.git
cd qa-automation-agent

python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.template .env
# Add ANTHROPIC_API_KEY to .env
```

### Run Tests

```bash
# All 127 tests
./run-tests.sh

# Single domain
./run-tests.sh cart.spec.ts

# From dashboard
uvicorn qa_agent.dashboard.server:app --host 0.0.0.0 --port 8080
open http://localhost:8080
```

### CLI Commands

```bash
# Agent
qa-agent run --source jira:QA-123              # From Jira ticket
qa-agent run --source figma:FILE/NODE          # From Figma design

# Testing
qa-agent health                                # Show latest health score
qa-agent triage --results results.json         # Self-heal failures
qa-agent eval --agent all                      # Benchmark 4 pipeline agents
qa-agent eval --ecc                            # Benchmark 12 ECC dev agents
qa-agent eval --ecc --agent security-reviewer  # Single ECC agent

# Dashboard
qa-agent dashboard                             # Launch web UI

# Memory
qa-agent memory stats                          # Entry counts + size
qa-agent memory prune --max-age 30             # Remove old entries
qa-agent memory learn                          # Generate lessons

# Review
qa-agent review weekly                         # Self-grading report
```

---

## Feature Roadmap

Build specs for planned features are in `features/`:

| Feature | Status | Spec |
|---------|--------|------|
| Healer Flaky Test Fix | **COMPLETE** | [HEALER_FLAKY_TEST_FIX.md](features/HEALER_FLAKY_TEST_FIX.md) |
| Dashboard Test Runner | **COMPLETE** | [DASHBOARD_TEST_RUNNER.md](features/DASHBOARD_TEST_RUNNER.md) |
| Dashboard Eval Runner | **COMPLETE** | [DASHBOARD_EVAL_RUNNER.md](features/DASHBOARD_EVAL_RUNNER.md) |
| Agent Audit Trail | **COMPLETE** | [AGENT_AUDIT_TRAIL.md](features/AGENT_AUDIT_TRAIL.md) |
| Pipeline Eval Agent | **COMPLETE** | [BUILD_SPEC_EVAL_AGENT.md](features/BUILD_SPEC_EVAL_AGENT.md) |
| QA Command Center | **COMPLETE** | [QA_COMMAND_CENTER_DASHBOARD.md](features/QA_COMMAND_CENTER_DASHBOARD.md) |
| ECC Agent Evals (Phase 1-4) | **COMPLETE** | [ECC_AGENT_EVALS.md](features/ECC_AGENT_EVALS.md) |
| ECC Anti-Overfitting | PLANNED | [ECC_EVAL_ANTI_OVERFITTING.md](features/ECC_EVAL_ANTI_OVERFITTING.md) |
| Dashboard Security Hardening | **COMPLETE** | 9 vulnerabilities patched (path traversal, code injection, auth, XSS, WebSocket) |
| Guild.AI Dashboard Alignment | PLANNED | [GUILD_AI_DASHBOARD_ALIGNMENT.md](features/GUILD_AI_DASHBOARD_ALIGNMENT.md) |
| Human Review Notifications | PLANNED | [HUMAN_REVIEW_NOTIFICATIONS.md](features/HUMAN_REVIEW_NOTIFICATIONS.md) |
| Retrospective Agent | PLANNED | [RETROSPECTIVE_AGENT.md](features/RETROSPECTIVE_AGENT.md) |
| ngrok Public Sharing | PLANNED | [NGROK_PUBLIC_SHARING.md](features/NGROK_PUBLIC_SHARING.md) |

---

## Project Structure

```
qa-automation-agent/
├── qa_agent/
│   ├── dashboard/                  # QA Command Center
│   │   ├── server.py               # FastAPI + WebSocket (20+ endpoints)
│   │   ├── Dockerfile              # Container config
│   │   ├── docker-compose.yml      # Docker orchestration
│   │   └── static/                 # Cyberpunk UI (HTML/JS/CSS)
│   ├── eval/                       # Agent evaluation system
│   │   ├── eval_runner.py          # Pipeline eval execution (4 agents)
│   │   ├── golden/                 # Pipeline golden datasets (63 scenarios)
│   │   ├── reports/                # Pipeline eval results
│   │   └── ecc/                    # ECC development agent evals
│   │       ├── ecc_eval_runner.py  # Parallel ECC eval orchestrator
│   │       ├── agent_invoker.py    # Anthropic API agent invocation
│   │       ├── finding_extractor.py # Agent output → structured findings
│   │       ├── finding_matcher.py  # Findings → planted issue matching
│   │       ├── llm_judge.py        # LLM-as-judge for generative agents
│   │       ├── golden/             # 12 agent golden datasets (138 scenarios)
│   │       └── reports/            # ECC eval results per agent
│   ├── nodes/                      # LangGraph agent nodes
│   │   ├── triage.py               # Failure classification (drift/flake/defect)
│   │   ├── healer.py               # Locator repair + timing fix
│   │   ├── planner.py              # Test planning
│   │   ├── generator.py            # Test generation
│   │   └── ...                     # 10 nodes total
│   ├── health.py                   # Weighted health scoring
│   ├── audit.py                    # Execution audit trail
│   ├── triage_runner.py            # Self-healing pipeline
│   ├── confidence.py               # 5-criteria rubric + flake detection
│   ├── memory.py                   # Markdown-backed memory store
│   └── prompts/                    # System prompts (editable markdown)
├── tests_generated/                # 14 Playwright spec files (127 tests)
├── page_objects/                   # 15 Page Object Models
├── test-results/                   # Timestamped run archives
├── health-reports/                 # Health score history (git-tracked)
├── memory/                         # Agent memory (14 markdown files)
├── features/                       # Feature build specs (20 specs)
├── run-tests.sh                    # Test runner script
└── pyproject.toml                  # Python project config
```

---

## Author

**QA Automation Portfolio Project**
AI-powered test automation with self-healing, flaky test detection, confidence-gated triage, real-time dashboard, event-driven architecture, and cross-run learning for QA Lead / Staff QA Engineer roles.

---

## License

MIT License - See [LICENSE](LICENSE) for details.
