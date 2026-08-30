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

### Phase D3 — Live Streaming (~2 days)
| # | Task |
|---|------|
| 1 | Playwright custom WebSocket reporter (`ws-reporter.ts`) |
| 2 | FastAPI WebSocket hub (test events → browser broadcast) |
| 3 | Browser-side WebSocket client (live DOM updates on test events) |
| 4 | Live health gauge recalculation as each test completes |
| 5 | Triage event streaming (classify/heal events in real-time) |
| 6 | Fallback polling mode when WebSocket reporter not configured |

### Phase D4 — Charts & Interactivity (~2 days)
| # | Task |
|---|------|
| 1 | Cost/token stacked bar chart (Chart.js) |
| 2 | Triage activity timeline |
| 3 | Trend sparklines for health and eval scores |
| 4 | Drill-down views (click domain → test details) |

### Phase D5 — Visual Design: Cyberpunk-Futuristic UI (~2 days)
| # | Task |
|---|------|
| 1 | Core theme: deep dark background (#0a0a0f), neon accent system |
| 2 | Neon glow effects on cards, gauges, and charts |
| 3 | Animated scan lines + grid background overlay |
| 4 | Glassmorphism panels (frosted glass with backdrop-blur) |
| 5 | Typography: mono/tech font (JetBrains Mono, Orbitron for headings) |
| 6 | Micro-animations: card hover lifts, data pulse effects, typing counters |
| 7 | Sound design (optional): subtle tick on test pass, alert on critical |

### Phase D6 — Polish & Comparison (~1 day)
| # | Task |
|---|------|
| 1 | Run comparison mode (select 2 runs, diff view) |
| 2 | Export (download scorecard as PDF or CSV) |
| 3 | Mobile-responsive layout |

---

## Live Streaming Architecture

The dashboard provides **real-time streaming** — you see each test pass/fail as it happens, not after the run completes.

### How It Works

```
┌──────────────┐     WebSocket      ┌──────────────────┐
│  Playwright   │ ──────────────────→│  Dashboard Server │
│  Test Runner  │   test events      │  (FastAPI)        │
│               │   {test, status,   │                   │
│  npx pw test  │    duration, err}  │  Broadcasts to    │
│               │                    │  all connected    │
│               │                    │  browsers via WS  │
└──────────────┘                    └────────┬─────────┘
                                             │ WebSocket
                                             ▼
                                    ┌──────────────────┐
                                    │  Browser          │
                                    │  Dashboard UI     │
                                    │                   │
                                    │  Tests animate    │
                                    │  in real-time     │
                                    └──────────────────┘
```

### Three Event Streams

**Stream 1: Test Execution (live)**
- Playwright custom reporter sends events via WebSocket as each test completes
- Events: `test:start`, `test:pass`, `test:fail`, `test:skip`, `run:start`, `run:end`
- Dashboard updates domain cards and health gauge in real-time
- Failed tests flash red immediately

**Stream 2: Triage Activity (live)**
- When self-healing fires after a failed run, triage events stream to the dashboard
- Events: `triage:start`, `triage:classify`, `heal:start`, `heal:complete`, `rerun:start`, `rerun:result`
- Dashboard shows the triage timeline populating in real-time

**Stream 3: Eval Runs (live)**
- When `qa-agent eval run` executes, scenario results stream to the dashboard
- Events: `eval:start`, `eval:scenario`, `eval:complete`
- Agent accuracy cards update as each scenario scores

### Playwright Custom Reporter

A custom Playwright reporter sends WebSocket events to the dashboard server:

```typescript
// qa_agent/dashboard/ws-reporter.ts
import type { Reporter, TestCase, TestResult } from '@playwright/test/reporter';

class DashboardReporter implements Reporter {
  private ws: WebSocket;

  onBegin(config, suite) {
    this.ws = new WebSocket('ws://localhost:8080/ws/tests');
    this.ws.send(JSON.stringify({
      event: 'run:start',
      totalTests: suite.allTests().length,
      timestamp: Date.now(),
    }));
  }

  onTestEnd(test: TestCase, result: TestResult) {
    this.ws.send(JSON.stringify({
      event: result.status === 'passed' ? 'test:pass' : 'test:fail',
      title: test.title,
      suite: test.parent.title,
      file: test.location.file,
      duration: result.duration,
      error: result.errors?.[0]?.message || null,
      timestamp: Date.now(),
    }));
  }

  onEnd(result) {
    this.ws.send(JSON.stringify({
      event: 'run:end',
      status: result.status,
      duration: result.duration,
      timestamp: Date.now(),
    }));
    this.ws.close();
  }
}
export default DashboardReporter;
```

Register in `playwright.config.ts`:
```typescript
reporter: [
  ['./qa_agent/dashboard/ws-reporter.ts'],  // live streaming
  ['html', { ... }],
  ['json', { ... }],
  ['list'],
],
```

### Server-Side WebSocket Hub (FastAPI)

```python
# In server.py
from fastapi import WebSocket, WebSocketDisconnect

connected_browsers: list[WebSocket] = []

@app.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    """Browser connects here to receive live updates."""
    await websocket.accept()
    connected_browsers.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive
    except WebSocketDisconnect:
        connected_browsers.remove(websocket)

@app.websocket("/ws/tests")
async def test_events_ws(websocket: WebSocket):
    """Playwright reporter connects here to send test events."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # Broadcast to all connected browsers
            for browser in connected_browsers:
                await browser.send_text(data)
    except WebSocketDisconnect:
        pass
```

### Browser-Side Live Updates

```javascript
// In app.js
const ws = new WebSocket('ws://localhost:8080/ws/dashboard');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.event) {
    case 'run:start':
      showRunningBanner(data.totalTests);
      break;
    case 'test:pass':
      updateDomainCard(data.suite, 'pass');
      incrementPassCount();
      break;
    case 'test:fail':
      updateDomainCard(data.suite, 'fail');
      flashDomainRed(data.suite);
      addToFailureFeed(data);
      break;
    case 'run:end':
      hideRunningBanner();
      recalculateHealthScore();
      break;
    case 'triage:classify':
      addToTriageFeed(data);
      break;
    case 'heal:complete':
      showHealAnimation(data);
      break;
  }
};
```

### What You See in Real-Time

1. **Run starts** → banner appears: "Running 127 tests..."
2. **Each test completes** → domain card updates instantly:
   - Green flash on pass
   - Red flash + error toast on fail
   - Pass counter increments live
   - Health gauge recalculates after each test
3. **Run ends** → banner shows final score, health report saves
4. **If failures** → triage timeline starts populating:
   - "Triaging cart.spec.ts:28..." 
   - "→ locator_drift (0.82)"
   - "Healing CartPage.ts..."
   - "→ Fixed ✓"
5. **Re-run starts** → "Re-running 1 healed spec..."
6. **Re-run passes** → domain card flips from red to green

### Docker Compose Update for WebSocket

```yaml
services:
  dashboard:
    build:
      context: .
      dockerfile: qa_agent/dashboard/Dockerfile
    ports:
      - "8080:8080"    # HTTP + WebSocket on same port
    volumes:
      - ./health-reports:/data/health:ro
      - ./qa_agent/eval/reports:/data/eval:ro
      - ./memory/audit_runs:/data/audit:ro
      - ./test-results:/data/test-results:ro
    environment:
      - DATA_DIR=/data
    restart: unless-stopped
```

No additional ports needed — WebSocket upgrades happen on the same HTTP port (8080).

### Fallback: Polling Mode

If the WebSocket reporter isn't configured (e.g., running tests on a different machine), the dashboard falls back to polling `/api/health/latest` every 5 seconds. The UI works identically — just with a slight delay instead of instant updates.

---

## Visual Design: Cyberpunk-Futuristic Aesthetic

### Design Philosophy

The dashboard should feel like a **mission control center from 2077** — dark, glowing, data-dense, and unmistakably futuristic. Think Blade Runner ops room meets Tony Stark's HUD. Every element should feel alive with data.

### Color System

```
Background:     #0a0a0f (near-black with blue undertone)
Surface:        #12121a (elevated panels)
Card:           rgba(18, 18, 30, 0.8) + backdrop-blur (glassmorphism)
Border:         rgba(0, 255, 200, 0.15) (subtle cyan glow)

Primary Neon:   #00ffc8 (cyan-green — healthy, passing, success)
Warning Neon:   #ffb800 (amber — degraded, warning)
Danger Neon:    #ff003c (hot pink-red — critical, failing)
Info Neon:      #00a8ff (electric blue — neutral data)
Accent:         #b400ff (purple — healer/agent activity)

Text Primary:   #e0e0e0 (light gray)
Text Secondary: #7a7a8a (muted)
Text Glow:      text-shadow: 0 0 10px currentColor (neon text effect)
```

### Glow Effects

Every interactive element has a subtle neon glow:
```css
/* Card glow */
.card {
  background: rgba(18, 18, 30, 0.8);
  border: 1px solid rgba(0, 255, 200, 0.15);
  backdrop-filter: blur(12px);
  box-shadow: 0 0 20px rgba(0, 255, 200, 0.05),
              inset 0 0 20px rgba(0, 255, 200, 0.02);
}

/* Healthy domain card */
.card.healthy {
  border-color: rgba(0, 255, 200, 0.3);
  box-shadow: 0 0 30px rgba(0, 255, 200, 0.1);
}

/* Critical domain card — pulses */
.card.critical {
  border-color: rgba(255, 0, 60, 0.5);
  animation: pulse-red 2s ease-in-out infinite;
}

@keyframes pulse-red {
  0%, 100% { box-shadow: 0 0 20px rgba(255, 0, 60, 0.1); }
  50% { box-shadow: 0 0 40px rgba(255, 0, 60, 0.3); }
}
```

### Health Gauge (Radial, Animated)

The main health gauge is a glowing SVG ring:
- Cyan-green arc for healthy percentage
- Dark gap for missing percentage
- Animated on load: arc draws from 0% to current value over 1.5 seconds
- Neon glow filter on the arc
- Large percentage number in center with glow effect
- Status text below: "HEALTHY" / "DEGRADED" / "CRITICAL" with matching color

```
        ╭━━━━━━━━━━━╮
      ━━              ━━
    ━━    98.7%          ━━
   ━      HEALTHY          ━
    ━━                   ━━
      ━━              ━━
        ╰━━━━━━━━━━━╯
   (cyan-green arc with glow)
```

### Domain Cards (Glass Panels)

Each domain card is a frosted glass panel:
- Semi-transparent background with backdrop-blur
- Left edge: thin color stripe (green/yellow/red based on status)
- Domain name in tech font
- Score in large neon-colored numbers
- Mini progress bar below the score, glowing
- ★ badge for critical purchase path domains
- Hover: card lifts slightly (transform: translateY(-2px)), glow intensifies
- Live test: cards flash with a brief pulse animation on each test pass/fail

### Agent Score Cards

Four horizontal cards in a row, each showing:
- Agent icon (terminal/robot/wrench/shield glyph)
- Agent name in Orbitron font
- Score as a large glowing number
- Sparkline chart with gradient fill (neon to transparent)
- Trend indicator: animated up/down/stable arrow
- Subtle scan-line overlay animation

### Charts (Neon Data Viz)

**Token cost chart:**
- Dark background with grid lines in very faint cyan
- Bars with gradient fill (dark base → neon top)
- Hover: bar glows brighter, tooltip with glass effect
- Y-axis labels in mono font

**Triage timeline:**
- Vertical timeline with glowing dots
- Green dot = healed, amber = skipped, red = failed
- Connecting line pulses when new events arrive
- Each entry slides in with a brief animation

### Background Effects

```css
/* Subtle grid overlay */
.dashboard-bg {
  background-color: #0a0a0f;
  background-image:
    linear-gradient(rgba(0, 255, 200, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 255, 200, 0.03) 1px, transparent 1px);
  background-size: 40px 40px;
}

/* Optional: slow-moving scan line */
.scan-line {
  position: fixed;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(0, 255, 200, 0.1), transparent);
  animation: scan 8s linear infinite;
}

@keyframes scan {
  0% { top: 0; }
  100% { top: 100vh; }
}
```

### Typography

```css
/* Headings: Orbitron (futuristic, angular) */
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&display=swap');

/* Data/code: JetBrains Mono */
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');

h1, h2, .score-value { font-family: 'Orbitron', sans-serif; }
.data, .metric, code, .mono { font-family: 'JetBrains Mono', monospace; }
```

### Micro-Animations

| Element | Animation | Trigger |
|---------|-----------|---------|
| Health gauge arc | Draw from 0% → value | Page load |
| Score numbers | Count up from 0 | Page load |
| Domain cards | Slide in staggered | Page load |
| Test pass | Brief green pulse on domain card | WebSocket event |
| Test fail | Red flash + shake on domain card | WebSocket event |
| Triage event | Slide in from right | WebSocket event |
| Heal complete | Green checkmark particle effect | WebSocket event |
| Card hover | Lift + glow intensify | Mouse hover |
| Sparkline | Draw left to right | Scroll into view |

### Dashboard Header

```
┌─────────────────────────────────────────────────────────────────┐
│  ◆ QA COMMAND CENTER               ◉ LIVE    08/30/2026 10:04 │
│  ─────────────────────────────────────────────────────────────  │
│  campingworld.com                    127 tests │ 14 domains    │
└─────────────────────────────────────────────────────────────────┘
```

- "QA COMMAND CENTER" in Orbitron, with subtle glow
- "LIVE" indicator: green dot that pulses when WebSocket connected
- Timestamp in mono font
- Test/domain count as quick-reference stats

### Responsive Breakpoints

| Width | Layout |
|-------|--------|
| ≥1440px | Full 4-column grid, all panels visible |
| 1024-1439px | 2-column grid, charts stack below |
| 768-1023px | Single column, cards collapse to compact rows |
| <768px | Mobile: stacked cards, gauge at top, tap to expand |

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
