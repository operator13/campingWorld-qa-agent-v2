# Feature: QA Agent Eval & Health Dashboard

> A real-time, interactive dashboard that visualizes agent eval scores, site health trends, triage activity, and cost metrics — giving instant visibility into the entire QA automation pipeline.

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

## Dashboard Sections

### 1. Site Health Overview (Hero Section)

**Large radial gauge** showing overall site health score with color coding:
- Green (≥95%): HEALTHY
- Yellow (≥80%): DEGRADED
- Red (<80%): CRITICAL

**Domain health grid** — 14 cards, one per domain:
- Each card shows: domain name, pass/fail count, health %, status badge
- Critical path domains (Cart, Checkout, Sign In) have a star indicator
- Cards pulse/glow red when CRITICAL
- Click a card → drill down to individual test results

**Trend sparkline** — last 10 runs inline, showing health trajectory

### 2. Agent Eval Scorecard (4-Panel Grid)

Four cards, one per agent (Triage, Planner, Generator, Healer):

Each card shows:
- Agent name + current score (large number)
- Pass/fail badge
- Mini bar chart showing score history (last 10 runs)
- Trend arrow (↑ improving, → stable, ↓ declining)
- Last run timestamp
- Click → drill down to recommendations and miss details

### 3. Cost & Token Tracking (from Audit Trail)

**Stacked bar chart** — tokens per agent per run:
- X-axis: run timestamps
- Y-axis: token count
- Stacked by agent (triage=blue, planner=green, generator=purple, healer=orange)

**Cost timeline** — line chart of estimated USD cost per run

**KPI strip:**
- Total tokens this session
- Total cost this session
- Average cost per run
- Most expensive agent

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
| **Server** | Python `http.server` or FastAPI | Serves static files + JSON API |
| **Data** | Read JSON files from disk | No database needed — files already exist |
| **Interactivity** | Alpine.js (3KB) | Minimal reactive framework for drill-downs |

### Why This Stack

1. **No build step** — `python -m http.server` serves it immediately
2. **Data already exists** — health reports, eval scorecards, audit JSON are all on disk
3. **Lightweight** — Chart.js is 60KB (vs Three.js 600KB+)
4. **Accessible** — real DOM elements, not canvas blobs
5. **Maintainable** — HTML/CSS that any developer can modify

---

## Architecture

```
qa_agent/dashboard/
├── server.py           # Python HTTP server + JSON API endpoints
├── static/
│   ├── index.html      # Main dashboard page
│   ├── styles.css      # Tailwind-based styles
│   ├── app.js          # Dashboard logic + Chart.js rendering
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
qa-agent dashboard                    # launch dashboard at http://localhost:8080
qa-agent dashboard --port 9090        # custom port
qa-agent dashboard --no-browser       # don't auto-open browser
```

---

## Build Phases

### Phase D1 — API Server + Data Layer (~2 days)
| # | Task |
|---|------|
| 1 | `server.py` — FastAPI or `http.server` with JSON endpoints |
| 2 | Data readers for health reports, eval scorecards, audit trail, triage reports |
| 3 | Aggregation logic for cost/token summaries |
| 4 | CLI command `qa-agent dashboard` |

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
