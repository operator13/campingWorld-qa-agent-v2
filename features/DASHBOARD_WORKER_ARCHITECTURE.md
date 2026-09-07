# Build Spec: Dashboard + Worker Two-Container Architecture

## Mission

The QA Command Center Dashboard currently runs as a single Docker container that can only display data — it cannot run evals, tests, or any operation requiring the full `qa_agent` package, API keys, or Claude Code CLI. The RUN buttons on Agent Evaluation cards (triage, planner, generator, healer), ECC Agent Eval cards (12 agents), EVAL ALL, and EVAL ECC AGENTS are non-functional in the Docker deployment because the container lacks the necessary environment.

This build spec splits the dashboard into two containers — a lightweight **Dashboard Server** for display/UI and an **Eval Worker** that has the full environment to execute evals and tests. This architecture works locally and deploys to cloud (GCP Cloud Run, AWS ECS Fargate) without modification.

**Status:** NOT STARTED
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
| 1 | Create `Dockerfile.worker` with full `qa_agent` package | `qa_agent/dashboard/Dockerfile.worker` | |
| 2 | Create worker FastAPI server with health check | `qa_agent/dashboard/worker.py` | |
| 3 | Add `POST /api/worker/eval/ecc/run` endpoint | `worker.py` | |
| 4 | Add `POST /api/worker/eval/run` endpoint (pipeline agents) | `worker.py` | |
| 5 | Add `POST /api/worker/test/run` endpoint | `worker.py` | |
| 6 | Add `POST /api/worker/test/stop` endpoint | `worker.py` | |
| 7 | Worker broadcasts progress to dashboard via HTTP POST | `worker.py` | |
| 8 | Update `docker-compose.yml` with two services + shared volume | `docker-compose.yml` | |
| 9 | Add `env_file` for worker with `ANTHROPIC_API_KEY` | `docker-compose.yml` | |
| 10 | Write tests for worker endpoints | `tests/test_worker.py` | |

### Phase 2: Dashboard Rewire (Week 1-2)

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Remove subprocess eval execution from `server.py` | `server.py` | |
| 2 | Add worker proxy: dashboard forwards RUN requests to worker | `server.py` | |
| 3 | Dashboard detects worker health (online/offline indicator) | `server.py`, `app.js` | |
| 4 | Disable RUN buttons when worker is offline | `app.js` | |
| 5 | Update ECC eval RUN to POST to worker | `app.js` | |
| 6 | Update pipeline eval RUN to POST to worker | `app.js` | |
| 7 | Update test runner to POST to worker | `app.js` | |
| 8 | Shared volume paths align between both containers | `docker-compose.yml` | |
| 9 | Write integration tests for dashboard → worker flow | `tests/test_dashboard_worker.py` | |

### Phase 3: Claude Code CLI in Worker (Week 2)

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Install Node.js 20 in worker Dockerfile | `Dockerfile.worker` | |
| 2 | Install Claude Code CLI in worker | `Dockerfile.worker` | |
| 3 | Install Playwright + Chromium in worker | `Dockerfile.worker` | |
| 4 | Verify ECC agent invocation works inside worker container | Manual test | |
| 5 | Verify Playwright test execution works inside worker container | Manual test | |
| 6 | End-to-end test: click RUN → progress bar → scores update | Manual test | |

### Phase 4: Cloud Deployment Readiness (Week 3)

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add health check endpoints to both containers | `server.py`, `worker.py` | |
| 2 | Add graceful shutdown handling to worker (finish current eval) | `worker.py` | |
| 3 | Document cloud deployment for GCP Cloud Run | `docs/DEPLOY_CLOUD_RUN.md` | |
| 4 | Document cloud deployment for AWS ECS Fargate | `docs/DEPLOY_ECS.md` | |
| 5 | Add GitHub Actions workflow for building and pushing images | `.github/workflows/docker-build.yml` | |
| 6 | Secret management documentation (Cloud Run secrets, AWS Secrets Manager) | Deployment docs | |

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

### Test Coverage Summary

| Phase | Unit | Integration | E2E | Total |
|-------|------|-------------|-----|-------|
| Phase 1: Worker Foundation | 15 | 3 | 0 | 18 |
| Phase 2: Dashboard Rewire | 2 | 6 | 5 | 13 |
| Phase 3: CLI in Worker | 0 | 8 | 2 | 10 |
| Phase 4: Cloud Readiness | 2 | 5 | 0 | 9* |
| **Total** | **19** | **22** | **7** | **50** |

*Phase 4 includes 2 CI tests run in GitHub Actions

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
