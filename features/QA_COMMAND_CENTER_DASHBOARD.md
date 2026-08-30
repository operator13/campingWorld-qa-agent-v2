# Feature: QA Command Center Dashboard

> A single-pane-of-glass dashboard showing site quality health scores per domain, overall site health, agent accuracy percentages, token costs per agent, triage activity, and trend history — everything needed to understand the state of campingworld.com QA at a glance.

**Status:** PLANNED
**Priority:** High
**Depends on:** Audit Trail (AT1-AT3), Eval Agent, Site Health Score, Triage Runner
**Inspired by:** Guild.ai Insights Dashboard, Weights & Biases Workspaces

---

## The Problem

Today, eval results, health scores, and triage reports live in JSON/markdown files scattered across directories. To understand the state of the system, you have to:
- Run `qa-agent eval run --agent all` and read terminal output
- Run `qa-agent health` and read terminal output
- Open JSON files in `health-reports/` and `qa_agent/eval/reports/`
- Manually compare scorecards across runs to spot trends

There's no single view that shows: "How healthy is the site? How are the agents performing? What's the cost trend? What got triaged and healed?"

## The Solution

A web-based dashboard served locally that pulls from existing data sources (health reports, eval scorecards, audit trail, triage reports) and renders interactive visualizations.

---

## The Three Core Metrics

Everything on the dashboard is organized around three questions:

1. **How healthy is the site?** → Domain health scores + overall score
2. **How accurate are the agents?** → Per-agent accuracy % with trend
3. **What does it cost?** → Token usage + USD cost per agent per run

---

## Dashboard Sections

### 1. Site Quality Health (Hero Section)

**Overall site health gauge** — large radial gauge, front and center:
- Score: weighted average across all 14 domains
- Color: Green (≥95% HEALTHY), Yellow (≥80% DEGRADED), Red (<80% CRITICAL)
- Number: "98.7% HEALTHY" in large text

**Domain quality grid** — 14 cards arranged in a responsive grid:

Each card shows:
- Domain name (e.g., "Cart", "Search", "Product Detail")
- Quality score: `9/9 = 100%`
- Health bar (filled proportionally, color-coded green/yellow/red)
- Status badge: HEALTHY / DEGRADED / CRITICAL
- Weight indicator: ★ for critical purchase path (Cart 2x, Checkout 2x, Sign In 1.5x)
- Cards glow red when CRITICAL, pulse amber when DEGRADED
- Click → drill down to individual test pass/fail list

**Trend line** — sparkline of overall health across last 10 runs, showing trajectory

### 2. Agent Accuracy Scores (4-Panel Grid)

Four cards, one per agent (Triage, Planner, Generator, Healer):

Each card shows:
- Agent name
- **Accuracy %** in large bold text (e.g., "90.0%")
- Pass/fail badge (green checkmark or red X)
- **What it measures** — subtitle text:
  - Triage: "Classification accuracy (30 scenarios)"
  - Planner: "AC coverage (8 scenarios)"
  - Generator: "Locator quality + POM/test validity (3 scenarios)"
  - Healer: "Fix correctness + assertion integrity (10 scenarios)"
- Mini bar chart: accuracy history over last 10 eval runs
- Trend arrow: ↑ improving, → stable, ↓ declining
- Last eval timestamp
- Click → drill down to: miss details, recommendations, confidence breakdown

### 3. Token Cost per Agent (Cost Panel)

**Stacked bar chart** — tokens consumed per agent per pipeline run:
- X-axis: run timestamps (last 20 runs)
- Y-axis: token count
- Stacked bars by agent:
  - Triage = blue
  - Planner = green
  - Generator = purple
  - Healer = orange
  - Executor/other = gray
- Hover: shows exact token count + estimated cost

**Cost timeline** — line chart overlay showing $ cost per run

**KPI strip across the top:**
| Metric | Example |
|--------|---------|
| Total tokens (all time) | 142,350 |
| Total cost (all time) | $2.84 |
| Avg cost per run | $0.11 |
| Most expensive agent | Generator ($0.06/run) |
| Cheapest agent | Executor ($0.00) |

**Per-agent cost table:**
| Agent | Avg Tokens In | Avg Tokens Out | Avg Cost/Run |
|-------|--------------|----------------|-------------|
| Triage | 3,857 | 312 | $0.016 |
| Planner | 561 | 1,807 | $0.029 |
| Generator | 2,684 | 3,180 | $0.056 |
| Healer | 1,200 | 800 | $0.016 |

Data source: `memory/audit_runs/*.json`

### 4. Triage & Self-Healing Activity

**Timeline view** — chronological list of triage events:
- Each entry shows: timestamp, spec file, test title, classification, confidence, healed/skipped badge
- Color coded: green (healed), yellow (app_defect), gray (unknown)

**Heal success rate** — donut chart:
- Healed vs. App Defect vs. Unknown vs. Failed to Heal

**Recent activity feed** — last 5 triage actions with expandable details

Data source: `health-reports/*-triage.json`

### 5. Run History & Comparison

**Table view** — all test runs with columns:
- Timestamp, Total Tests, Passed, Failed, Health %, Duration, Status

**Compare mode** — select 2 runs and see side-by-side:
- Which domains changed (green=improved, red=regressed)
- Which tests flipped (was passing, now failing)

Data source: `health-reports/*.json`

---

## Technology Decision: Three.js vs Alternatives

### Three.js Assessment

Three.js is a **3D rendering engine** designed for WebGL scenes, 3D models, and spatial visualizations. For a metrics dashboard with charts, gauges, and tables, it would be:

- **Overkill** — we need 2D charts, not 3D scenes
- **Heavy** — 600KB+ bundle for visualizations that don't need 3D
- **Poor accessibility** — canvas-based rendering breaks screen readers
- **Hard to maintain** — custom shader code for what should be a chart

**Verdict: Do NOT use Three.js.**

### Recommended Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| **Framework** | Vanilla HTML + Tailwind CSS | Simple, no build step, served as static files |
| **Charts** | Chart.js (lightweight) or D3.js (powerful) | Purpose-built for data visualization |
| **Gauges** | Custom SVG (radial gauge) | Clean, lightweight, accessible |
| **Server** | FastAPI (Python) | Serves static files + JSON API, async-native |
| **Data** | Read JSON files from disk | No database needed — files already exist |
| **Interactivity** | Alpine.js (3KB) | Minimal reactive framework for drill-downs |
| **Container** | Docker + Docker Compose | Isolated, reproducible, one-command deploy |

### Why This Stack

1. **Containerized** — `docker compose up` and the dashboard is running
2. **Data already exists** — health reports, eval scorecards, audit JSON are all on disk, mounted into the container
3. **Lightweight** — Chart.js is 60KB (vs Three.js 600KB+)
4. **Accessible** — real DOM elements, not canvas blobs
5. **Maintainable** — HTML/CSS that any developer can modify
6. **Portable** — runs the same on any machine with Docker

---

## Docker Architecture

### Container Layout

```
┌─────────────────────────────────────────────────┐
│              Docker Compose Stack                 │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │  qa-dashboard (FastAPI + static files)       │ │
│  │  Port: 8080                                  │ │
│  │  Image: python:3.11-slim                     │ │
│  │                                              │ │
│  │  Volumes (read-only mounts):                 │ │
│  │    ./health-reports    → /data/health        │ │
│  │    ./qa_agent/eval/reports → /data/eval      │ │
│  │    ./memory/audit_runs → /data/audit         │ │
│  │    ./test-results      → /data/test-results  │ │
│  └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY qa_agent/dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy dashboard code
COPY qa_agent/dashboard/ ./dashboard/

# Data directories mounted at runtime via docker-compose
# /data/health, /data/eval, /data/audit, /data/test-results

EXPOSE 8080

CMD ["uvicorn", "dashboard.server:app", "--host", "0.0.0.0", "--port", "8080"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  dashboard:
    build:
      context: .
      dockerfile: qa_agent/dashboard/Dockerfile
    ports:
      - "8080:8080"
    volumes:
      # Mount data directories read-only — dashboard never writes
      - ./health-reports:/data/health:ro
      - ./qa_agent/eval/reports:/data/eval:ro
      - ./memory/audit_runs:/data/audit:ro
      - ./test-results:/data/test-results:ro
    environment:
      - DATA_DIR=/data
    restart: unless-stopped
```

### Key Design Decisions

1. **Read-only volume mounts** — the dashboard container never writes to your project. It only reads JSON files produced by test runs and eval runs.

2. **No database** — the container doesn't run Postgres, Redis, or any data store. It reads files on every API request. When tests run on the host and produce new reports, the dashboard sees them immediately (volume mount).

3. **Single container** — no multi-service orchestration needed. One container serves both the API and the static frontend.

4. **Hot reload in dev** — mount the dashboard source code as a volume for live editing:
   ```yaml
   volumes:
     - ./qa_agent/dashboard:/app/dashboard  # dev mode
   ```

5. **Lightweight image** — `python:3.11-slim` (~150MB) with FastAPI + uvicorn (~20MB of pip deps). Total image size < 200MB.

---

## File Structure

```
qa_agent/dashboard/
├── Dockerfile              # Container image definition
├── docker-compose.yml      # One-command deployment
├── requirements.txt        # FastAPI, uvicorn, jinja2
├── server.py               # FastAPI app + JSON API endpoints
├── static/
│   ├── index.html          # Main dashboard page
│   ├── styles.css          # Tailwind-based styles
│   ├── app.js              # Dashboard logic + Chart.js rendering
│   └── components/
│       ├── health-gauge.js    # Radial SVG gauge
│       ├── domain-grid.js     # Domain health cards
│       ├── eval-cards.js      # Agent eval scorecard
│       ├── cost-chart.js      # Token/cost timeline
│       ├── triage-feed.js     # Triage activity timeline
│       └── run-history.js     # Run comparison table
```

### API Endpoints (served by `server.py`)

```
GET /api/health/latest       → latest health.json
GET /api/health/history      → last 20 health reports
GET /api/eval/{agent}/latest → latest eval scorecard
GET /api/eval/{agent}/history → last 10 eval runs
GET /api/audit/recent        → last 10 audit trail entries
GET /api/triage/recent       → last 10 triage reports
GET /api/cost/summary        → aggregated token/cost data
```

Each endpoint reads directly from disk — no database:
- `/api/health/*` reads from `health-reports/*.json`
- `/api/eval/*` reads from `qa_agent/eval/reports/{agent}/*.json`
- `/api/audit/*` reads from `memory/audit_runs/*.json`
- `/api/triage/*` reads from `health-reports/*-triage.json`

---

## Dashboard Layout (ASCII Wireframe)

```
┌─────────────────────────────────────────────────────────────────┐
│                    CampingWorld QA Dashboard                     │
├──────────────────────┬──────────────────────────────────────────┤
│                      │                                          │
│   ┌──────────────┐   │  Domain Health Grid                      │
│   │              │   │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐   │
│   │   98.7%      │   │  │Home  │ │Nav   │ │Search│ │Product│  │
│   │  HEALTHY     │   │  │100%  │ │100%  │ │100%  │ │100%  │   │
│   │  ◉━━━━━━━━━  │   │  └──────┘ └──────┘ └──────┘ └──────┘   │
│   │              │   │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐   │
│   └──────────────┘   │  │Cart★ │ │Check★│ │SignIn│ │Regist│   │
│   Trend: ▁▂▃▅▇█      │  │100%  │ │100%  │ │100%  │ │100%  │   │
│                      │  └──────┘ └──────┘ └──────┘ └──────┘   │
├──────────────────────┴──────────────────────────────────────────┤
│  Agent Eval Scores                                              │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐      │
│  │ Triage    │ │ Planner   │ │ Generator │ │ Healer    │      │
│  │ 90.0%  ✓  │ │ 97.8%  ✓  │ │ 100%   ✓  │ │ 100%   ✓  │      │
│  │ ▁▃▅▇█▇▇█ │ │ ▇▇▇▇█▇▇█ │ │ ████████ │ │ ████████ │      │
│  │ → stable  │ │ → stable  │ │ → stable  │ │ → stable  │      │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘      │
├─────────────────────────────┬───────────────────────────────────┤
│ Cost & Tokens               │ Triage Activity                   │
│                             │                                   │
│  █▓░                        │ 10:04 cart.spec.ts                │
│  █▓▒░                       │   locator_drift → HEALED ✓       │
│  ██▓▒░                      │ 09:44 nav.spec.ts                │
│  ███▓▒░                     │   app_defect → SKIPPED           │
│  ████▓▒░                    │ 09:37 product.spec.ts            │
│  Total: $0.42 | 12K tokens  │   unknown → NEEDS REVIEW         │
├─────────────────────────────┴───────────────────────────────────┤
│ Run History                                                     │
│ ┌──────────────┬───────┬────────┬────────┬───────┬──────────┐  │
│ │ Timestamp    │ Tests │ Passed │ Failed │ Health│ Status    │  │
│ ├──────────────┼───────┼────────┼────────┼───────┼──────────┤  │
│ │ 08/30 10:04  │  127  │  127   │   0    │ 100%  │ HEALTHY  │  │
│ │ 08/30 09:44  │  127  │  126   │   1    │ 98.7% │ HEALTHY  │  │
│ │ 08/30 09:37  │  127  │  123   │   4    │ 97.0% │ HEALTHY  │  │
│ │ 08/30 09:22  │  127  │   99   │  28    │ 81.1% │ DEGRADED │  │
│ └──────────────┴───────┴────────┴────────┴───────┴──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## CLI Integration

```bash
# Docker (recommended)
docker compose -f qa_agent/dashboard/docker-compose.yml up        # start dashboard
docker compose -f qa_agent/dashboard/docker-compose.yml up -d     # start in background
docker compose -f qa_agent/dashboard/docker-compose.yml down      # stop

# Shortcut via qa-agent CLI
qa-agent dashboard                    # docker compose up + open browser
qa-agent dashboard --port 9090        # custom port
qa-agent dashboard --no-docker        # run without Docker (python directly)
qa-agent dashboard --stop             # docker compose down
```

---

## Build Phases

### Phase D1 — Docker + API Server + Data Layer (~2 days)
| # | Task |
|---|------|
| 1 | `Dockerfile` + `docker-compose.yml` + `requirements.txt` |
| 2 | `server.py` — FastAPI with JSON API endpoints |
| 3 | Data readers for health reports, eval scorecards, audit trail, triage reports |
| 4 | Aggregation logic for cost/token summaries |
| 5 | CLI command `qa-agent dashboard` (wraps docker compose) |
| 6 | Verify: `docker compose up` serves API at localhost:8080 |

### Phase D2 — Core Dashboard UI (~3 days)
| # | Task |
|---|------|
| 1 | `index.html` — layout with Tailwind CSS |
| 2 | Health gauge (radial SVG) |
| 3 | Domain health grid (14 cards) |
| 4 | Agent eval scorecard (4 cards with sparklines) |
| 5 | Run history table |

### Phase D3 — Charts & Interactivity (~2 days)
| # | Task |
|---|------|
| 1 | Cost/token stacked bar chart (Chart.js) |
| 2 | Triage activity timeline |
| 3 | Trend sparklines for health and eval scores |
| 4 | Auto-refresh (poll every 30s for live updates) |
| 5 | Drill-down views (click domain → test details) |

### Phase D4 — Polish & Comparison (~1 day)
| # | Task |
|---|------|
| 1 | Run comparison mode (select 2 runs, diff view) |
| 2 | Dark/light theme |
| 3 | Export (download scorecard as PDF or CSV) |
| 4 | Mobile-responsive layout |

---

## Data Refresh Strategy

The dashboard reads files from disk on each API request — no database, no cache, no stale data. When tests run or evals complete, their reports are written to disk and the dashboard picks them up on the next request.

For live monitoring during a test run:
- Dashboard polls `/api/health/latest` every 30 seconds
- When a new health report appears (different timestamp), the UI refreshes
- No WebSocket needed — simple polling is sufficient for update frequency

---

## Design Principles (Learned from Guild.ai)

1. **Visibility before optimization** — show the data first, let users decide what to act on
2. **Drill-down, not dump** — top-level KPIs with the ability to dig into details on demand
3. **Real-time without complexity** — file-based polling, not WebSocket infrastructure
4. **Export for stakeholders** — clean data that can be shared with non-technical teams
5. **Cost awareness** — token/cost tracking front and center, not hidden in logs

---

## Why NOT Three.js

Three.js excels at:
- 3D product visualizers
- Game-like interactive scenes
- Spatial data (maps, molecular structures)
- WebGL shader effects

Our dashboard needs:
- 2D line/bar/donut charts ← Chart.js does this in 60KB
- SVG gauges ← native browser SVG
- HTML tables ← `<table>` elements
- Card layouts ← CSS grid

Using Three.js would be like driving a semi truck to pick up groceries. Chart.js + Tailwind CSS delivers everything we need at 1/10th the complexity.

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Dashboard load time | < 1 second |
| Data freshness | Within 30 seconds of latest run |
| All data sources connected | Health, Eval, Audit, Triage |
| Usable without training | Self-explanatory layout |
| Works on localhost | No cloud infrastructure needed |
