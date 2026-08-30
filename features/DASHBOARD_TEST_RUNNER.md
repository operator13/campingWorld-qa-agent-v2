# Feature: Dashboard Test Runner Card

> Run tests directly from the dashboard — select individual domains, multiple domains, or run all. Watch results stream in real-time via WebSocket.

**Status:** PLANNED
**Priority:** High
**Depends on:** QA Command Center Dashboard, WebSocket streaming

---

## The Problem

To run tests, you have to switch to the terminal and type `./run-tests.sh` or `./run-tests.sh cart.spec.ts`. There's no way to trigger tests from the dashboard, select which domains to test, or watch results without leaving the browser.

## The Solution

A new dashboard card with domain checkboxes and a "RUN" button. Click run, tests execute on the server, results stream to the dashboard in real-time, and the health score updates live.

---

## UI Design

```
┌─────────────────────────────────────────────────────┐
│  TEST RUNNER                              ◉ IDLE    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │  ☑ Select All                               │    │
│  │  ─────────────────────────────────────────   │    │
│  │  ★ ☑ Cart          ☑ Homepage    ☑ Search   │    │
│  │  ★ ☑ Checkout      ☑ Nav        ☑ Product   │    │
│  │  ★ ☑ Sign In       ☑ Register   ☑ Footer    │    │
│  │    ☑ Store Locator  ☑ Good Sam  ☑ RV Parts  │    │
│  │    ☑ RVs For Sale   ☑ RV Detail              │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  Workers: [1] [2] [●3] [4]    Retries: [●0] [1]    │
│                                                     │
│  ┌──────────────────────┐  ┌──────────────────┐     │
│  │    ▶ RUN SELECTED     │  │   ▶ RUN ALL       │     │
│  └──────────────────────┘  └──────────────────┘     │
│                                                     │
│  ── Progress ───────────────────────────────────    │
│  ▰▰▰▰▰▰▰▰▰▰▰▰▱▱▱▱▱▱▱▱  64/127  (50.4%)         │
│                                                     │
│  ✓ Cart 8/8  ✓ Checkout 4/4  ◌ Search 3/9...       │
│  ✗ Nav 12/14 (2 failed)                             │
└─────────────────────────────────────────────────────┘
```

### States

| State | Indicator | UI Behavior |
|-------|-----------|-------------|
| IDLE | Gray dot | Checkboxes enabled, buttons enabled |
| RUNNING | Green pulsing dot | Checkboxes disabled, "RUN" becomes "STOP", progress bar animates |
| HEALING | Purple pulsing dot | "Self-healing in progress..." shown below progress |
| COMPLETE | Green dot (3s then back to IDLE) | Results summary, health score refreshes |
| ERROR | Red dot | Error message shown, buttons re-enabled |

### Interactive Elements

**Domain checkboxes:**
- 14 checkboxes, one per domain
- "Select All" toggle at top
- Critical domains (Cart, Checkout, Sign In) have ★ prefix
- Disabled while tests are running

**Worker count selector:**
- Buttons: 1, 2, 3 (default), 4
- Highlighted button = selected
- Tooltip: "More workers = faster but may cause flaky failures"

**Retry selector:**
- Buttons: 0 (default), 1
- 0 = no retries, 1 = retry failed tests once

**Run buttons:**
- "RUN SELECTED" — runs only checked domains
- "RUN ALL" — checks all and runs (shortcut)
- Both disable while running, show "STOP" to cancel

**Progress section (visible only during run):**
- Progress bar with percentage
- Per-domain mini-status: ✓ (all passed), ✗ (has failures), ◌ (running), ○ (pending)
- Live test count: "64/127 (50.4%)"

---

## Architecture

### API Endpoints (new)

```
POST /api/tests/run
  Body: {"specs": ["cart.spec.ts", "search.spec.ts"], "workers": 3, "retries": 0}
  Response: {"run_id": "run-123", "status": "started"}

GET /api/tests/status
  Response: {"status": "running|idle|healing", "run_id": "run-123", "progress": 64, "total": 127}

POST /api/tests/stop
  Response: {"status": "stopped"}
```

### Server-Side Execution

When `POST /api/tests/run` is called:

1. Server spawns `npx playwright test [spec files] --workers=N --retries=N --reporter=json` as a subprocess
2. Reads stdout line by line, parsing JSON events
3. Broadcasts each test result via WebSocket to `/ws/dashboard`
4. When complete, runs health scorer on results
5. If failures and self-healing enabled, triggers triage runner
6. Broadcasts final health update

```python
# In server.py
import asyncio
import subprocess

active_process: subprocess.Popen | None = None

@app.post("/api/tests/run")
async def run_tests(body: dict):
    global active_process
    if active_process and active_process.poll() is None:
        return JSONResponse({"error": "Tests already running"}, status_code=409)
    
    specs = body.get("specs", [])
    workers = body.get("workers", 3)
    retries = body.get("retries", 0)
    
    # Launch in background task
    asyncio.create_task(_run_tests_async(specs, workers, retries))
    return JSONResponse({"status": "started", "run_id": f"run-{int(time.time())}"})
```

### WebSocket Events (test runner → browser)

```json
{"event": "run:start", "total": 127, "specs": ["cart.spec.ts", ...]}
{"event": "test:pass", "suite": "Cart", "title": "cart loads", "duration": 5200}
{"event": "test:fail", "suite": "Nav", "title": "sign in visible", "error": "TimeoutError..."}
{"event": "suite:done", "suite": "Cart", "passed": 8, "failed": 0, "total": 8}
{"event": "run:end", "passed": 125, "failed": 2, "total": 127, "duration": 300000}
{"event": "heal:start", "failures": 2}
{"event": "heal:done", "healed": 1, "skipped": 1}
{"event": "health:update", "score": 98.7, "status": "HEALTHY"}
```

### Browser-Side Handling

```javascript
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  switch (data.event) {
    case 'run:start':
      showProgressBar(data.total);
      disableControls();
      break;
    case 'test:pass':
      incrementProgress();
      updateDomainMiniStatus(data.suite, 'pass');
      flashDomainCardGreen(data.suite);
      break;
    case 'test:fail':
      incrementProgress();
      updateDomainMiniStatus(data.suite, 'fail');
      flashDomainCardRed(data.suite);
      break;
    case 'suite:done':
      markSuiteComplete(data.suite, data.passed, data.failed);
      break;
    case 'run:end':
      showRunComplete(data);
      enableControls();
      refreshHealthData();
      break;
    case 'heal:start':
      showHealingStatus(data.failures);
      break;
    case 'health:update':
      updateHealthGauge(data.score, data.status);
      break;
  }
};
```

---

## Spec-to-Domain Mapping

The checkboxes map to spec files:

| Checkbox Label | Spec File | Tests |
|---------------|-----------|-------|
| ★ Cart | cart.spec.ts | 8 |
| ★ Checkout | checkout.spec.ts | 4 |
| ★ Sign In | sign-in.spec.ts | 10 |
| Homepage | homepage.spec.ts | 13 |
| Nav | nav.spec.ts | 14 |
| Search | search.spec.ts | 9 |
| Product | product.spec.ts | 9 |
| Register | register.spec.ts | 6 |
| Store Locator | store-locator.spec.ts | 10 |
| Good Sam | good-sam.spec.ts | 6 |
| RV Parts | rv-parts.spec.ts | 5 |
| RVs For Sale | rvs-for-sale.spec.ts | 10 |
| RV Detail | rvs-for-sale-detail.spec.ts | 10 |
| Footer | footer.spec.ts | 13 |

---

## Safety

1. **Only one run at a time** — second click returns 409 Conflict
2. **Stop button** — kills the subprocess via SIGTERM
3. **Auto-commit** — health report auto-committed after run completes
4. **Self-healing optional** — only triggers if failures detected and triage enabled
5. **No destructive actions** — running tests doesn't modify source code (only healer does, with backup)

---

## Build Phases

### Phase TR1 — Backend API (~1 day)
| # | Task |
|---|------|
| 1 | `POST /api/tests/run` — spawn Playwright subprocess |
| 2 | `GET /api/tests/status` — return current run status |
| 3 | `POST /api/tests/stop` — kill running subprocess |
| 4 | Background task that reads subprocess output and broadcasts via WebSocket |
| 5 | Health score computation after run completes |

### Phase TR2 — Frontend Card (~1 day)
| # | Task |
|---|------|
| 1 | Test runner card HTML with checkboxes, worker/retry selectors, run buttons |
| 2 | CSS styling matching cyberpunk theme |
| 3 | Progress bar with live percentage |
| 4 | Per-domain mini-status indicators |
| 5 | WebSocket handlers for all test runner events |
| 6 | State management (idle → running → healing → complete) |

### Phase TR3 — Integration (~0.5 day)
| # | Task |
|---|------|
| 1 | Auto-commit health report after run |
| 2 | Trigger self-healing on failures |
| 3 | Refresh all dashboard data after run completes |
| 4 | Error handling (subprocess crash, timeout) |

---

## Cyberpunk Styling

- Card matches existing glassmorphism theme
- Checkboxes: custom cyan-glow checkboxes (not browser default)
- Run button: neon cyan border, fills with glow on hover, pulses while running
- Progress bar: gradient fill from dark to neon cyan, glow effect
- Worker/retry selectors: pill buttons with active glow state
- Domain mini-status: ✓ green glow, ✗ red glow, ◌ cyan pulse (running)
- Stop button: neon red with danger glow
