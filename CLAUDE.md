# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**campingWorld-qa-agent-v2** is an AI-powered QA automation framework for [campingworld.com](https://www.campingworld.com). It combines LangGraph orchestration, Playwright browser automation, and self-healing capabilities into a closed-loop testing pipeline.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Orchestration | LangGraph `StateGraph` (Python 3.11+) |
| LLM | Claude Sonnet 4.6 / Opus via `langchain-anthropic` |
| Browser Automation | Playwright (`@playwright/test` 1.52.0, TypeScript) |
| Dashboard | FastAPI + WebSocket + Vanilla JS |
| MCP Integrations | Figma, Atlassian (Jira), Playwright |
| Memory | Git-tracked markdown files (zero databases) |
| Testing | pytest (30+ modules) |

## Architecture

9-node LangGraph StateGraph:
```
design_reader -> planner -> generator -> executor
                                          |
                                    [pass -> metrics -> END]
                                    [fail -> triage]
                                          |
                         [sure drift/flake -> healer -> executor (retry)]
                         [sure defect -> defect_report -> metrics -> END]
                         [unsure -> human_review -> (dynamic)]
```

### Key Directories

- `qa_agent/` - Main Python package (nodes, prompts, config, memory, dashboard, eval)
- `qa_agent/nodes/` - 9 LLM/system nodes (triage, healer, planner, generator, executor, etc.)
- `qa_agent/prompts/` - Editable system prompts (markdown)
- `qa_agent/dashboard/` - FastAPI web UI with WebSocket
- `qa_agent/eval/` - Agent evaluation system with golden datasets
- `tests/` - pytest test suite (30+ modules)
- `tests_generated/` - 14 Playwright spec files (127 tests across 14 domains)
- `page_objects/` - 15 TypeScript Page Object Model classes
- `memory/` - Git-tracked agent memory (14 markdown files)
- `features/` - Build specs and feature roadmap
- `health-reports/` - Per-run health scores

## Running Tests

```bash
# Playwright E2E tests (all domains)
./run-tests.sh

# Specific domain
./run-tests.sh cart.spec.ts

# Python unit/integration tests
pytest tests/ -v

# Agent evaluation
python -m qa_agent.eval.run_eval

# With coverage
pytest tests/ --cov=qa_agent --cov-report=term-missing
```

## CLI Commands

```bash
qa-agent run --dry                      # Compile graph, list MCP tools
qa-agent run --source jira:QA-123       # From Jira ticket
qa-agent run --source figma:FILE/NODE   # From Figma design
qa-agent health                         # Latest health score
qa-agent triage --results results.json  # Self-heal failures
qa-agent eval --agent all               # Benchmark all 4 agents
qa-agent dashboard                      # Launch web UI
qa-agent memory stats                   # Memory stats
qa-agent review weekly                  # Self-grading report
```

## Development Guidelines

### Python Code (`qa_agent/`)

- Follow PEP 8 + type annotations on all function signatures
- Use `async def` for I/O operations (FastAPI, MCP clients)
- Use `dataclasses` or Pydantic models for data containers
- Use `logging` module, never `print()` in production code
- Format with `black` and lint with `ruff`
- File locking (`fcntl.flock()`) on all memory writes

### TypeScript Code (`page_objects/`, `tests_generated/`)

- Page Object Model pattern with semantic locators (`data-testid`)
- Use auto-wait locators, never `page.waitForTimeout()`
- Keep assertions in spec files, not page objects
- No `console.log` in generated specs

### Testing Requirements

- 80%+ coverage target
- New nodes require matching tests in `tests/`
- Golden datasets in `qa_agent/eval/golden/` for eval benchmarks
- AAA pattern (Arrange-Act-Assert) for all tests

### Commit Style

- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`, `perf:`

## Configuration

- `.env` for secrets (`ANTHROPIC_API_KEY`, `FIGMA_TOKEN`, `JIRA_*`, `LANGSMITH_API_KEY`)
- `qa_agent/config.py` for runtime config (confidence thresholds, model map, pricing)
- `playwright.config.ts` for Playwright settings (3 workers, 1 retry, 30s timeout)
- `pyproject.toml` for Python dependencies

## ECC Integration

This project uses [Everything Claude Code (ECC)](https://github.com/affaan-m/ECC) for development guardrails:

### Installed Components

**Rules** (`.claude/rules/ecc/`):
- `common/` - Universal coding style, security, testing, git workflow, performance
- `python/` - PEP 8, FastAPI patterns, Python security, pytest
- `typescript/` - Type safety, Playwright patterns, TS security

**Agents** (`.claude/agents/`):
- `e2e-runner` - Playwright test execution and maintenance
- `security-reviewer` - Vulnerability detection (OWASP Top 10)
- `python-reviewer` - Python code quality (mypy, ruff, bandit)
- `typescript-reviewer` - TypeScript type safety and async correctness
- `code-reviewer` - General code quality gate
- `silent-failure-hunter` - Finds swallowed errors and dangerous fallbacks
- `planner` - Feature implementation planning (Opus)
- `build-error-resolver` - Minimal-diff build fixes
- `performance-optimizer` - Performance analysis and optimization
- `fastapi-reviewer` - FastAPI-specific code review
- `tdd-guide` - Test-driven development workflow
- `refactor-cleaner` - Dead code cleanup

**Skills** (`.claude/skills/`):
- `e2e-testing` - Playwright POM patterns and flaky test remediation
- `browser-qa` - 4-phase QA (smoke, interaction, visual, accessibility)
- `python-patterns` - Pythonic idioms and design patterns
- `python-testing` - pytest fixtures, async testing, TDD
- `fastapi-patterns` - FastAPI production patterns
- `docker-patterns` - Container security and multi-stage builds
- `security-review` - Pre-deployment security checklist
- `agent-eval` - Agent comparison and benchmarking
- `agent-self-evaluation` - 5-axis self-assessment rubric
- `agentic-engineering` - Eval-first agent execution
- `continuous-agent-loop` - Loop architecture patterns
- `tdd-workflow` - RED-GREEN-REFACTOR cycle
- `jira-integration` - Jira MCP patterns and ticket analysis

**Hooks** (`.claude/settings.json`):
- Pre-edit: Config protection, fact-forcing gate, compaction suggestions
- Post-edit: Auto-format (Prettier/black), type checking, console.log detection
- Session: Context persistence, pattern extraction, cost tracking, desktop notifications

### Skills Reference

| Area | Skill to invoke |
|------|----------------|
| Writing/fixing Playwright tests | `e2e-testing`, `browser-qa` |
| Python node development | `python-patterns`, `python-testing` |
| Dashboard work | `fastapi-patterns` |
| Eval system changes | `agent-eval`, `agent-self-evaluation` |
| Self-healing loop design | `agentic-engineering`, `continuous-agent-loop` |
| Security hardening | `security-review` |
| Docker/deployment | `docker-patterns` |
| Jira integration | `jira-integration` |
| New feature planning | Use `planner` agent |
| Test-first development | `tdd-workflow` |
