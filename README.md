# QA Automation AI Agent

[![Tests](https://img.shields.io/badge/tests-219%20passing-brightgreen)](https://github.com)
[![Graph Nodes](https://img.shields.io/badge/graph%20nodes-10-blue)](https://github.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-4f46e5?logo=python)](https://langchain-ai.github.io/langgraph/)
[![Playwright](https://img.shields.io/badge/Playwright-1.62+-2EAD33?logo=playwright)](https://playwright.dev/)
[![Claude](https://img.shields.io/badge/Claude-Opus%20%2B%20Sonnet-d97706?logo=anthropic)](https://anthropic.com/)

An **AI-powered QA automation framework** that reads Figma designs and Jira tickets, generates Playwright tests with page objects, runs them, and self-heals when locators drift — with a confidence-gated triage system that defers to humans when it isn't sure. Built with **LangGraph**, **Claude**, and **MCP**.

## Key Highlights

- **10-node LangGraph agent** with confidence-gated triage and self-healing loop
- **3 MCP integrations** — Playwright (browser), Figma (design), Atlassian (Jira)
- **Assertion guardrail** — Healer can fix locators but provably never touches assertions
- **Human-in-the-loop** — low-confidence failures pause for human review via LangGraph `interrupt()`
- **Agent memory** — markdown-backed cross-run learning (known fixes, failure patterns, human decisions)
- **Eval harness** — scores AC coverage, locator quality, and Triage accuracy against golden fixtures
- **219 automated tests** covering all nodes, routers, memory, guardrails, and integrations

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
| **Memory** | Git-tracked markdown files | Cross-run learning (locator history, failure patterns) |
| **Metrics** | SQLite | Run history, escape rate, Triage accuracy |
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
| **Triage** | AI | Opus | Classifies failure (locator drift vs app defect) + confidence 0–1 |
| **Healer** | AI | Sonnet | Patches drifted locators in page objects (never assertions) |
| **Human Review** | Human | — | LangGraph `interrupt()` for low-confidence cases |
| **Defect Report** | System | — | Files deduped Jira ticket via Atlassian MCP |
| **Metrics** | System | — | Records every run + Triage call to SQLite |

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
| **Confidence gate** | Triage defers to humans when unsure (< 0.75) — no guessing on the fence |
| **MAX_ATTEMPTS** | Heal loop is bounded (3 attempts) — no infinite retries |
| **Memory validation** | Known-fix fast path still runs through the assertion guardrail before applying |
| **Stale fix protection** | Failed fixes are marked `success: no` and excluded from future lookups |
| **Prompt-injection guards** | 12 regex patterns strip injection attempts from Figma/DOM text |
| **Token budget** | Per-run ceiling (500K tokens) prevents runaway costs |
| **Kill switches** | `MEMORY_ENABLED`, `HEALER_MEMORY`, `TRIAGE_MEMORY` — disable per-node |

---

## Agent Memory

Git-tracked markdown files in `memory/` that persist across runs — human-readable, editable, PR-reviewable.

| File | What it stores | Who writes | Who reads |
|------|---------------|------------|-----------|
| `memory/locators/CHECKOUT.md` | Locator drift history per route | Healer | Healer, Generator |
| `memory/FAILURES.md` | Recurring error signatures + resolutions | Triage, Healer | Triage, Healer |
| `memory/HUMAN_DECISIONS.md` | Every Human Review verdict + reasoning | Human Review | Triage (calibration) |

### How memory improves each run

- **Healer** checks for known fixes before calling the LLM — instant repair, no API cost
- **Triage** receives past human corrections as few-shot calibration context
- **Triage** matches against similar past failures for classification hints

---

## 219 Automated Tests

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
| **Metrics** | 9 | MetricsDB CRUD, escape rate, accuracy |
| **Eval** | 13 | AC coverage, locator quality, Triage accuracy, golden fixtures |
| **Memory** | 53 | Locator CRUD, known fix, mark failed, failure patterns, human decisions, calibration, kill switch, integration |
| **Cache** | 8 | Hash, round-trip, invalidation |
| **Sanitizer** | 18 | Injection patterns, DOM, Figma elements, false positives |
| **Observability** | 8 | Alerts, auto-tuning, report |
| **Budget** | 10 | Token tracking, exhaustion, concurrency |
| **PR Gate** | 3 | PR body generation |
| **TOTAL** | **219** | |

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

## Project Structure

```
qa-automation-agent/
├── qa_agent/
│   ├── state.py                    # QAState shared state schema
│   ├── config.py                   # Env, thresholds, model map
│   ├── graph.py                    # StateGraph wiring (10 nodes, 2 routers)
│   ├── cli.py                      # CLI entrypoint
│   ├── memory.py                   # MemoryStore (markdown-backed)
│   ├── cache.py                    # Determinism cache
│   ├── sanitizer.py                # Prompt-injection guards
│   ├── observability.py            # Escape-rate alerts, auto-tuning
│   ├── budget.py                   # Token budget + concurrency limiter
│   ├── intake/                     # Jira MCP + Figma intake adapters
│   │   ├── base.py                 # Intake protocol + IntakeResult
│   │   ├── jira.py                 # Jira MCP adapter
│   │   └── figma.py                # Figma REST adapter
│   ├── nodes/                      # One file per graph node
│   │   ├── design_reader.py        # Figma → ExpectedUI
│   │   ├── planner.py              # UI spec + AC → test cases
│   │   ├── generator.py            # Test plan → page objects + specs
│   │   ├── executor.py             # Runs Playwright tests
│   │   ├── triage.py               # Failure classification + confidence
│   │   ├── healer.py               # Locator repair (memory-enhanced)
│   │   ├── defect_report.py        # Jira ticket filing
│   │   └── metrics.py              # Run + Triage call recording
│   ├── mcp/                        # MCP client configs
│   │   ├── figma_client.py         # Figma MCP (HTTP)
│   │   ├── playwright_client.py    # Playwright MCP (stdio)
│   │   └── atlassian_client.py     # Atlassian MCP (stdio)
│   ├── prompts/                    # System prompt per AI node
│   ├── schemas/                    # Pydantic I/O models
│   ├── surfaces/                   # Human review, Jira defect, PR gate
│   └── eval/                       # Eval harness + golden fixtures
├── memory/                         # Git-tracked agent memory (markdown)
│   ├── locators/                   # Per-route locator history
│   ├── FAILURES.md                 # Recurring failure patterns
│   └── HUMAN_DECISIONS.md          # Human Review verdicts
├── page_objects/                    # Generated page objects (one per route)
├── tests_generated/                # Generated Playwright specs
├── tests/                          # 219 automated tests
├── features/                       # Feature build specs (backlog)
├── .github/workflows/              # Nightly CI workflow
├── PROJECT_STATUS.md               # Phase tracking (100% complete)
├── CHANGELOG.md                    # Commit-level change history
└── pyproject.toml                  # Python project config
```

---

## CLI Commands

```bash
qa-agent run --dry                        # Compile graph + test MCP connections
qa-agent run --source jira:QA-123         # Run from Jira ticket
qa-agent run --source figma:FILE/NODE     # Run from Figma design
qa-agent run --source jira:X --source figma:Y  # Both sources
qa-agent run --dry --verbose              # Debug logging
```

---

## Feature Roadmap

Build specs for all planned features are in `features/`:

| Feature | Status | Spec |
|---------|--------|------|
| Agent Memory (M1-M2) | DONE | [MEMORY.md](features/MEMORY.md) |
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

## Skills Demonstrated

| Category | Skills |
|----------|--------|
| **AI Engineering** | LangGraph agent orchestration, structured LLM output, prompt engineering, confidence calibration |
| **QA Automation** | Playwright test generation, Page Object Model, self-healing tests, assertion guardrails |
| **MCP Integration** | Multi-server MCP clients (Figma, Playwright, Atlassian), tool binding |
| **Software Architecture** | Graph-based state machines, conditional routing, human-in-the-loop patterns |
| **Testing** | 219 automated tests, table-driven parametrized tests, mocked LLM integration tests |
| **Observability** | Metrics DB, escape-rate tracking, Triage accuracy auditing, auto-threshold tuning |
| **Security** | Prompt-injection guards, assertion guardrails, token budget controls |
| **DevOps** | GitHub Actions CI, nightly workflows, PR gate automation |

---

## Author

**QA Automation Portfolio Project**
Demonstrating AI-powered test automation with self-healing capabilities, confidence-gated triage, and human-in-the-loop safety for QA Lead / Staff QA Engineer roles.

---

## License

MIT License - See [LICENSE](LICENSE) for details.
