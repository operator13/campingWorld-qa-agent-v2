# Build Spec: Dashboard + Worker Two-Container Architecture

## Mission

The QA Command Center Dashboard currently runs as a single Docker container that can only display data — it cannot run evals, tests, or any operation requiring the full `qa_agent` package, API keys, or Claude Code CLI. The RUN buttons on Agent Evaluation cards (triage, planner, generator, healer), ECC Agent Eval cards (12 agents), EVAL ALL, and EVAL ECC AGENTS are non-functional in the Docker deployment because the container lacks the necessary environment.

This build spec splits the dashboard into two containers — a lightweight **Dashboard Server** for display/UI and an **Eval Worker** that has the full environment to execute evals and tests. This architecture works locally and deploys to cloud (GCP Cloud Run, AWS ECS Fargate) without modification.

**Status:** COMPLETE (Phase 1-4)
**Priority:** High
**Depends on:** QA Command Center Dashboard (existing), ECC Agent Evals (Phase 1-4)

---

## Current State (Broken)

| Component | Status | Problem |
|-----------|--------|---------|
| Dashboard RUN buttons (individual agent) | Non-functional in Docker | Subprocess needs `qa_agent` package, not installed |
| EVAL ALL button | Non-functional in Docker | Same — spawns subprocess that can't import `qa_agent` |
| EVAL ECC AGENTS button | Non-functional in Docker | Same |
| Test Runner (Run Selected, Run All) | Non-functional in Docker | Needs Playwright + Node.js |
| Health Reports | Functional (read-only) | Reads from volume mount |
| Score display | Functional (read-only) | Reads from volume mount |
| WebSocket progress from CLI | Functional | CLI broadcasts work when run on host |

---

## Architecture

```
┌─────────────────────────┐         ┌──────────────────────────┐
│  Container A:           │         │  Container B:            │
│  DASHBOARD SERVER       │         │  EVAL WORKER             │
│                         │  HTTP   │                          │
│  - FastAPI + WebSocket  │────────>│  - FastAPI server        │
│  - Static UI (JS/CSS)   │         │  - Full qa_agent package │
│  - Read-only data view  │<────────│  - Claude Code CLI       │
│  - No secrets           │   WS    │  - ANTHROPIC_API_KEY     │
│  - Port 8080            │         │  - Playwright + Node.js  │
│                         │         │  - Writes reports        │
│  Dockerfile.dashboard   │         │  - Port 8081 (internal)  │
│                         │         │                          │
│                         │         │  Dockerfile.worker       │
└────────────┬────────────┘         └────────────┬─────────────┘
             │                                   │
             └──────────────┬────────────────────┘
                            │
                   Shared Docker Volume
                   ┌────────────────────┐
                   │  /data/            │
                   │  ├── health-reports/│
                   │  ├── eval/reports/ │
                   │  ├── eval/ecc/    │
                   │  │   └── reports/  │
                   │  └── memory/       │
                   └────────────────────┘
```

### Communication Flow

1. **User clicks RUN** on any eval card or EVAL ALL / EVAL ECC AGENTS
2. **Dashboard** POSTs to Worker: `POST http://worker:8081/api/worker/eval/run`
3. **Worker** validates request, starts eval in background task
4. **Worker** broadcasts progress events to Dashboard: `POST http://dashboard:8080/api/eval/ecc/broadcast`
5. **Dashboard** fans out events to all WebSocket clients (browser tabs, phones)
6. **Worker** writes reports to shared volume (`/data/eval/ecc/reports/`)
7. **Dashboard** reads reports from shared volume to display scores

### What Each Container Needs

#### Container A: Dashboard Server (`Dockerfile.dashboard`)

```
FROM python:3.11-slim
- fastapi, uvicorn, websockets (existing requirements.txt)
- Static files (index.html, app.js, styles.css)
- server.py (read-only endpoints + WebSocket broadcast)
- NO secrets, NO qa_agent package, NO Claude CLI
- ~50MB image
```

#### Container B: Eval Worker (`Dockerfile.worker`)

```
FROM python:3.11-slim + Node.js 20
- Full qa_agent package (pip install -e .)
- Claude Code CLI (npm install -g @anthropic-ai/claude-code)
- Playwright + Chromium (for test runner)
- ANTHROPIC_API_KEY via env_file
- Small FastAPI server for /api/worker/* endpoints
- ~1.5GB image (Playwright + Chromium is heavy)
```

---

## Buttons That Must Work

### Agent Evaluation Section

| Button | Action | Worker Endpoint |
|--------|--------|----------------|
| Individual RUN (triage) | Eval single pipeline agent | `POST /api/worker/eval/run {agent: "triage"}` |
| Individual RUN (planner) | Eval single pipeline agent | `POST /api/worker/eval/run {agent: "planner"}` |
| Individual RUN (generator) | Eval single pipeline agent | `POST /api/worker/eval/run {agent: "generator"}` |
| Individual RUN (healer) | Eval single pipeline agent | `POST /api/worker/eval/run {agent: "healer"}` |
| EVAL ALL | Eval all 4 pipeline agents | `POST /api/worker/eval/run {all: true}` |

### ECC Development Agent Evals Section

| Button | Action | Worker Endpoint |
|--------|--------|----------------|
| Individual RUN (per agent) | Eval single ECC agent | `POST /api/worker/eval/ecc/run {agents: ["security-reviewer"]}` |
| EVAL ECC AGENTS | Eval all 12 ECC agents | `POST /api/worker/eval/ecc/run {all: true}` |

### Test Runner Section

| Button | Action | Worker Endpoint |
|--------|--------|----------------|
| RUN SELECTED | Run selected Playwright specs | `POST /api/worker/test/run {specs: [...]}` |
| RUN ALL | Run all Playwright specs | `POST /api/worker/test/run {all: true}` |
| STOP | Kill running test process | `POST /api/worker/test/stop` |

---

## Implementation Phases

### Phase 1: Worker Server Foundation (Week 1)

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create `Dockerfile.worker` with full `qa_agent` package | `qa_agent/dashboard/Dockerfile.worker` | DONE |
| 2 | Create worker FastAPI server with health check | `qa_agent/dashboard/worker.py` | DONE |
| 3 | Add `POST /api/worker/eval/ecc/run` endpoint | `worker.py` | DONE |
| 4 | Add `POST /api/worker/eval/run` endpoint (pipeline agents) | `worker.py` | DONE |
| 5 | Add `POST /api/worker/test/run` endpoint | `worker.py` | DONE |
| 6 | Add `POST /api/worker/test/stop` endpoint | `worker.py` | DONE |
| 7 | Worker broadcasts progress to dashboard via HTTP POST | `worker.py` | DONE |
| 8 | Update `docker-compose.yml` with two services + shared volume | `docker-compose.yml` | DONE |
| 9 | Add `env_file` for worker with `ANTHROPIC_API_KEY` | `docker-compose.yml` | DONE |
| 10 | Write tests for worker endpoints | `tests/test_worker.py` | DONE (22 tests) |

### Phase 2: Dashboard Rewire (Week 1-2)

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Remove subprocess eval execution from `server.py` | `server.py` | DONE |
| 2 | Add worker proxy: dashboard forwards RUN requests to worker | `server.py` | DONE |
| 3 | Dashboard detects worker health (online/offline indicator) | `server.py`, `app.js` | DONE |
| 4 | Disable RUN buttons when worker is offline | `app.js` | DONE |
| 5 | Update ECC eval RUN to POST to worker | `app.js` | DONE |
| 6 | Update pipeline eval RUN to POST to worker | `app.js` | DONE |
| 7 | Update test runner to POST to worker | `app.js` | DONE |
| 8 | Shared volume paths align between both containers | `docker-compose.yml` | DONE |
| 9 | Write integration tests for dashboard → worker flow | `tests/test_dashboard_worker.py` | DONE (13 tests) |

### Phase 3: Claude Code CLI in Worker (Week 2)

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Install Node.js 20 in worker Dockerfile | `Dockerfile.worker` | DONE |
| 2 | Install Claude Code CLI in worker | `Dockerfile.worker` | DONE |
| 3 | Install Playwright + Chromium in worker | `Dockerfile.worker` | DONE |
| 4 | Verify ECC agent invocation works inside worker container | Manual test | PENDING (requires `docker compose up`) |
| 5 | Verify Playwright test execution works inside worker container | Manual test | PENDING (requires `docker compose up`) |
| 6 | End-to-end test: click RUN → progress bar → scores update | Manual test | PENDING (requires `docker compose up`) |

### Phase 4: Cloud Deployment Readiness (Week 3)

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add health check endpoints to both containers | `server.py`, `worker.py` | DONE |
| 2 | Add graceful shutdown handling to worker (finish current eval) | `worker.py` | DONE |
| 3 | Document cloud deployment for GCP Cloud Run | `docs/DEPLOY_CLOUD_RUN.md` | DONE |
| 4 | Document cloud deployment for AWS ECS Fargate | `docs/DEPLOY_ECS.md` | DONE |
| 5 | Add GitHub Actions workflow for building and pushing images | `.github/workflows/docker-build.yml` | DONE |
| 6 | Secret management documentation (Cloud Run secrets, AWS Secrets Manager) | Deployment docs | DONE |

---

## Pre-Mortem: What Could Go Wrong

### P0: Critical — Would block the feature entirely

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| 1 | Claude Code CLI cannot be installed in Docker (binary not available for linux/arm64 or linux/amd64) | Medium | Blocks ECC evals entirely | Test CLI installation in Docker early (Phase 3, Task 2). Fallback: use the Anthropic API directly instead of Claude Code CLI for agent invocation |
| 2 | Worker container cannot reach Dashboard for WebSocket broadcast (Docker networking) | Low | No progress updates visible | Use Docker Compose service names (`http://dashboard:8080`). Test inter-container HTTP in Phase 1 |
| 3 | Shared volume permissions — worker writes reports but dashboard can't read them | Medium | Scores won't display | Set consistent UID/GID in both Dockerfiles. Test read/write in Phase 1 |
| 4 | `ANTHROPIC_API_KEY` not available to worker at runtime | Low | All evals fail silently | Validate API key on worker startup, log clear error. Health check reports key status |

### P1: High — Would degrade the experience

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| 5 | Worker image is too large (>2GB) with Playwright + Chromium + Claude CLI | High | Slow builds, high cloud costs | Multi-stage build. Separate test-runner from eval-worker if needed. Playwright only needed for test runner, not evals |
| 6 | Eval runs consume worker memory/CPU, blocking other requests | Medium | Dashboard health check fails, buttons unresponsive | Run evals in subprocess (not in-process). Worker health check responds even during eval. Add max concurrent evals limit |
| 7 | Worker crashes mid-eval, reports partially written | Medium | Corrupt data on dashboard | Worker writes reports atomically (write to temp, then rename). Dashboard validates report JSON before displaying |
| 8 | Dashboard RUN button clicked multiple times, queues duplicate evals | Medium | Wasted API spend | Worker rejects duplicate agent eval if already running. Dashboard disables button while running (existing behavior) |
| 9 | Cloud Run cold start — worker takes 30-60s to boot | High (Cloud Run) | User clicks RUN, nothing happens for a minute | Add startup progress indicator. Use min-instances=1 on Cloud Run (costs more). Or use ECS Fargate with always-on task |

### P2: Medium — Annoyances

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| 10 | Docker Compose `depends_on` doesn't wait for worker to be ready | High | Dashboard tries to reach worker before it's up | Add health check with retry in `depends_on: worker: condition: service_healthy` |
| 11 | Report timestamps differ between worker and dashboard containers | Low | Confusing display | Both containers use UTC (already the case) |
| 12 | Browser cache serves old JS after rebuild | High | Users see stale UI | Cache-busting query params on static assets (learned this session) |
| 13 | Worker logs not visible to user | Medium | Hard to debug failed evals | Stream worker stdout to dashboard log panel via WebSocket |

### P3: Low — Edge cases

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| 14 | Rate limiting from Anthropic API during parallel ECC eval (12 agents) | Low | Some agents fail with 429 | Existing sequential fallback in eval runner. Worker retries with backoff |
| 15 | Docker volume not synced in real-time on macOS (virtioFS lag) | Low | Brief delay before new scores appear | Dashboard polls with short interval after eval complete event |

---

## Success Criteria

- [ ] All 16 RUN buttons work from the dashboard (4 pipeline + 12 ECC agents)
- [ ] EVAL ALL triggers all 4 pipeline agents with progress bars
- [ ] EVAL ECC AGENTS triggers all 12 ECC agents with progress bars
- [ ] Test Runner RUN SELECTED and RUN ALL execute Playwright tests
- [ ] Progress bars update in real-time from actual eval/test execution
- [ ] Token usage and cost are recorded and displayed correctly
- [ ] Reports persist across container restarts (shared volume)
- [ ] Worker offline → RUN buttons disabled with clear indicator
- [ ] `docker compose up` starts both containers with no manual steps
- [ ] Same architecture deploys to GCP Cloud Run or AWS ECS Fargate

---

## Test Plan

### Phase 1 Tests: Worker Server Foundation (`tests/test_worker.py`)

| # | Test | Type | What It Validates |
|---|------|------|-------------------|
| 1 | `test_worker_health_check` | Unit | `GET /api/worker/health` returns 200 with status, API key presence, uptime |
| 2 | `test_worker_health_no_api_key` | Unit | Health check reports `api_key: false` when `ANTHROPIC_API_KEY` is missing |
| 3 | `test_ecc_eval_run_single_agent` | Unit | `POST /api/worker/eval/ecc/run {agents: ["security-reviewer"]}` returns 200, starts background task |
| 4 | `test_ecc_eval_run_all` | Unit | `POST /api/worker/eval/ecc/run {all: true}` returns 200, starts background task for all 12 agents |
| 5 | `test_ecc_eval_run_invalid_agent` | Unit | `POST /api/worker/eval/ecc/run {agents: ["fake-agent"]}` returns 400 |
| 6 | `test_ecc_eval_reject_duplicate` | Unit | Second POST while eval running returns 409 Conflict |
| 7 | `test_pipeline_eval_run_single` | Unit | `POST /api/worker/eval/run {agent: "triage"}` returns 200 |
| 8 | `test_pipeline_eval_run_all` | Unit | `POST /api/worker/eval/run {all: true}` returns 200 |
| 9 | `test_pipeline_eval_invalid_agent` | Unit | `POST /api/worker/eval/run {agent: "fake"}` returns 400 |
| 10 | `test_test_run_selected` | Unit | `POST /api/worker/test/run {specs: ["cart.spec.ts"]}` returns 200 |
| 11 | `test_test_run_all` | Unit | `POST /api/worker/test/run {all: true}` returns 200 |
| 12 | `test_test_stop` | Unit | `POST /api/worker/test/stop` returns 200, kills running process |
| 13 | `test_test_stop_nothing_running` | Unit | `POST /api/worker/test/stop` when idle returns 200 (no-op) |
| 14 | `test_worker_broadcasts_to_dashboard` | Unit | Worker POSTs progress events to `http://dashboard:8080/api/eval/ecc/broadcast` |
| 15 | `test_worker_broadcast_failure_resilient` | Unit | Worker continues eval even if dashboard broadcast POST fails (dashboard offline) |
| 16 | `test_worker_status_endpoint` | Unit | `GET /api/worker/status` returns current running agent, progress, queue |
| 17 | `test_docker_compose_both_services_start` | Integration | `docker compose up` starts both dashboard and worker, both respond to health checks |
| 18 | `test_shared_volume_writable_by_worker` | Integration | Worker can write a file to `/data/eval/ecc/reports/`, dashboard can read it |

### Phase 2 Tests: Dashboard Rewire (`tests/test_dashboard_worker.py`)

| # | Test | Type | What It Validates |
|---|------|------|-------------------|
| 1 | `test_dashboard_proxies_ecc_eval_to_worker` | Integration | Dashboard `POST /api/eval/ecc/run` forwards to worker `POST /api/worker/eval/ecc/run` |
| 2 | `test_dashboard_proxies_pipeline_eval_to_worker` | Integration | Dashboard `POST /api/eval/run` forwards to worker `POST /api/worker/eval/run` |
| 3 | `test_dashboard_proxies_test_run_to_worker` | Integration | Dashboard `POST /api/test/run` forwards to worker `POST /api/worker/test/run` |
| 4 | `test_dashboard_worker_offline_returns_503` | Integration | Dashboard returns 503 when worker is unreachable |
| 5 | `test_dashboard_health_includes_worker_status` | Integration | `GET /api/health` includes `worker_online: true/false` |
| 6 | `test_worker_progress_reaches_websocket_clients` | Integration | Worker broadcasts event → dashboard receives → WebSocket clients receive |
| 7 | `test_subprocess_removed_from_server` | Unit | `server.py` no longer contains `asyncio.create_subprocess_exec` for eval execution |
| 8 | `test_no_secrets_in_dashboard_container` | Integration | Dashboard container has no `ANTHROPIC_API_KEY` env var |
| 9 | `test_run_buttons_disabled_when_worker_offline` | E2E | Browser test: stop worker → refresh dashboard → RUN buttons are disabled/grayed |
| 10 | `test_run_buttons_enabled_when_worker_online` | E2E | Browser test: start worker → refresh dashboard → RUN buttons are clickable |
| 11 | `test_ecc_eval_full_flow` | E2E | Click RUN on security-reviewer → card shows Running... → progress updates → card restores with scores |
| 12 | `test_eval_all_full_flow` | E2E | Click EVAL ALL → all 4 pipeline cards show Running... → progress → restore |
| 13 | `test_eval_ecc_agents_full_flow` | E2E | Click EVAL ECC AGENTS → all 12 ECC cards show Running... → progress → restore |

### Phase 3 Tests: Claude Code CLI in Worker (`tests/test_worker_cli.py`)

| # | Test | Type | What It Validates |
|---|------|------|-------------------|
| 1 | `test_claude_cli_installed` | Integration | `docker exec worker claude --version` returns version string |
| 2 | `test_node_installed` | Integration | `docker exec worker node --version` returns v20.x |
| 3 | `test_playwright_installed` | Integration | `docker exec worker npx playwright --version` returns version |
| 4 | `test_ecc_agent_invocation_real` | Integration | Worker invokes security-reviewer on a sample file, gets non-empty output with findings |
| 5 | `test_ecc_agent_token_tracking` | Integration | After ECC eval, report contains `token_estimate > 0` |
| 6 | `test_playwright_test_execution` | Integration | Worker runs a single Playwright spec, produces results.json |
| 7 | `test_ecc_eval_progress_events` | E2E | Run ECC eval → verify `[1/N]`, `[2/N]` progress events broadcast to dashboard |
| 8 | `test_ecc_eval_report_written` | Integration | After eval, new report JSON exists in shared volume with valid scores |
| 9 | `test_pipeline_eval_real_execution` | Integration | Worker runs triage eval, produces scorecard with non-zero score |
| 10 | `test_cost_recorded_after_eval` | Integration | Report contains `token_estimate > 0`, dashboard card shows non-zero cost |

### Phase 4 Tests: Cloud Deployment Readiness (`tests/test_deployment.py`)

| # | Test | Type | What It Validates |
|---|------|------|-------------------|
| 1 | `test_dashboard_health_endpoint` | Unit | `GET /health` returns 200 with `{status: "ok", worker_online: bool}` |
| 2 | `test_worker_health_endpoint` | Unit | `GET /health` returns 200 with `{status: "ok", api_key: bool, cli: bool}` |
| 3 | `test_worker_graceful_shutdown` | Integration | Send SIGTERM to worker during eval → eval finishes → report saved → worker exits |
| 4 | `test_worker_graceful_shutdown_timeout` | Integration | Send SIGTERM → eval exceeds 60s grace period → worker force exits |
| 5 | `test_docker_build_dashboard` | CI | `docker build -f Dockerfile.dashboard .` succeeds, image < 100MB |
| 6 | `test_docker_build_worker` | CI | `docker build -f Dockerfile.worker .` succeeds, image < 2GB |
| 7 | `test_containers_restart_recovery` | Integration | Kill both containers → `docker compose up` → dashboard shows previous reports, RUN buttons work |
| 8 | `test_worker_startup_validates_api_key` | Integration | Worker without `ANTHROPIC_API_KEY` starts but health check reports `api_key: false`, eval endpoints return 503 |
| 9 | `test_github_actions_build_workflow` | CI | `.github/workflows/docker-build.yml` builds both images successfully |

### UI Tests: Dashboard RUN Buttons (`tests/e2e/test_dashboard_buttons.spec.ts`)

Playwright browser tests that verify every RUN button on the dashboard triggers real work and shows real progress. These run against the full two-container stack.

| # | Test | What It Validates |
|---|------|-------------------|
| 1 | `test_security_reviewer_run_button` | Click RUN on security-reviewer → card shows Running... → progress bar moves from 0% to 100% → card restores with updated scores and token count |
| 2 | `test_code_reviewer_run_button` | Same for code-reviewer |
| 3 | `test_silent_failure_hunter_run_button` | Same for silent-failure-hunter |
| 4 | `test_python_reviewer_run_button` | Same for python-reviewer |
| 5 | `test_typescript_reviewer_run_button` | Same for typescript-reviewer |
| 6 | `test_fastapi_reviewer_run_button` | Same for fastapi-reviewer |
| 7 | `test_performance_optimizer_run_button` | Same for performance-optimizer |
| 8 | `test_planner_ecc_run_button` | Same for planner-ecc (generative — checks quality score) |
| 9 | `test_tdd_guide_run_button` | Same for tdd-guide |
| 10 | `test_build_error_resolver_run_button` | Same for build-error-resolver |
| 11 | `test_e2e_runner_run_button` | Same for e2e-runner |
| 12 | `test_refactor_cleaner_run_button` | Same for refactor-cleaner |
| 13 | `test_triage_run_button` | Click RUN on triage → card shows Running... → progress → restores with accuracy score |
| 14 | `test_planner_run_button` | Same for planner |
| 15 | `test_generator_run_button` | Same for generator |
| 16 | `test_healer_run_button` | Same for healer |
| 17 | `test_eval_all_button` | Click EVAL ALL → all 4 pipeline cards show Running... → progress bars update → all restore with scores |
| 18 | `test_eval_ecc_agents_button` | Click EVAL ECC AGENTS → all 12 ECC cards show Running... → progress bars update → all restore with scores |
| 19 | `test_run_button_disabled_during_run` | Click RUN on one agent → verify RUN button is hidden → eval completes → button reappears |
| 20 | `test_stop_button_appears_during_eval_all` | Click EVAL ALL → STOP button appears, EVAL ALL hidden → click STOP → evals cancel |
| 21 | `test_progress_bar_increments` | Click RUN → verify progress text changes from "0%" to "[1/N]" to "[2/N]" etc. (not stuck at 0%) |
| 22 | `test_token_count_increases_after_run` | Record token count before RUN → click RUN → wait for complete → token count is higher |
| 23 | `test_cost_increases_after_run` | Record cost before RUN → click RUN → wait for complete → cost is higher |
| 24 | `test_multiple_sequential_runs` | Click RUN on agent A → wait for complete → click RUN on agent B → both produce reports |
| 25 | `test_score_updates_after_run` | Record recall/quality score → click RUN → score reflects new eval (may be same value but timestamp updates) |
| 26 | `test_eval_all_stop_button` | Click EVAL ALL → STOP button appears → click STOP → evals cancel → cards restore → EVAL ALL button reappears |
| 27 | `test_eval_ecc_agents_stop_button` | Click EVAL ECC AGENTS → STOP button appears → click STOP → evals cancel → cards restore → EVAL ECC AGENTS button reappears |

### UI Tests: Test Runner Buttons (`tests/e2e/test_test_runner_buttons.spec.ts`)

Playwright browser tests for the Test Runner section (Run Selected, Run All, Stop).

| # | Test | What It Validates |
|---|------|-------------------|
| 1 | `test_run_selected_single_domain` | Select Cart domain → click RUN SELECTED → runner status shows RUNNING → console output streams → status shows COMPLETE with pass/fail count |
| 2 | `test_run_selected_multiple_domains` | Select Cart + Search → click RUN SELECTED → both domains run → progress shows per-domain |
| 3 | `test_run_selected_none_selected` | No domains selected → click RUN SELECTED → nothing happens or shows warning |
| 4 | `test_run_all_button` | Click RUN ALL → all domains run → runner status RUNNING → console output streams → COMPLETE with total pass/fail |
| 5 | `test_stop_button_during_run` | Click RUN ALL → STOP button appears, RUN buttons hidden → click STOP → tests cancel → status shows STOPPED |
| 6 | `test_stop_button_hidden_when_idle` | Verify STOP button is hidden when no tests running |
| 7 | `test_run_buttons_disabled_during_run` | Click RUN ALL → RUN SELECTED and RUN ALL buttons hidden → STOP visible → tests complete → buttons restore |
| 8 | `test_console_output_streams` | Click RUN ALL → console output section appears → log lines stream in real-time (not all at once) |
| 9 | `test_domain_progress_bars` | Click RUN ALL → each domain tile shows progress (running/pass/fail indicator) |
| 10 | `test_health_updates_after_test_run` | Run tests → complete → System Health gauge and Domain Status cards reflect new results |
| 11 | `test_run_history_row_added` | Run tests → complete → new row appears in Run History table with timestamp, tests, passed, failed, health % |
| 12 | `test_worker_options_respected` | Set Workers to 1, Retries to 1, Self-Heal ON → click RUN ALL → verify test command uses those options |
| 13 | `test_clear_button` | Click CLEAR → console output cleared, domain progress reset |

### UI Tests: CLI-Triggered Runs Display on Dashboard (`tests/e2e/test_cli_dashboard_sync.spec.ts`)

Verify that evals triggered from the CLI on the host show live progress on the dashboard, matching the existing broadcast mechanism.

| # | Test | What It Validates |
|---|------|-------------------|
| 1 | `test_cli_ecc_eval_shows_running_state` | Start `qa-agent eval --ecc --agent security-reviewer` from CLI → dashboard card shows Running... within 5s |
| 2 | `test_cli_ecc_eval_progress_bar_updates` | CLI eval running → dashboard progress bar updates with [1/N], [2/N] from broadcast events |
| 3 | `test_cli_ecc_eval_card_restores_on_complete` | CLI eval finishes → dashboard card restores with updated scores |
| 4 | `test_cli_pipeline_eval_shows_on_dashboard` | Start `qa-agent eval run --agent triage` → dashboard triage card shows Running... |
| 5 | `test_cli_eval_all_shows_all_cards_running` | Start `qa-agent eval run --agent all` → all 4 pipeline cards show Running... |
| 6 | `test_cli_and_dashboard_run_conflict` | CLI starts eval → user clicks RUN on dashboard → dashboard shows 409 or queues (doesn't duplicate) |
| 7 | `test_cli_eval_tokens_reflected_on_dashboard` | CLI eval completes → refresh dashboard → token count and cost updated on card |
| 8 | `test_cli_run_while_dashboard_closed` | Run CLI eval with dashboard stopped → start dashboard → scores reflect the completed eval |
| 9 | `test_mobile_receives_cli_progress` | CLI eval running → open dashboard on mobile viewport (375px) → progress bar visible and updating |
| 10 | `test_multiple_browser_tabs_receive_progress` | Open 2 dashboard tabs → run CLI eval → both tabs show Running... and progress simultaneously |

### Test Coverage Summary

| Phase | Unit | Integration | E2E/UI | Total |
|-------|------|-------------|--------|-------|
| Phase 1: Worker Foundation | 15 | 3 | 0 | 18 |
| Phase 2: Dashboard Rewire | 2 | 6 | 5 | 13 |
| Phase 3: CLI in Worker | 0 | 8 | 2 | 10 |
| Phase 4: Cloud Readiness | 2 | 5 | 0 | 9* |
| UI: Eval RUN Buttons | 0 | 0 | 27 | 27 |
| UI: Test Runner Buttons | 0 | 0 | 13 | 13 |
| UI: CLI → Dashboard Sync | 0 | 0 | 10 | 10 |
| **Total** | **19** | **22** | **57** | **100** |

*Phase 4 includes 2 CI tests run in GitHub Actions

### All Buttons Under Test

| Button | Location | Test File | Test Count |
|--------|----------|-----------|-----------|
| RUN (triage) | Agent Evaluation | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (planner) | Agent Evaluation | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (generator) | Agent Evaluation | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (healer) | Agent Evaluation | `test_dashboard_buttons.spec.ts` | 1 |
| EVAL ALL | Agent Evaluation | `test_dashboard_buttons.spec.ts` | 1 |
| STOP (eval) | Agent Evaluation | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (security-reviewer) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (code-reviewer) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (silent-failure-hunter) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (python-reviewer) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (typescript-reviewer) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (fastapi-reviewer) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (performance-optimizer) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (planner-ecc) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (tdd-guide) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (build-error-resolver) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (e2e-runner) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| RUN (refactor-cleaner) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| EVAL ECC AGENTS | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| STOP (ECC eval) | ECC Evals | `test_dashboard_buttons.spec.ts` | 1 |
| RUN SELECTED | Test Runner | `test_test_runner_buttons.spec.ts` | 3 |
| RUN ALL | Test Runner | `test_test_runner_buttons.spec.ts` | 1 |
| STOP (test runner) | Test Runner | `test_test_runner_buttons.spec.ts` | 2 |
| CLEAR | Test Runner | `test_test_runner_buttons.spec.ts` | 1 |
| **Total: 24 buttons** | | | **27 tests** |

### Test Files Summary

| File | Tests | Purpose |
|------|-------|---------|
| `tests/test_worker.py` | 18 | Worker endpoint unit + integration tests |
| `tests/test_dashboard_worker.py` | 13 | Dashboard ↔ worker integration + E2E |
| `tests/test_worker_cli.py` | 10 | CLI/Playwright installation, real eval execution |
| `tests/test_deployment.py` | 9 | Health checks, graceful shutdown, CI builds |
| `tests/e2e/test_dashboard_buttons.spec.ts` | 27 | Every eval RUN/STOP button + progress + scores |
| `tests/e2e/test_test_runner_buttons.spec.ts` | 13 | Test runner RUN/STOP/CLEAR + console + history |
| `tests/e2e/test_cli_dashboard_sync.spec.ts` | 10 | CLI evals show live on dashboard |

---

## Files Summary

| Action | File | Purpose |
|--------|------|---------|
| **Create** | `qa_agent/dashboard/Dockerfile.worker` | Worker container with full environment |
| **Create** | `qa_agent/dashboard/worker.py` | Worker FastAPI server |
| **Create** | `qa_agent/dashboard/requirements-worker.txt` | Worker Python dependencies |
| **Create** | `tests/test_worker.py` | Worker endpoint tests |
| **Create** | `tests/test_dashboard_worker.py` | Integration tests |
| **Create** | `docs/DEPLOY_CLOUD_RUN.md` | Cloud Run deployment guide |
| **Create** | `docs/DEPLOY_ECS.md` | ECS Fargate deployment guide |
| **Create** | `.github/workflows/docker-build.yml` | CI for building/pushing images |
| **Modify** | `qa_agent/dashboard/docker-compose.yml` | Two services + shared volume |
| **Modify** | `qa_agent/dashboard/server.py` | Remove subprocess, add worker proxy |
| **Modify** | `qa_agent/dashboard/static/app.js` | Worker health indicator, button disable |
| **Modify** | `qa_agent/dashboard/Dockerfile` | Rename to `Dockerfile.dashboard` |
