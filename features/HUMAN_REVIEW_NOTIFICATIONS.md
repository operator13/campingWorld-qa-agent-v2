# Feature: Human Review Notifications & Failure Action Panel

> Surface unhealed test failures that need human attention directly on the dashboard — with context, confidence breakdown, and actionable response buttons.

**Status:** PLANNED
**Priority:** High
**Depends on:** QA Command Center Dashboard, Self-Healing Pipeline, Triage Agent

---

## The Problem

When a test failure can't be auto-healed (low confidence, navigation timeout, unknown classification), the only way a user discovers it is by manually checking the Run History table and noticing "1 unhealed." There's no proactive notification, no context about why it wasn't healed, and no way to respond from the dashboard.

The user has to:
1. Notice the unhealed count in Run History (easy to miss)
2. Switch to terminal to read the triage report JSON
3. Figure out what happened and decide what to do
4. Manually re-run, fix, or ignore the failure

This breaks the "everything from the browser" promise of the dashboard.

---

## The Solution

### 1. Notification Banner

A persistent alert bar at the top of the dashboard when unresolved failures exist:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ⚠ 1 failure needs human review                                            │
│  nav.spec.ts › "Find a Store link opens store locator panel"               │
│  Reason: navigation timeout (confidence: 0.20)                    [REVIEW] │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Behavior:**
- Appears after a self-heal run produces unhealed failures
- Stays visible until user clicks REVIEW or DISMISS
- Multiple failures stack: "3 failures need human review"
- Synced across devices — dismissing on desktop clears on iPhone
- Amber/yellow styling to distinguish from red errors

### 2. Failure Detail Panel

Clicking REVIEW (or clicking an unhealed row in Run History) opens a slide-out panel:

```
┌──────────────────────────────────────────────────┐
│  FAILURE REVIEW                           [CLOSE]│
│                                                  │
│  nav.spec.ts                                     │
│  "Find a Store link opens store locator panel"   │
│                                                  │
│  ── Classification ─────────────────────────     │
│  Class: test_flake                               │
│  Confidence: 0.20 (threshold: 0.75)              │
│                                                  │
│  ── Confidence Breakdown ────────────────────    │
│  C1 Error type:        0.10  (generic timeout)   │
│  C2 DOM evidence:      0.00  (no DOM snapshot)   │
│  C3 Historical match:  0.00  (first occurrence)  │
│  C4 Human calibration: 0.10  (neutral)           │
│  C5 Consistency:       0.00  (insufficient data) │
│                                                  │
│  ── Why Not Healed ─────────────────────────     │
│  Confidence 0.20 is below the auto-heal          │
│  threshold of 0.75. The failure is a navigation  │
│  timeout — the page didn't load within 30s.      │
│  The Healer cannot fix site availability issues.  │
│                                                  │
│  ── Error ──────────────────────────────────     │
│  Test timeout of 30000ms exceeded while          │
│  running "beforeEach" hook.                      │
│  > await nav.navigate();                         │
│                                                  │
│  ── Historical Context ─────────────────────     │
│  This test has passed 12/14 recent runs.         │
│  Last passed: 2026-08-31 22:00                   │
│  Pattern: intermittent (likely site availability)│
│                                                  │
│  ── Actions ────────────────────────────────     │
│  ┌──────────┐ ┌──────────┐ ┌─────────────────┐  │
│  │ ▶ RETRY  │ │ ✕ IGNORE │ │ ⚡ FORCE HEAL   │  │
│  └──────────┘ └──────────┘ └─────────────────┘  │
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │ 📝 ADD NOTE                              │    │
│  │ ┌──────────────────────────────────────┐ │    │
│  │ │ Site was slow, retry later           │ │    │
│  │ └──────────────────────────────────────┘ │    │
│  │                              [SAVE NOTE] │    │
│  └──────────────────────────────────────────┘    │
└──────────────────────────────────────────────────┘
```

### 3. Action Buttons

| Action | What It Does |
|--------|-------------|
| **RETRY** | Re-runs just this single test spec. If it passes, auto-dismisses the notification. |
| **IGNORE** | Marks as known issue. Adds to a suppression list so future identical failures don't trigger notifications. |
| **FORCE HEAL** | Sends the failure to the Healer regardless of confidence. The Healer attempts a fix and reports back. |
| **ADD NOTE** | Saves a human note to the triage report (e.g., "site was down", "known intermittent"). Recorded in memory for future triage context. |

### 4. Notification Badge

A small red counter badge on section headers when unresolved failures exist:

```
TEST RUNNER  ⚠ 1          RUN HISTORY  ⚠ 1
```

- Updates in real-time via WebSocket
- Cleared when all failures are resolved (retried, ignored, or healed)

---

## Full Dashboard Visual With Notifications

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  QA COMMAND CENTER                                              ● LIVE     │
├──────────────────────────────────────────────────────────────────────────────┤
│  ⚠ 1 failure needs human review — nav.spec.ts: "Find a Store link..."      │
│    Reason: navigation timeout (confidence: 0.20)          [REVIEW][DISMISS]│
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐    DOMAIN STATUS                                           │
│  │ SYSTEM      │    ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                    │
│  │ HEALTH      │    │ Cart │ │Chkout│ │SignIn│ │ Nav  │                    │
│  │   92.9%     │    │ 100% │ │ 100% │ │ 100% │ │92.9% │ ← degraded       │
│  │ DEGRADED    │    └──────┘ └──────┘ └──────┘ └──────┘                    │
│  └─────────────┘                                                            │
│                                                                              │
│  AGENT EVALUATION          [▶ EVAL ALL]                                     │
│  ...                                                                         │
│                                                                              │
│  TEST RUNNER ⚠1           RUN HISTORY ⚠1                                   │
│  ...                       2026-08-31 23:02  1 triaged  0 healed  SELF-HEAL │
│                            ↑ clicking this row opens the Failure Detail Panel│
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Architecture

### Data Flow

```
Test fails → Triage classifies → Confidence < 0.75 → NOT healed
                                                         │
                                                         ▼
                                              Server stores failure in
                                              _pending_reviews list
                                                         │
                                                         ▼
                                              WebSocket broadcasts
                                              {"event": "review:new"}
                                                         │
                                            ┌────────────┼────────────┐
                                            ▼            ▼            ▼
                                         Desktop      iPhone       Other
                                         Shows        Shows        devices
                                         banner       banner
                                                         │
                                                    User clicks REVIEW
                                                         │
                                                         ▼
                                              Failure Detail Panel opens
                                              User takes action:
                                              RETRY / IGNORE / FORCE HEAL / NOTE
                                                         │
                                                         ▼
                                              Server processes action
                                              WebSocket broadcasts
                                              {"event": "review:resolved"}
                                                         │
                                                         ▼
                                              Banner dismissed on all devices
```

### API Endpoints (New)

```
GET  /api/reviews/pending
  Response: [{"id": "...", "spec": "nav.spec.ts", "title": "...", "error": "...",
              "failure_class": "test_flake", "confidence": 0.20, "breakdown": {...},
              "timestamp": "...", "run_id": "..."}]

POST /api/reviews/{id}/retry
  Response: {"status": "retrying"}
  → Re-runs the single spec, broadcasts result

POST /api/reviews/{id}/ignore
  Body: {"reason": "known intermittent"}
  Response: {"status": "ignored"}
  → Adds to suppression list, dismisses notification

POST /api/reviews/{id}/force-heal
  Response: {"status": "healing"}
  → Sends to Healer regardless of confidence

POST /api/reviews/{id}/note
  Body: {"note": "Site was slow today"}
  Response: {"status": "noted"}
  → Saves to triage report + memory

POST /api/reviews/{id}/dismiss
  Response: {"status": "dismissed"}
  → Removes from pending without action
```

### WebSocket Events

```json
{"event": "review:new", "id": "...", "spec": "nav.spec.ts", "title": "...", "confidence": 0.20}
{"event": "review:resolved", "id": "...", "action": "retry_passed"}
{"event": "review:resolved", "id": "...", "action": "ignored"}
{"event": "review:resolved", "id": "...", "action": "force_healed"}
{"event": "review:dismissed", "id": "..."}
```

### Server-Side State

```python
_pending_reviews: list[dict] = []

# Populated by triage_runner after self-heal produces unhealed failures
# Each entry contains: id, spec_file, test_title, error, failure_class,
# confidence, confidence_breakdown, timestamp, run_id

# Persisted to health-reports/{timestamp}-triage.json (already exists)
# Loaded on server start from latest triage reports with unhealed failures
```

### Files to Modify

| File | Change |
|------|--------|
| `qa_agent/dashboard/server.py` | Add review endpoints, pending reviews state, WebSocket events |
| `qa_agent/dashboard/static/index.html` | Add notification banner container |
| `qa_agent/dashboard/static/app.js` | Banner rendering, failure detail panel, action handlers, WebSocket handlers |
| `qa_agent/dashboard/static/styles.css` | Banner styling, panel styling, badge styling, animations |
| `qa_agent/triage_runner.py` | Populate pending reviews after unhealed failures, notify dashboard |

### Files to Create

| File | Purpose |
|------|---------|
| `memory/IGNORED_FAILURES.md` | Suppression list for ignored failure patterns |

---

## Build Phases

### Phase HR1 — Notification Banner (~0.5 day)

| # | Task |
|---|------|
| 1 | Server: `_pending_reviews` list populated from triage runner unhealed results |
| 2 | Server: `GET /api/reviews/pending` endpoint |
| 3 | Server: Broadcast `review:new` WebSocket event after self-heal with unhealed |
| 4 | Server: Load pending reviews from recent triage reports on startup |
| 5 | Frontend: Notification banner HTML/CSS at top of dashboard |
| 6 | Frontend: Fetch pending reviews on page load, show banner if any |
| 7 | Frontend: WebSocket handler for `review:new` to show banner in real-time |
| 8 | Frontend: DISMISS button to hide banner (broadcasts to all devices) |

### Phase HR2 — Failure Detail Panel (~1 day)

| # | Task |
|---|------|
| 1 | Frontend: Slide-out panel HTML/CSS with glassmorphism styling |
| 2 | Panel sections: classification, confidence breakdown, error, historical context |
| 3 | Server: Include confidence breakdown in pending review data |
| 4 | Server: Include historical test data (pass/fail history from health reports) |
| 5 | Panel opens from: banner REVIEW button OR clicking unhealed Run History row |
| 6 | Responsive: full-screen modal on iPhone, side panel on desktop |

### Phase HR3 — Action Buttons (~0.5 day)

| # | Task |
|---|------|
| 1 | Server: `POST /api/reviews/{id}/retry` — re-run single spec |
| 2 | Server: `POST /api/reviews/{id}/ignore` — add to suppression list |
| 3 | Server: `POST /api/reviews/{id}/force-heal` — send to Healer with no confidence gate |
| 4 | Server: `POST /api/reviews/{id}/note` — save human note to triage report + memory |
| 5 | Frontend: Action buttons in panel with loading states |
| 6 | WebSocket: `review:resolved` event clears banner on all devices |
| 7 | RETRY: if test passes on retry, auto-resolve and dismiss |

### Phase HR4 — Notification Badge + Suppression (~0.5 day)

| # | Task |
|---|------|
| 1 | Frontend: Red badge counter on TEST RUNNER and RUN HISTORY section headers |
| 2 | Badge updates via WebSocket (new reviews increment, resolved decrement) |
| 3 | Create `memory/IGNORED_FAILURES.md` — suppression list |
| 4 | Triage runner checks suppression list before creating pending reviews |
| 5 | IGNORE action records pattern so identical future failures are auto-suppressed |

### Phase HR5 — Push Notifications (Future)

| # | Task |
|---|------|
| 1 | Webhook URL config (Slack, email, or custom endpoint) |
| 2 | Server sends webhook after unhealed failure if configured |
| 3 | Payload: spec file, test title, error summary, dashboard link |
| 4 | Rate limiting: max 1 notification per 15 minutes per spec |

---

## Cyberpunk Styling

### Notification Banner
- Amber/yellow gradient border (not red — red is for critical errors)
- Dark glass background matching dashboard cards
- Pulsing `⚠` icon
- Slide-down animation on appear, slide-up on dismiss

### Failure Detail Panel
- Slide-in from right (desktop) or bottom sheet (mobile)
- Same glassmorphism as agent eval tooltips
- Confidence breakdown as horizontal bar chart with cyan fills
- Error message in monospace code block with neon border
- Action buttons: cyan for RETRY, amber for IGNORE, magenta for FORCE HEAL

### Notification Badge
- Red circle with white count number
- Pulses once when count increases
- Positioned top-right of section title

---

## Integration with Existing Systems

### Triage Runner → Pending Reviews
After `run_triage_and_heal()` produces unhealed failures:
```python
for detail in summary["details"]:
    if not detail["healed"] and detail["failure_class"] != "app_defect":
        _add_pending_review(detail, summary["timestamp"])
        await broadcast_to_dashboard(json.dumps({
            "event": "review:new", ...
        }))
```

### Human Decision Memory
When user takes an action (IGNORE, NOTE, FORCE HEAL), record it in `memory/HUMAN_DECISIONS.md` so the Triage agent can learn from it:
```markdown
| Date | Spec | Test | Triage Class | Confidence | Human Action | Note |
|------|------|------|-------------|------------|-------------|------|
| 2026-08-31 | nav.spec.ts | Find a Store... | test_flake | 0.20 | ignore | Site was slow |
```

This feeds back into the C4 (human calibration) scoring in future triage runs.

### Force Heal Flow
When user clicks FORCE HEAL:
1. Build QAState with the failure data
2. Call `healer(state)` regardless of confidence
3. If fix produced → write file, re-run test
4. If test passes → resolve review, commit fix
5. If test fails → report back "Healer couldn't fix this"
6. Record the human override in HUMAN_DECISIONS.md

---

## Success Criteria

1. Unhealed failure triggers visible notification banner on all connected dashboards within 2 seconds
2. Clicking REVIEW opens detail panel with full context (error, confidence breakdown, history)
3. RETRY re-runs the test and auto-resolves if it passes
4. IGNORE suppresses future identical failures
5. FORCE HEAL bypasses confidence gate and attempts a fix
6. All actions sync across devices via WebSocket
7. Notification badge shows count on section headers
8. Panel is responsive — side panel on desktop, full-screen modal on iPhone
9. Human decisions recorded in memory for future Triage calibration
