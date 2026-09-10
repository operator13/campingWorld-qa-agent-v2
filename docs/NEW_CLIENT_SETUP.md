# New Client Setup Guide

This guide explains how to use the QA Agent Framework for a new client project.

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- Anthropic API key
- (Optional) Figma token, Jira credentials, LangSmith API key

## Quick Start

```bash
# 1. Clone the framework
git clone https://github.com/operator13/qa-agent-framework.git qa-agent-toyota
cd qa-agent-toyota

# 2. Run the init script
./init-new-client.sh --url https://www.toyota.com --name "Toyota"

# 3. Copy and configure your environment
cp .env.template .env
# Edit .env with your API keys

# 4. Install dependencies
pip install -e ".[dev]"
npm install

# 5. Launch the dashboard
cd qa_agent/dashboard
docker compose up -d

# 6. Open http://localhost:8080
```

## What the Init Script Does

`./init-new-client.sh --url <URL> --name <NAME>` performs 7 steps to reset the framework:

### Step 1: Clear Test Specs and Page Objects

Deletes all generated Playwright test files and page object classes:

- `tests_generated/*.spec.ts` — all domain-specific E2E test specs
- `page_objects/*.ts` — all Page Object Model classes

These are client-specific and must be regenerated for your target site.

### Step 2: Clear Health Reports and Test Results

- `health-reports/*.json` and `*.md` — per-run health scores
- `test-results/*/` — Playwright HTML reports and trace files

### Step 3: Clear Eval Reports

- `qa_agent/eval/reports/*.json` and `*.md` — pipeline agent eval results
- `qa_agent/eval/ecc/reports/*.json` — development agent (ECC) eval results

### Step 4: Reset Memory Files

Memory files in `memory/` are truncated to their headers (first 3 lines), preserving the file structure but clearing all client-specific learned data:

- Audit runs (`memory/audit_runs/*.json`)
- Locator snapshots (`memory/locators/*`)
- Retrospectives (`memory/retrospectives/*`)

### Step 5: Update Playwright Config

Sets `baseURL` in `playwright.config.ts` to your target URL:

```typescript
// Before
baseURL: 'https://www.campingworld.com'

// After (example)
baseURL: 'https://www.toyota.com'
```

### Step 6: Clear Dashboard Configuration

Resets the dashboard UI to an empty state:

- **DOMAINS array** in `qa_agent/dashboard/static/app.js` — cleared to an empty array with placeholder comments
- **ALLOWED_SPECS** in `qa_agent/dashboard/server.py` and `worker.py` — cleared to empty sets

You must populate these after generating your test specs.

### Step 7: Update Project Metadata

- Renames the project in `pyproject.toml` (e.g., `qa-agent-toyota`)
- Deletes `.ecc_eval_status.json` and any screenshots

## After Running the Init Script

### 1. Configure Environment Variables

Copy `.env.template` to `.env` and fill in your keys:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for LLM agents |
| `FIGMA_TOKEN` | No | For generating specs from Figma designs |
| `JIRA_PROJECT_KEY` | No | For generating specs from Jira tickets |
| `APP_BASE_URL` | No | Override for local development URLs |
| `LANGSMITH_API_KEY` | No | For LangSmith tracing/observability |
| `DASHBOARD_API_TOKEN` | No | API auth for production deployments |

### 2. Generate Test Specs

Use the CLI to generate Playwright specs from your design sources:

```bash
# From a Figma design
qa-agent run --source figma:FILE_KEY/NODE_ID

# From a Jira ticket
qa-agent run --source jira:TICKET-123

# Or manually create specs in tests_generated/
```

### 3. Configure the Dashboard

After generating specs, update these files:

**`qa_agent/dashboard/static/app.js`** — Add your domains to the DOMAINS array:

```javascript
const DOMAINS = [
  {spec: "homepage.spec.ts", label: "Homepage", tests: 12, critical: true},
  {spec: "search.spec.ts", label: "Search", tests: 8, critical: true},
  {spec: "cart.spec.ts", label: "Cart", tests: 15, critical: true},
];
```

**`qa_agent/dashboard/server.py`** and **`worker.py`** — Add your specs to ALLOWED_SPECS:

```python
ALLOWED_SPECS = {
    "homepage.spec.ts",
    "search.spec.ts",
    "cart.spec.ts",
}
```

### 4. Launch the Dashboard

```bash
cd qa_agent/dashboard
docker compose up -d
```

The dashboard runs as two containers:

| Container | Port | Role |
|-----------|------|------|
| **dashboard** | 8080 | Read-only web UI, serves static files, proxies requests to worker |
| **worker** | 8081 | Runs evals, Playwright tests, and Claude CLI — requires API keys |

Open `http://localhost:8080` to access the QA Command Center.

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│                  Browser (UI)               │
│              http://localhost:8080           │
└──────────────────┬──────────────────────────┘
                   │ WebSocket + REST
                   ▼
┌──────────────────────────────────────────────┐
│           Dashboard Server (:8080)           │
│  - Serves static UI (HTML/CSS/JS)            │
│  - WebSocket fan-out to all connected tabs   │
│  - Proxies RUN/STOP requests to worker       │
│  - Read-only access to shared data dirs      │
│  - No secrets, no API keys                   │
└──────────────────┬───────────────────────────┘
                   │ HTTP proxy
                   ▼
┌──────────────────────────────────────────────┐
│            Eval Worker (:8081)               │
│  - Runs pipeline agent evals (4 agents)      │
│  - Runs ECC development agent evals (12)     │
│  - Runs Playwright test suites               │
│  - Has ANTHROPIC_API_KEY, Node.js, Claude    │
│  - Broadcasts progress → dashboard → browser │
└──────────────────────────────────────────────┘
```

**Data flow**: Both containers share bind-mounted host directories for health reports, eval reports, test results, and audit trails. The worker writes; the dashboard reads.

## Directory Structure

```
qa-agent-<client>/
├── init-new-client.sh          # One-time setup script
├── .env.template               # Environment variable template
├── .env                        # Your secrets (git-ignored)
├── pyproject.toml              # Python project config
├── playwright.config.ts        # Playwright settings
├── package.json                # Node.js dependencies
│
├── qa_agent/                   # Main Python package
│   ├── nodes/                  # 9 LangGraph pipeline nodes
│   ├── prompts/                # Editable system prompts (markdown)
│   ├── config.py               # Runtime config (thresholds, models)
│   ├── eval/                   # Agent evaluation system
│   │   ├── golden/             # Golden datasets for benchmarks
│   │   ├── reports/            # Pipeline eval results
│   │   └── ecc/                # ECC agent eval system + reports
│   └── dashboard/              # FastAPI web UI
│       ├── server.py           # Dashboard server (read-only)
│       ├── worker.py           # Eval worker (runs tests)
│       ├── docker-compose.yml  # Two-container deployment
│       ├── Dockerfile          # Dashboard image
│       ├── Dockerfile.worker   # Worker image
│       └── static/             # HTML, CSS, JS
│
├── tests_generated/            # Playwright spec files (generated)
├── page_objects/               # Page Object Model classes (generated)
├── tests/                      # pytest test suite
├── memory/                     # Git-tracked agent memory
├── health-reports/             # Per-run health scores
└── docs/                       # Documentation
```

## CLI Reference

```bash
qa-agent run --dry                      # Compile graph, list MCP tools
qa-agent run --source jira:QA-123       # Generate specs from Jira ticket
qa-agent run --source figma:FILE/NODE   # Generate specs from Figma design
qa-agent health                         # Show latest health score
qa-agent triage --results results.json  # Self-heal test failures
qa-agent eval --agent all               # Benchmark all 4 pipeline agents
qa-agent dashboard                      # Launch web UI
qa-agent memory stats                   # Memory usage stats
qa-agent review weekly                  # Self-grading report
```

## Cloud Deployment

See the deployment guides for production hosting:

- [Deploy to GCP Cloud Run](DEPLOY_CLOUD_RUN.md)
- [Deploy to AWS ECS Fargate](DEPLOY_ECS.md)
