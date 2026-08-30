# QA Automation AI Agent

[![Tests](https://img.shields.io/badge/Playwright-127%20tests%20%C2%B7%2014%20domains-2EAD33?logo=playwright)](https://playwright.dev/)
[![Health](https://img.shields.io/badge/health%20score-live%20dashboard-00ffc8)](https://github.com)
[![Agents](https://img.shields.io/badge/agents-4%20evaluated-4f46e5)](https://github.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-4f46e5?logo=python)](https://langchain-ai.github.io/langgraph/)
[![Claude](https://img.shields.io/badge/Claude-Opus%20%2B%20Sonnet-d97706?logo=anthropic)](https://anthropic.com/)
[![Docker](https://img.shields.io/badge/Docker-dashboard-2496ED?logo=docker)](https://docker.com/)

An **AI-powered QA automation framework** that generates Playwright tests, runs them against [campingworld.com](https://www.campingworld.com), self-heals when locators drift, and serves a real-time cyberpunk dashboard for monitoring health scores, triggering test runs, and tracking agent performance — all from your browser or phone. Built with **LangGraph**, **Claude**, **FastAPI**, and **WebSocket**.

---

## What It Does

```
                    ┌──────────────┐
                    │  DASHBOARD   │  Real-time health, test runner, agent evals
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
4. **Heal** — Triages failures, auto-fixes locator drift, defers to humans when unsure
5. **Evaluate** — Benchmarks 4 AI agents (Triage, Planner, Generator, Healer) against golden datasets
6. **Monitor** — Live dashboard with WebSocket streaming, accessible from desktop and mobile

---

## QA Command Center Dashboard

A real-time cyberpunk-themed dashboard for monitoring and controlling the entire QA pipeline from any device.

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
│  AGENT EVALUATION        │                                          │
│  Triage 90% │ Plan 97.8% │  Generator 100% │ Healer 100%           │
├──────────────────────────┼───────────────────────────────────────────┤
│  TEST RUNNER             │  RUN HISTORY                             │
│  Workers [1][2][●3][4]   │  2026-08-30 20:29  127  126  1  99.3%  │
│  Retries [●0][1]         │  2026-08-30 20:20  127  125  2  98.7%  │
│  Self-Heal [OFF][●ON]    │  2026-08-30 19:45   21   21  0 100.0%  │
│  [▶ RUN SELECTED][▶ ALL] │  ← Click any row to view HTML report    │
│  ○ ★ Cart      8 tests   │                                         │
│  ○ ★ Checkout  4 tests   │  SELF-HEAL rows show triage stats       │
│  ○ ★ Sign In  10 tests   │  (triaged / healed / unhealed)          │
│  ○   Search    9 tests   │                                         │
│  ...14 domains total      │                                         │
└──────────────────────────┴───────────────────────────────────────────┘
```

### Dashboard Features

| Feature | Description |
|---------|-------------|
| **Health Gauge** | SVG circular gauge with weighted overall score |
| **Domain Cards** | 14 cards showing per-domain pass rate, test counts, status |
| **Agent Eval Cards** | 4 cards with accuracy scores, token usage, cost per agent |
| **Test Runner** | Select domains, configure workers/retries, trigger from browser |
| **Self-Heal Toggle** | Auto-triage and fix failures after test run completes |
| **Run History** | Clickable rows open Playwright HTML reports in new tab |
| **Self-Heal Rows** | Purple badges showing triage/healed/unhealed counts |
| **Console Output** | Live streaming test output via WebSocket |
| **Cross-Device Sync** | Start tests on iPhone, watch results on desktop (and vice versa) |
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
| `GET` | `/api/eval/summary` | All 4 agent scores + token/cost data |
| `GET` | `/api/eval/{agent}/latest` | Latest eval for specific agent |
| `GET` | `/api/audit/summary` | Total tokens, cost, per-run breakdown |
| `POST` | `/api/tests/run` | Start test run with specs/workers/retries/heal |
| `POST` | `/api/tests/stop` | Kill running subprocess |
| `POST` | `/api/tests/clear` | Clear runner state (syncs across devices) |
| `GET` | `/api/tests/status` | Current runner state |
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
              locator_drift   app_defect      unsure
                    │             │              │
                    ▼             ▼              ▼
               Healer Agent   Defect Report   Human Review
               (fix locator)  (file Jira)     (interrupt)
                    │
                    ▼
               Re-run fixed test
```

The triage agent uses a **5-criteria confidence rubric** (C1-C5) with anti-inflation guards:

| Criterion | What it measures |
|-----------|-----------------|
| **C1** Error type signal | Is the error clearly drift or clearly defect? |
| **C2** DOM evidence | Does the DOM show the element renamed or absent? |
| **C3** Historical pattern | Has this error been seen before? |
| **C4** Human calibration | Do past human decisions agree? |
| **C5** Consistency check | Do multiple signals agree? |

**Current accuracy:** Triage 90%, Planner 97.8%, Generator 100%, Healer 100%

---

## Agent Evaluation System

4 agents benchmarked against golden datasets with regression detection.

```bash
# Run all evals
qa-agent eval --agent all

# Single agent
qa-agent eval --agent triage --threshold 0.75
```

| Agent | Metrics | Golden Scenarios |
|-------|---------|-----------------|
| **Triage** | Classification accuracy, confidence calibration | 10 labeled failure cases |
| **Planner** | AC coverage, test case quality | 5 planning scenarios |
| **Generator** | Locator quality, POM validity, test validity | 5 generation scenarios |
| **Healer** | Fix correctness, import correctness, diff minimality | 5 healing scenarios |

Reports auto-commit to `qa_agent/eval/reports/{agent}/` with PASS/FAIL/BASELINE status.

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

Storage: `memory/AUDIT_TRAIL.md` (human-readable) + `memory/audit_runs/*.json` (machine-readable)

---

## Architecture

### 10-Node LangGraph Agent

| Node | Type | Model | Purpose |
|------|------|-------|---------|
| **Design Reader** | AI | Sonnet | Figma MCP → structured UI spec |
| **Planner** | AI | Opus | UI spec + AC → categorized test cases |
| **Generator** | AI | Sonnet | Test plan → page objects + Playwright specs |
| **Executor** | Runner | — | Runs `npx playwright test`, captures results |
| **Triage** | AI | Opus | Classifies failure + 5-criteria confidence rubric |
| **Healer** | AI | Sonnet | Patches drifted locators (never assertions) |
| **Human Review** | Human | — | LangGraph `interrupt()` for low-confidence cases |
| **Defect Report** | System | — | Files deduped Jira ticket via Atlassian MCP |
| **Metrics** | System | — | Records runs + triage calls to markdown |

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Orchestration** | LangGraph StateGraph, Python 3.11+ |
| **LLM** | Claude Opus + Sonnet via `langchain-anthropic` |
| **Browser** | Playwright (127 tests, 14 domains) |
| **Dashboard** | FastAPI + WebSocket + Vanilla JS |
| **Design** | Figma MCP |
| **Tickets** | Atlassian MCP (Jira) |
| **Containerization** | Docker + docker-compose |
| **Generated Tests** | TypeScript `@playwright/test` with POM |
| **Memory** | Git-tracked markdown (12 files, zero databases) |
| **Eval** | Custom harness with golden datasets |
| **Audit** | Dual-format (Markdown + JSON) with token tracking |

---

## Safety Guardrails

| Guardrail | What it prevents |
|-----------|-----------------|
| **Assertion guardrail** | Healer can never modify `expect()`, `toBeVisible()`, etc. |
| **Confidence gate** | Triage defers to humans when unsure (< 0.75) |
| **MAX_ATTEMPTS** | Heal loop bounded to 3 attempts |
| **Anti-inflation guards** | First-seen capped at 0.7, no DOM capped at 0.5 |
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
qa-agent eval --agent all                      # Benchmark all agents

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

## Project Structure

```
qa-automation-agent/
├── qa_agent/
│   ├── dashboard/                  # QA Command Center
│   │   ├── server.py               # FastAPI + WebSocket (13 endpoints)
│   │   ├── Dockerfile              # Container config
│   │   ├── docker-compose.yml      # Docker orchestration
│   │   └── static/                 # Cyberpunk UI (HTML/JS/CSS)
│   ├── eval/                       # Agent evaluation system
│   │   ├── eval_runner.py          # Parallel eval execution
│   │   ├── golden/                 # Golden datasets (4 agents)
│   │   └── reports/                # Eval results (auto-committed)
│   ├── nodes/                      # LangGraph agent nodes
│   │   ├── triage.py               # Failure classification
│   │   ├── healer.py               # Locator repair
│   │   ├── planner.py              # Test planning
│   │   ├── generator.py            # Test generation
│   │   └── ...                     # 10 nodes total
│   ├── health.py                   # Weighted health scoring
│   ├── audit.py                    # Execution audit trail
│   ├── triage_runner.py            # Self-healing pipeline
│   ├── confidence.py               # 5-criteria rubric scorer
│   ├── memory.py                   # Markdown-backed memory store
│   └── prompts/                    # System prompts (editable markdown)
├── tests_generated/                # 14 Playwright spec files (127 tests)
├── page_objects/                   # 15 Page Object Models
├── test-results/                   # Timestamped run archives
├── health-reports/                 # Health score history (git-tracked)
├── memory/                         # Agent memory (12 markdown files)
├── run-tests.sh                    # Test runner script
└── pyproject.toml                  # Python project config
```

---

## Author

**QA Automation Portfolio Project**
AI-powered test automation with self-healing, confidence-gated triage, real-time dashboard, and cross-run learning for QA Lead / Staff QA Engineer roles.

---

## License

MIT License - See [LICENSE](LICENSE) for details.
