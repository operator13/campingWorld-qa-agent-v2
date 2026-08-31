# Feature: Dashboard Eval Runner

> Run agent evaluations directly from the dashboard — per-agent or all at once. Scores, tokens, and cost update in real-time across all connected devices via WebSocket.

**Status:** PLANNED
**Priority:** High
**Depends on:** QA Command Center Dashboard, Agent Evaluation System, Event-Driven WebSocket Push

---

## The Problem

To run agent evals, you have to switch to the terminal and run `qa-agent eval --agent triage` or write a Python script. There's no way to trigger evals from the dashboard, watch progress, or see results update without leaving the browser.

---

## The Solution

Add "RUN" buttons to each agent eval card and an "EVAL ALL" button at the section level. Evals execute on the server, results push to all dashboards in real-time, and cumulative tokens/cost update immediately.

---

## UI Design

### Desktop Layout (Phase 1 — Build Now)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  AGENT EVALUATION                                          [▶ EVAL ALL]     │
│                                                                              │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐  ┌──│
│  │ TRIAGE      [▶ RUN]│  │ PLANNER     [▶ RUN]│  │ GENERATOR   [▶ RUN]│  │ H│
│  │                    │  │                    │  │                    │  │  │
│  │      85.7%         │  │     100.0%         │  │     100.0%         │  │  │
│  │      PASS          │  │      PASS          │  │      PASS          │  │  │
│  │                    │  │                    │  │                    │  │  │
│  │ TOKENS  271.1K     │  │ TOKENS  79.0K      │  │ TOKENS  23.9K      │  │  │
│  │ COST    $1.3099    │  │ COST    $0.9022    │  │ COST    $0.1770    │  │  │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘  └──│
└──────────────────────────────────────────────────────────────────────────────┘
```

### Running State

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  AGENT EVALUATION                                   [■ STOP] ● RUNNING      │
│                                                                              │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐  ┌──│
│  │ TRIAGE    ● EVAL   │  │ PLANNER   ● EVAL   │  │ GENERATOR  ◌ QUEUE│  │ H│
│  │                    │  │                    │  │                    │  │  │
│  │   ◌  Running...    │  │   ◌  Running...    │  │     100.0%         │  │  │
│  │                    │  │                    │  │      PASS          │  │  │
│  │                    │  │                    │  │                    │  │  │
│  │ TOKENS  271.1K     │  │ TOKENS  79.0K      │  │ TOKENS  23.9K      │  │  │
│  │ COST    $1.3099    │  │ COST    $0.9022    │  │ COST    $0.1770    │  │  │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘  └──│
└──────────────────────────────────────────────────────────────────────────────┘
```

### Complete State (card flashes, data updates)

```
┌────────────────────┐
│ TRIAGE      [▶ RUN]│  ← Button re-enabled
│                    │
│      87.2%         │  ← Score updated (was 85.7%)
│      PASS          │
│                    │
│ TOKENS  339.0K  ▲  │  ← Cumulative increased
│ COST    $1.64   ▲  │  ← Cost increased
└────────────────────┘
```

### States Per Card

| State | Indicator | UI Behavior |
|-------|-----------|-------------|
| IDLE | No indicator | RUN button enabled, shows latest score |
| RUNNING | Pulsing cyan dot + "Running..." | RUN button hidden, score replaced with spinner |
| COMPLETE | Green flash (2s) → back to IDLE | Score/tokens/cost update, RUN button re-enabled |
| ERROR | Red flash (3s) → back to IDLE | Error logged to console, RUN button re-enabled |

### Section-Level States

| State | EVAL ALL Button | Behavior |
|-------|----------------|----------|
| All idle | `[▶ EVAL ALL]` enabled | Click runs all 4 sequentially |
| Any running | `[■ STOP]` + `● RUNNING` | Stop cancels remaining evals |
| All complete | `[▶ EVAL ALL]` re-enabled | All cards show updated data |

---

## iPhone Layout (Phase 2 — Future Implementation)

> **Not built in Phase 1.** The eval runner buttons are desktop-only initially. iPhone users see the eval cards with scores/tokens but no RUN buttons. This section documents the future mobile design.

### Why Desktop-Only First

1. Evals take 2-5 minutes per agent — long-running operations aren't ideal on mobile
2. The eval cards are already compact on iPhone (2-column grid) — adding buttons would crowd the layout
3. iPhone users still see real-time score updates when someone triggers evals from desktop

### Future iPhone Design

```
┌─────────────────────────────┐
│ AGENT EVALUATION  [▶ ALL]   │
│                             │
│ ┌───────────┐ ┌───────────┐│
│ │TRIAGE [▶] │ │PLANNER[▶] ││
│ │  85.7%    │ │  100.0%   ││
│ │  PASS     │ │  PASS     ││
│ │ 271K $1.31│ │ 79K $0.90 ││
│ └───────────┘ └───────────┘│
│ ┌───────────┐ ┌───────────┐│
│ │GENRTR [▶] │ │HEALER[▶] ││
│ │  100.0%   │ │  94.0%    ││
│ │  PASS     │ │  PASS     ││
│ │ 24K $0.18 │ │ 122K $0.66││
│ └───────────┘ └───────────┘│
└─────────────────────────────┘
```

- Smaller `[▶]` buttons that don't disrupt the compact layout
- `[▶ ALL]` in section header
- Running state shows inline spinner instead of replacing the score
- Bottom sheet confirmation: "Run Triage eval? This takes ~2 min" before triggering

---

## Architecture

### API Endpoints (New)

```
POST /api/eval/run
  Body: {"agents": ["triage", "planner"], "all": false}
  Response: {"status": "started", "agents": ["triage", "planner"]}

POST /api/eval/run
  Body: {"all": true}
  Response: {"status": "started", "agents": ["triage", "planner", "generator", "healer"]}

GET /api/eval/run/status
  Response: {"state": "running", "current_agent": "planner", "completed": ["triage"], "queued": ["generator", "healer"]}

POST /api/eval/stop
  Response: {"status": "stopped", "completed": ["triage", "planner"], "cancelled": ["generator", "healer"]}
```

### WebSocket Events

```json
{"event": "eval:start", "agents": ["triage", "planner", "generator", "healer"]}
{"event": "eval:agent:start", "agent": "triage"}
{"event": "eval:agent:complete", "agent": "triage", "score": 0.8571, "passed": true, "tokens": 67990, "cost": 0.3305}
{"event": "eval:agent:error", "agent": "planner", "error": "API timeout"}
{"event": "eval:complete", "completed": 4, "failed": 0}
```

Each `eval:agent:complete` triggers the dashboard to refresh that specific card — score, tokens, cost all update instantly.

### Server-Side Execution

```python
# In server.py
_eval_process: asyncio.subprocess.Process | None = None
_eval_status: dict = {"state": "idle", "current_agent": None, "completed": [], "queued": []}

@app.post("/api/eval/run")
async def run_eval(body: dict = {}):
    if _eval_status["state"] == "running":
        return JSONResponse({"error": "Eval already running"}, status_code=409)

    agents = body.get("agents", [])
    run_all = body.get("all", False)
    if run_all:
        agents = ["triage", "planner", "generator", "healer"]

    asyncio.create_task(_execute_eval_run(agents))
    return JSONResponse({"status": "started", "agents": agents})

async def _execute_eval_run(agents: list[str]):
    """Run evals sequentially, broadcasting progress via WebSocket."""
    _eval_status["state"] = "running"
    _eval_status["queued"] = list(agents)
    _eval_status["completed"] = []

    await broadcast_to_dashboard(json.dumps({
        "event": "eval:start", "agents": agents
    }))

    for agent in agents:
        if _eval_status["state"] == "stopped":
            break

        _eval_status["current_agent"] = agent
        _eval_status["queued"].remove(agent)

        await broadcast_to_dashboard(json.dumps({
            "event": "eval:agent:start", "agent": agent
        }))

        try:
            # Spawn eval as subprocess to avoid blocking the event loop
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "qa_agent.eval.eval_runner",
                "--agent", agent,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
            )
            await proc.wait()

            # eval_runner already calls /api/eval/notify which broadcasts eval:updated
            _eval_status["completed"].append(agent)

            await broadcast_to_dashboard(json.dumps({
                "event": "eval:agent:complete", "agent": agent
            }))

        except Exception as e:
            await broadcast_to_dashboard(json.dumps({
                "event": "eval:agent:error", "agent": agent, "error": str(e)
            }))

    _eval_status["state"] = "idle"
    _eval_status["current_agent"] = None

    await broadcast_to_dashboard(json.dumps({
        "event": "eval:complete",
        "completed": len(_eval_status["completed"]),
        "failed": len(agents) - len(_eval_status["completed"]),
    }))
```

### Browser-Side Handling

```javascript
// On eval:agent:start — show running state on specific card
case 'eval:agent:start':
    setEvalCardState(data.agent, 'running');
    break;

// On eval:agent:complete — flash green, refresh card data
case 'eval:agent:complete':
    setEvalCardState(data.agent, 'complete');
    fetchEvalSummary();  // Refresh all cards (cumulative tokens update)
    break;

// On eval:complete — re-enable all buttons
case 'eval:complete':
    enableEvalButtons();
    break;
```

---

## Interactive Elements

### RUN Button (per card)

- Position: Top-right corner of each eval card
- Style: Small neon cyan border button, matches pill button aesthetic
- States:
  - Idle: `[▶ RUN]` — cyan border, clickable
  - Running: hidden (replaced by pulsing dot + "Running...")
  - Other agent running: disabled (grayed out) — only one eval at a time

### EVAL ALL Button (section header)

- Position: Right side of "AGENT EVALUATION" section title
- Style: Matches `RUN ALL` button in test runner
- Behavior: Runs all 4 agents sequentially (triage → planner → generator → healer)
- While running: becomes `[■ STOP]` with red border

### STOP Button

- Cancels remaining queued evals (current eval finishes, rest are skipped)
- Completed evals keep their results

---

## Cross-Device Sync

All eval events broadcast via WebSocket — same pattern as test runner:

| Event | All Devices See |
|-------|----------------|
| `eval:start` | All RUN buttons disable, section shows RUNNING |
| `eval:agent:start` | Specific card shows running spinner |
| `eval:agent:complete` | Card updates with new score/tokens/cost |
| `eval:complete` | All buttons re-enable |
| `eval:updated` | Cards refresh data (already implemented) |

iPhone users see cards updating in real-time even though they can't trigger evals (Phase 1).

---

## Desktop-Only Enforcement (Phase 1)

The RUN buttons are hidden on mobile via CSS media query:

```css
/* Hide eval run buttons on mobile */
@media (max-width: 768px) {
    .eval-run-btn,
    .eval-all-btn {
        display: none;
    }
}
```

iPhone users see the eval cards normally — scores, tokens, cost all visible and updating in real-time. They just can't trigger runs.

---

## Files to Modify

| File | Change |
|------|--------|
| `qa_agent/dashboard/server.py` | Add `POST /api/eval/run`, `GET /api/eval/run/status`, `POST /api/eval/stop`, background task |
| `qa_agent/dashboard/static/app.js` | RUN/EVAL ALL buttons, WebSocket handlers, card state management |
| `qa_agent/dashboard/static/styles.css` | Button styling, running/complete animations, mobile hide |
| `qa_agent/dashboard/static/index.html` | EVAL ALL button in section header |

---

## Build Phases

### Phase ER1 — Backend API (~0.5 day)

| # | Task |
|---|------|
| 1 | `POST /api/eval/run` — accept agent list or `all: true`, spawn background task |
| 2 | `GET /api/eval/run/status` — return current eval state (idle/running/agent/queue) |
| 3 | `POST /api/eval/stop` — cancel remaining queued evals |
| 4 | Background task: run evals sequentially, broadcast WebSocket events per agent |
| 5 | Subprocess execution so evals don't block the server event loop |

### Phase ER2 — Frontend Desktop UI (~0.5 day)

| # | Task |
|---|------|
| 1 | Add `[▶ RUN]` button to each eval card (desktop only) |
| 2 | Add `[▶ EVAL ALL]` button to section header |
| 3 | Card running state: pulsing dot, "Running..." text, button hidden |
| 4 | Card complete state: green flash animation, data refresh |
| 5 | STOP button: replaces EVAL ALL while running |
| 6 | CSS: hide buttons on mobile (`max-width: 768px`) |

### Phase ER3 — WebSocket Integration (~0.5 day)

| # | Task |
|---|------|
| 1 | Handle `eval:start` — disable all RUN buttons across devices |
| 2 | Handle `eval:agent:start` — show running state on specific card |
| 3 | Handle `eval:agent:complete` — flash card, refresh data |
| 4 | Handle `eval:agent:error` — show error, re-enable button |
| 5 | Handle `eval:complete` — re-enable all buttons |
| 6 | Sync state on WebSocket connect (catch mid-eval state) |

### Phase ER4 — iPhone Eval Runner (Future)

| # | Task |
|---|------|
| 1 | Unhide buttons on mobile with compact layout |
| 2 | Small `[▶]` icon buttons instead of `[▶ RUN]` text |
| 3 | Bottom sheet confirmation before triggering ("Run Triage? ~2 min") |
| 4 | Inline spinner instead of replacing score text |
| 5 | `[▶ ALL]` in section header (compact) |

---

## Safety

1. **Only one eval at a time** — second click returns 409 Conflict
2. **Sequential execution** — agents run one after another, not parallel (avoids LLM rate limits)
3. **STOP button** — cancels queued evals, lets current one finish
4. **No data loss** — completed evals keep their results even if STOP is pressed
5. **Subprocess isolation** — evals run as subprocesses so server stays responsive
6. **Cumulative tokens** — each completed eval adds to the running total (odometer)

---

## Success Criteria

1. Click `[▶ RUN]` on Triage card → eval runs, card shows spinner, completes with updated score
2. Click `[▶ EVAL ALL]` → all 4 agents run sequentially, each card updates as it completes
3. Tokens and cost increase after every eval (cumulative, never decrease)
4. All connected dashboards see updates in real-time (desktop + iPhone viewers)
5. STOP cancels remaining evals without losing completed results
6. RUN buttons hidden on iPhone (Phase 1)
7. No eval can run while another is in progress (409 conflict)
