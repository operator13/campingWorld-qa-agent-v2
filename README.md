# QA Automation AI Agent

[![Tests](https://img.shields.io/badge/tests-355%20passing-brightgreen)](https://github.com)
[![Graph Nodes](https://img.shields.io/badge/graph%20nodes-10-blue)](https://github.com)
[![Memory Phases](https://img.shields.io/badge/memory-M1--M7%20complete-purple)](https://github.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-4f46e5?logo=python)](https://langchain-ai.github.io/langgraph/)
[![Playwright](https://img.shields.io/badge/Playwright-1.62+-2EAD33?logo=playwright)](https://playwright.dev/)
[![Claude](https://img.shields.io/badge/Claude-Opus%20%2B%20Sonnet-d97706?logo=anthropic)](https://anthropic.com/)

An **AI-powered QA automation framework** that reads Figma designs and Jira tickets, generates Playwright tests with page objects, runs them, and self-heals when locators drift — with a confidence-gated triage system that defers to humans when it isn't sure. Built with **LangGraph**, **Claude**, and **MCP**.

## Key Highlights

- **10-node LangGraph agent** with confidence-gated triage and self-healing loop
- **3 MCP integrations** — Playwright (browser), Figma (design), Atlassian (Jira)
- **Assertion guardrail** — Healer can fix locators but provably never touches assertions
- **Human-in-the-loop** — low-confidence failures pause for human review via LangGraph `interrupt()`
- **7-phase agent memory** — markdown-backed cross-run learning with pattern scoreboard, weekly self-grading, and formal confidence rubric
- **Zero databases** — all storage is git-tracked markdown (memory, metrics, prompts)
- **Formal confidence rubric** — 5-criteria scoring with anti-inflation guards (not loose "rate 0-1")
- **Weekly self-grading** — automated performance reviews with letter grades and prescriptions
- **Eval harness** — scores AC coverage, locator quality, and Triage accuracy against golden fixtures
- **355 automated tests** covering all nodes, routers, memory, guardrails, and integrations
- **3 rounds of pre-mortems** — 68 issues identified and fixed across the memory system

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         QA AUTOMATION AI AGENT                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
    │   FIGMA      │     │    JIRA      │     │  PLAYWRIGHT  │     │   CLAUDE     │
    │   MCP        │────▶│    MCP       │────▶│    MCP       │────▶│   LLM        │
    │  (Design)    │     │  (Tickets)   │     │  (Browser)   │     │  (Reasoning) │
    └──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
           │                    │                    │                    │
           ▼                    ▼                    ▼                    ▼
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                          LANGGRAPH STATE GRAPH                              │
    │                                                                             │
    │  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
    │  │ DESIGN  │─▶│ PLANNER │─▶│GENERATOR │─▶│ EXECUTOR │─▶│  PASS? → END  │  │
    │  │ READER  │  │         │  │          │  │          │  │  FAIL? ↓      │  │
    │  └─────────┘  └─────────┘  └──────────┘  └──────────┘  └───────────────┘  │
    │                                                                ↓           │
    │                              ┌──────────────────────────────────────────┐   │
    │                              │           FAILURE PANEL                  │   │
    │                              │                                          │   │
    │                              │  ┌────────┐     ┌─────────────────────┐  │   │
    │                              │  │TRIAGE  │────▶│ SURE DRIFT → HEALER│──┼───│──▶ EXECUTOR (retry)
    │                              │  │        │     │ SURE BUG  → DEFECT │  │   │
    │                              │  │        │     │ UNSURE   → HUMAN   │  │   │
    │                              │  └────────┘     └─────────────────────┘  │   │
    │                              └──────────────────────────────────────────┘   │
    │                                                         │                  │
    │  ┌──────────┐                                           │                  │
    │  │ METRICS  │◀──────────────────────────────────────────┘                  │
    │  │          │──▶ END                                                       │
    │  └──────────┘                                                              │
    └─────────────────────────────────────────────────────────────────────────────┘
```

### Agent Flow

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                            CONFIDENCE-GATED FLOW                               │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  ┌───────┐    ┌─────────┐    ┌─────────┐    ┌──────────┐    ┌──────────┐      │
│  │ START │───▶│ DESIGN  │───▶│ PLANNER │───▶│GENERATOR │───▶│ EXECUTOR │      │
│  └───────┘    │ READER  │    │ (Opus)  │    │ (Sonnet) │    │(Playwrt) │      │
│               └─────────┘    └─────────┘    └──────────┘    └─────┬────┘      │
│                                                                   │           │
│                                               ┌───────────────────┤           │
│                                               ▼                   ▼           │
│                                          ┌─────────┐        ┌─────────┐       │
│                                          │  PASS   │        │  FAIL   │       │
│                                          │ → END   │        │→ TRIAGE │       │
│                                          └─────────┘        └────┬────┘       │
│                                                                  │            │
│                    ┌─────────────────────────┬───────────────────┤            │
│                    ▼                         ▼                   ▼            │
│              ┌──────────┐             ┌────────────┐      ┌──────────┐       │
│              │  HEALER  │             │   HUMAN    │      │  DEFECT  │       │
│              │(fix loc) │             │  REVIEW    │      │  REPORT  │       │
│              └────┬─────┘             └──────┬─────┘      └──────────┘       │
│                   │                     heal │ defect              │          │
│                   ▼                      ▼   ▼                    ▼          │
│              ┌──────────┐          ┌────────┐ ┌────────┐    ┌──────────┐     │
│              │ EXECUTOR │          │ HEALER │ │ DEFECT │    │ METRICS  │     │
│              │ (retry)  │          └────────┘ │ REPORT │    │  → END   │     │
│              └──────────┘                     └────────┘    └──────────┘     │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Orchestration** | LangGraph StateGraph, Python 3.11+ | Node-based agent graph with conditional routing |
| **LLM** | Claude Opus + Sonnet via `langchain-anthropic` | Structured reasoning per node (Pydantic tool-calling) |
| **Browser** | Playwright MCP | Drives the browser for test execution |
| **Design** | Figma MCP | Reads designs for UI spec extraction |
| **Tickets** | Atlassian MCP | Reads Jira tickets, files deduped bug reports |
| **Generated Tests** | TypeScript `@playwright/test` | Page Object Model with resilient locators |
| **Memory** | Git-tracked markdown files | Cross-run learning — all 12 memory files |
| **Metrics** | Git-tracked markdown files | Run history, escape rate, Triage accuracy |
| **Prompts** | Markdown files | System prompts loaded at runtime — editable without code changes |
| **Eval** | Custom harness | AC coverage, locator quality, Triage accuracy scoring |
| **CI** | GitHub Actions | Nightly tests + eval gate + agent run |
| **Observability** | LangSmith + custom alerts | Token tracing, escape-rate alerts, auto-tuning |

---

## Agent Nodes

### 10 Nodes — 6 AI, 1 Human, 2 System, 1 Metrics

| Node | Type | Model | Purpose |
|------|------|-------|---------|
| **Design Reader** | AI | Sonnet | Figma MCP → structured `ExpectedUI` spec |
| **Planner** | AI | Opus | UI spec + acceptance criteria → categorized test cases |
| **Generator** | AI | Sonnet | Test plan → page objects + Playwright spec files |
| **Executor** | AI/Runner | — | Writes files, runs `npx playwright test`, captures results |
| **Triage** | AI | Opus | Classifies failure (locator drift vs app defect) + 5-criteria confidence rubric |
| **Healer** | AI | Sonnet | Patches drifted locators in page objects (never assertions) — memory-enhanced |
| **Human Review** | Human | — | LangGraph `interrupt()` for low-confidence cases — records decisions to memory |
| **Defect Report** | System | — | Files deduped Jira ticket via Atlassian MCP — records failure patterns |
| **Metrics** | System | — | Records every run + Triage call to markdown |

### Routing Logic

```python
CONF_SURE    = 0.75   # >= this => Triage acts automatically
MAX_ATTEMPTS = 3      # heal attempts before escalating to a bug

def route_after_triage(state):
    if state.attempts >= MAX_ATTEMPTS:   return "defect_report"
    if state.confidence < CONF_SURE:     return "human_review"
    if state.failure_class == "locator_drift": return "healer"
    return "defect_report"
```

---

## Safety Guardrails

| Guardrail | What it prevents |
|-----------|-----------------|
| **Assertion guardrail** | Healer can never modify `expect()`, `toBeVisible()`, `toHaveText()`, etc. — any diff touching assertions is rejected |
| **Confidence rubric** | 5-criteria scoring (C1-C5) with 4 anti-inflation guards — no loose "rate 0-1" |
| **Confidence gate** | Triage defers to humans when unsure (< 0.75) — no guessing on the fence |
| **MAX_ATTEMPTS** | Heal loop is bounded (3 attempts) — no infinite retries |
| **Memory validation** | Known-fix fast path runs through assertion guardrail before applying |
| **Stale fix protection** | Fixes recorded as unverified; executor confirms on re-run; failed fixes excluded |
| **Prompt-injection guards** | 12 regex patterns strip injection attempts from Figma/DOM text + memory content sanitized before prompt injection |
| **Token budget** | Per-run ceiling (500K tokens) prevents runaway costs |
| **File locking** | `fcntl.flock` on all memory writes with Windows fallback — prevents concurrent corruption |
| **Kill switches** | `MEMORY_ENABLED`, `HEALER_MEMORY`, `TRIAGE_MEMORY`, `PLANNER_MEMORY`, `GENERATOR_MEMORY`, `LESSONS_MEMORY` |

---

## Agent Memory (7 Phases Complete)

Git-tracked markdown files in `memory/` that persist across runs — human-readable, editable, PR-reviewable. Zero databases.

```
memory/
├── locators/              # Per-route locator drift history
│   ├── CHECKOUT.md
│   └── LOGIN.md
├── APP_STRUCTURE.md       # Known routes, testids, change frequency
├── CONFIDENCE_RUBRIC.md   # 5-criteria Triage scoring rubric
├── ESCAPES.md             # Bugs that slipped past green runs
├── FAILURES.md            # Recurring error patterns + resolutions
├── HEALER_STATS.md        # Cache hit vs LLM call counts
├── HUMAN_DECISIONS.md     # Every Human Review verdict + reasoning
├── LESSONS.md             # Pattern scoreboard + route insights + reflections
├── RUN_HISTORY.md         # Every run: passed/failed, outcome
├── TEST_STABILITY.md      # Per-test pass/fail history, flakiness scores
├── TRIAGE_CALLS.md        # Every Triage classification for audit
└── WEEKLY_REVIEW.md       # Periodic self-grading with prescriptions
```

### Memory Phases

| Phase | What it does | Key capability |
|-------|-------------|----------------|
| **M1** | Healer remembers past fixes | Known-fix fast path — instant repair, no LLM call |
| **M2** | Triage calibration from human corrections | Few-shot calibration context in Triage prompt |
| **M3** | App structure + Planner intelligence | Volatile route detection, flaky test flagging |
| **M4** | Memory maintenance | TTL pruning, dedup, stats CLI (`qa-agent memory stats`) |
| **M5** | Lessons learned | Pattern scoreboard, route insights, decision reflections |
| **M6** | Weekly self-grading | Letter grades (A-F), trend arrows, prescriptions |
| **M7** | Formal confidence rubric | 5-criteria scoring with anti-inflation guards |

### How memory improves each run

- **Healer** checks for known fixes before calling the LLM — instant repair, no API cost
- **Healer** reads locator history to pick more durable selectors
- **Triage** receives past human corrections as few-shot calibration context
- **Triage** matches against similar past failures for classification hints
- **Triage** uses 5-criteria rubric pre-scored from memory data
- **Planner** prioritizes volatile routes and flags flaky tests
- **Generator** uses known testid prefixes and avoids locators that drifted before
- **All nodes** receive synthesized lessons (pattern scoreboard, route insights)

---

## Confidence Rubric

Triage confidence is scored with a formal 5-criteria rubric, not a loose "rate 0-1":

| Criterion | Scores | What it measures |
|-----------|--------|-----------------|
| **C1** Error type signal | 0.0–0.2 | Is the error clearly drift or clearly defect? |
| **C2** DOM evidence | 0.0–0.2 | Does the DOM show the element renamed or absent? |
| **C3** Historical pattern | 0.0–0.2 | Has this error been seen before? |
| **C4** Human calibration | 0.0–0.2 | Do past human decisions agree? |
| **C5** Consistency check | 0.0–0.2 | Do multiple signals agree? |

**Anti-inflation guards:**
- First-seen error → capped at 0.7
- Humans overridden 2+ times → capped at 0.6
- No DOM snapshot → capped at 0.5
- Timeout without DOM → capped at 0.6

---

## 355 Automated Tests

### Test Summary by Category

| Category | Count | Description |
|----------|-------|-------------|
| **State + schemas** | 5 | QAState round-trip, reducer, Pydantic models |
| **Config** | 5 | Constants, model map, env loading, route map |
| **Graph** | 6 | Compilation, node presence, node count |
| **Intake** | 10 | Jira/Figma parsing, ADF, URL extraction |
| **AI Nodes** | 5 | Design Reader, Planner, Generator, Executor (mocked LLM) |
| **Routers** | 22 | Table-driven: every (failure_class, confidence, attempts) combo |
| **Triage** | 7 | Parser, clamping, code blocks, mocked LLM |
| **Healer + guardrail** | 13 | Assertion reject/accept, mocked LLM, guardrail enforcement |
| **Human Review** | 7 | Routing decisions, defaults, payload |
| **Jira Defect** | 10 | Fingerprint, dedup, payload structure |
| **Defect Report** | 4 | Report builder, MCP integration |
| **Metrics** | 11 | Markdown-backed CRUD, escape rate, accuracy, unique IDs |
| **Eval** | 13 | AC coverage, locator quality, Triage accuracy, golden fixtures |
| **Memory** | 120+ | Locator CRUD, known fix, mark failed, failure patterns, human decisions, calibration, app structure, test stability, lessons, weekly review, confidence rubric, kill switches, integration |
| **Cache** | 8 | Hash, round-trip, invalidation |
| **Sanitizer** | 18 | Injection patterns, DOM, Figma elements, false positives |
| **Observability** | 8 | Alerts, auto-tuning, report |
| **Budget** | 10 | Token tracking, exhaustion, concurrency |
| **PR Gate** | 3 | PR body generation |
| **Confidence** | 35 | Criteria scoring, guards, full scoring, consistency |
| **Weekly Review** | 25 | Grading, trends, prescriptions, CLI |
| **Pre-mortem regressions** | 15 | Targeted tests for each fixed issue |
| **TOTAL** | **355** | |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+ (for Playwright + MCP servers)
- Anthropic API key ([Get yours here](https://console.anthropic.com/settings/keys))

### 1. Clone and Setup

```bash
git clone https://github.com/operator13/qa-automation-agent.git
cd qa-automation-agent

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### 2. Configure Environment

```bash
cp .env.template .env

# Edit .env and add your Anthropic API key:
# ANTHROPIC_API_KEY=sk-ant-your-key-here

# Set your app URL:
# APP_BASE_URL=http://localhost:3000
```

### 3. Verify Setup

```bash
# Compile the graph and test MCP connections
qa-agent run --dry

# Run all tests
python -m pytest tests/ -v
```

### 4. Run the Agent

```bash
# From a Jira ticket
qa-agent run --source jira:QA-123

# From a Figma design
qa-agent run --source figma:FILE_KEY/NODE_ID

# Both sources (AC from Jira, design from Figma)
qa-agent run --source jira:QA-123 --source figma:FILE_KEY/NODE_ID
```

---

## CLI Commands

```bash
# Run the agent
qa-agent run --dry                              # Compile graph + test MCP connections
qa-agent run --source jira:QA-123               # Run from Jira ticket
qa-agent run --source figma:FILE/NODE           # Run from Figma design
qa-agent run --source jira:X --source figma:Y   # Both sources
qa-agent run --dry --verbose                    # Debug logging

# Memory management
qa-agent memory stats                           # Show memory entry counts + size
qa-agent memory prune                           # Remove entries older than 90 days
qa-agent memory prune --max-age 30              # Custom TTL
qa-agent memory learn                           # Generate lessons from accumulated data

# Weekly review
qa-agent review weekly                          # Generate weekly self-grading report
```

---

## Project Structure

```
qa-automation-agent/
├── qa_agent/
│   ├── state.py                    # QAState shared state schema
│   ├── config.py                   # Env, thresholds, model map
│   ├── graph.py                    # StateGraph wiring (10 nodes, 2 routers)
│   ├── cli.py                      # CLI entrypoint (run, memory, review)
│   ├── memory.py                   # MemoryStore (markdown-backed, file-locked)
│   ├── confidence.py               # 5-criteria rubric scorer + anti-inflation guards
│   ├── weekly_review.py            # Periodic self-grading with grades + prescriptions
│   ├── cache.py                    # Determinism cache
│   ├── sanitizer.py                # Prompt-injection guards
│   ├── observability.py            # Escape-rate alerts, auto-tuning
│   ├── budget.py                   # Token budget + concurrency limiter
│   ├── intake/                     # Jira MCP + Figma intake adapters
│   ├── nodes/                      # One file per graph node (the agents)
│   │   ├── design_reader.py        # Figma → ExpectedUI
│   │   ├── planner.py              # UI spec + AC → test cases (memory-enhanced)
│   │   ├── generator.py            # Test plan → page objects + specs (memory-enhanced)
│   │   ├── executor.py             # Runs Playwright tests, verifies fixes
│   │   ├── triage.py               # Failure classification + rubric scoring (memory-enhanced)
│   │   ├── healer.py               # Locator repair with known-fix cache (memory-enhanced)
│   │   ├── defect_report.py        # Jira ticket filing + failure pattern recording
│   │   └── metrics.py              # Run + Triage call recording (markdown-backed)
│   ├── mcp/                        # MCP client configs
│   │   ├── figma_client.py         # Figma MCP (HTTP)
│   │   ├── playwright_client.py    # Playwright MCP (stdio)
│   │   └── atlassian_client.py     # Atlassian MCP (stdio)
│   ├── prompts/                    # System prompts (markdown files)
│   │   ├── DESIGN_READER.md
│   │   ├── PLANNER.md
│   │   ├── GENERATOR.md
│   │   ├── EXECUTOR.md
│   │   ├── TRIAGE.md
│   │   └── HEALER.md
│   ├── schemas/                    # Pydantic I/O models
│   ├── surfaces/                   # Human review, Jira defect, PR gate
│   └── eval/                       # Eval harness + golden fixtures
├── memory/                         # Git-tracked agent memory (12 markdown files)
├── page_objects/                    # Generated page objects (one per route)
├── tests_generated/                # Generated Playwright specs
├── tests/                          # 355 automated tests
├── features/                       # Feature build specs (10 specs)
├── .github/workflows/              # Nightly CI workflow
├── PROJECT_STATUS.md               # Phase tracking
├── CHANGELOG.md                    # Commit-level change history
└── pyproject.toml                  # Python project config
```

---

## Feature Roadmap

Build specs for all planned features are in `features/`:

| Feature | Status | Spec |
|---------|--------|------|
| Agent Memory (M1-M7) | **COMPLETE** | [MEMORY.md](features/MEMORY.md) |
| TPM Agent | PLANNED | [TPM_AGENT.md](features/TPM_AGENT.md) |
| Auto-Threshold Tuning | PLANNED | [AUTO_THRESHOLD_TUNING.md](features/AUTO_THRESHOLD_TUNING.md) |
| Red-Team Negative Path | PLANNED | [RED_TEAM_NEGATIVE_PATH.md](features/RED_TEAM_NEGATIVE_PATH.md) |
| Visual Regression + A11y | PLANNED | [VISUAL_REGRESSION_ACCESSIBILITY.md](features/VISUAL_REGRESSION_ACCESSIBILITY.md) |
| API Integration Testing | PLANNED | [API_INTEGRATION_TESTING.md](features/API_INTEGRATION_TESTING.md) |
| Per-Commit PR Gating | PLANNED | [PER_COMMIT_PR_GATING.md](features/PER_COMMIT_PR_GATING.md) |
| WebSocket Testing | PLANNED | [WEBSOCKET_TESTING.md](features/WEBSOCKET_TESTING.md) |
| Domain Knowledge Graph | PLANNED | [DOMAIN_KNOWLEDGE_GRAPH.md](features/DOMAIN_KNOWLEDGE_GRAPH.md) |
| Mobile Web Testing | PARTIAL | [MOBILE_WEB_TESTING.md](features/MOBILE_WEB_TESTING.md) |

---

## Pre-mortem Process

The memory system underwent **3 rounds of pre-mortems** with 68 total issues identified and fixed:

| Pass | Issues found | Fixed | Key findings |
|------|-------------|-------|-------------|
| 1 | 12 | 11 | Naive matching, assertion guardrail bypass, stale fix poisoning |
| 2 | 35 | 35 | TOCTOU races, prompt injection via memory, premature success recording |
| 3 | 21 | 19 | Windows crash in file locking, duplicate IDs, scoreboard never persisted |

15 regression tests were written specifically for the pre-mortem fixes.

---

## Skills Demonstrated

| Category | Skills |
|----------|--------|
| **AI Engineering** | LangGraph agent orchestration, structured LLM output, prompt engineering, confidence calibration, 5-criteria rubric design |
| **QA Automation** | Playwright test generation, Page Object Model, self-healing tests, assertion guardrails |
| **MCP Integration** | Multi-server MCP clients (Figma, Playwright, Atlassian), tool binding |
| **Software Architecture** | Graph-based state machines, conditional routing, human-in-the-loop patterns |
| **Memory Systems** | Markdown-backed cross-run learning, pattern recognition, weekly self-grading |
| **Testing** | 355 automated tests, table-driven parametrized tests, mocked LLM integration tests, regression tests from pre-mortems |
| **Observability** | Markdown metrics, escape-rate tracking, Triage accuracy auditing, auto-threshold tuning |
| **Security** | Prompt-injection guards, assertion guardrails, token budget controls, file locking, memory content sanitization |
| **DevOps** | GitHub Actions CI, nightly workflows, PR gate automation |
| **Process** | Pre-mortem analysis (3 rounds, 68 issues), feature build specs, phased implementation |

---

## Author

**QA Automation Portfolio Project**
Demonstrating AI-powered test automation with self-healing capabilities, confidence-gated triage, cross-run learning, and human-in-the-loop safety for QA Lead / Staff QA Engineer roles.

---

## License

MIT License - See [LICENSE](LICENSE) for details.
