import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Directory resolution
# ---------------------------------------------------------------------------

DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).resolve().parent.parent.parent))
HEALTH_DIR = Path(DATA_DIR) / "health-reports"
EVAL_DIR = Path(DATA_DIR) / "qa_agent" / "eval" / "reports"
ECC_EVAL_DIR = Path(DATA_DIR) / "qa_agent" / "eval" / "ecc" / "reports"
AUDIT_DIR = Path(DATA_DIR) / "memory" / "audit_runs"

STATIC_DIR = Path(__file__).resolve().parent / "static"

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="QA Command Center")

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

DASHBOARD_API_TOKEN = os.environ.get("DASHBOARD_API_TOKEN", "")


async def require_auth(x_api_token: str | None = Header(None)):
    """Require a valid API token for mutating endpoints.

    If DASHBOARD_API_TOKEN is not set, auth is disabled (local-only mode).
    """
    if DASHBOARD_API_TOKEN and x_api_token != DASHBOARD_API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# Security constants
# ---------------------------------------------------------------------------

SAFE_RUN_ID = re.compile(r"^[\w\-]+$")
ALLOWED_EVAL_AGENTS = {"triage", "planner", "generator", "healer"}
ALLOWED_SPECS = {
    "cart.spec.ts", "checkout.spec.ts", "footer.spec.ts", "good-sam.spec.ts",
    "homepage.spec.ts", "nav.spec.ts", "product.spec.ts", "register.spec.ts",
    "rv-parts.spec.ts", "rvs-for-sale-detail.spec.ts", "rvs-for-sale.spec.ts",
    "search.spec.ts", "sign-in.spec.ts", "store-locator.spec.ts",
}
ALLOWED_WS_EVENTS = {
    "runner:log", "runner:start", "runner:end", "runner:clear",
    "runner:healing", "runner:healed",
    "eval:start", "eval:complete", "eval:log",
    "eval:agent:start", "eval:agent:complete", "eval:agent:error",
    "ecc_eval:start", "ecc_eval:complete", "ecc_eval:log",
    "ecc_eval:agent:start", "ecc_eval:agent:complete", "ecc_eval:agent:error",
    "health:updated",
}
MAX_WORKERS = 10
MAX_RETRIES = 3

if not DASHBOARD_API_TOKEN:
    import logging as _logging
    _logging.getLogger("qa_dashboard").warning(
        "DASHBOARD_API_TOKEN is not set — all POST endpoints are unauthenticated. "
        "Set DASHBOARD_API_TOKEN in .env to enable auth."
    )

# Mount static files (CSS, JS, etc.)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---------------------------------------------------------------------------
# WebSocket connection managers
# ---------------------------------------------------------------------------

# Browser clients connected to /ws/dashboard
dashboard_connections: list[WebSocket] = []

# Test runner state
_test_process: asyncio.subprocess.Process | None = None
_test_run_status: dict = {"state": "idle", "run_id": None, "started_at": None}
_last_run_log: list[str] = []  # Stores log lines from the last completed run
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TESTS_DIR = PROJECT_ROOT / "tests_generated"
TEST_RESULTS_TMP = PROJECT_ROOT / "test-results-tmp"
TEST_RESULTS_DIR = PROJECT_ROOT / "test-results"


async def broadcast_to_dashboard(message: str) -> None:
    """Send a message to every connected dashboard browser."""
    dead: list[WebSocket] = []
    for ws in dashboard_connections:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        dashboard_connections.remove(ws)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _sorted_json_files(directory: Path) -> list[Path]:
    """Return JSON files in *directory* sorted alphabetically (= chronologically)."""
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Static page
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return FileResponse(str(index_file))  # FastAPI will 404 naturally if missing


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health/latest")
async def health_latest() -> JSONResponse:
    files = _sorted_json_files(HEALTH_DIR)
    if not files:
        return JSONResponse(content={})

    # Find the latest full run as the baseline
    base: dict[str, Any] | None = None
    base_idx = -1
    for i, f in enumerate(reversed(files)):
        data = _read_json(f)
        if data and isinstance(data, dict):
            domains = data.get("domains", [])
            if len(domains) >= 10:
                base = data
                base_idx = len(files) - 1 - i
                break

    if base is None:
        # No full run yet — return the most recent report as-is
        data = _read_json(files[-1])
        return JSONResponse(content=data or {})

    # Merge any partial runs that came after the full run
    partial_files = files[base_idx + 1:]
    if not partial_files:
        return JSONResponse(content=base)

    # Build domain lookup from the base full run
    domain_map: dict[str, dict] = {}
    for d in base.get("domains", []):
        domain_map[d["name"]] = d

    merged = False
    for pf in partial_files:
        pdata = _read_json(pf)
        if not pdata or not isinstance(pdata, dict):
            continue
        for d in pdata.get("domains", []):
            if d.get("name"):
                domain_map[d["name"]] = d
                merged = True

    if not merged:
        return JSONResponse(content=base)

    # Recompute totals from merged domains
    merged_domains = list(domain_map.values())
    total_passed = sum(d.get("passed", 0) for d in merged_domains)
    total_failed = sum(d.get("failed", 0) for d in merged_domains)
    total_skipped = sum(d.get("skipped", 0) for d in merged_domains)
    total_tests = sum(d.get("total", 0) for d in merged_domains)

    # Recompute weighted overall score
    total_weight = sum(d.get("weight", 1.0) for d in merged_domains)
    if total_weight > 0:
        overall_score = sum(d.get("score", 0) * d.get("weight", 1.0) for d in merged_domains) / total_weight
    else:
        overall_score = 0.0

    if overall_score >= 0.95:
        overall_status = "HEALTHY"
    elif overall_score >= 0.75:
        overall_status = "DEGRADED"
    else:
        overall_status = "CRITICAL"

    result = {
        **base,
        "domains": merged_domains,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_skipped": total_skipped,
        "total_tests": total_tests,
        "overall_score": round(overall_score, 4),
        "overall_status": overall_status,
    }
    return JSONResponse(content=result)


@app.get("/api/health/history")
async def health_history() -> JSONResponse:
    files = _sorted_json_files(HEALTH_DIR)
    recent = files[-20:]
    results = []
    for f in recent:
        data = _read_json(f)
        if not data or not isinstance(data, dict):
            continue

        if "-triage" in f.stem:
            # Triage/self-healing report
            triaged = data.get("triaged", 0)
            healed = data.get("healed", 0)
            results.append(
                {
                    "run_id": f.stem,
                    "timestamp": data.get("timestamp"),
                    "overall_score": None,
                    "overall_status": "SELF-HEAL",
                    "total_passed": healed,
                    "total_failed": triaged - healed,
                    "total_tests": triaged,
                    "has_report": False,
                    "is_triage": True,
                }
            )
        else:
            run_id = data.get("run_id") or f.stem
            has_report = (TEST_RESULTS_DIR / run_id / "html-report" / "index.html").exists()
            results.append(
                {
                    "run_id": run_id,
                    "timestamp": data.get("timestamp"),
                    "overall_score": data.get("overall_score"),
                    "overall_status": data.get("overall_status"),
                    "total_passed": data.get("total_passed"),
                    "total_failed": data.get("total_failed"),
                    "total_tests": data.get("total_tests"),
                    "has_report": has_report,
                    "is_triage": False,
                }
            )
    return JSONResponse(content=results)


# ---------------------------------------------------------------------------
# Test report serving
# ---------------------------------------------------------------------------


@app.get("/report/{run_id}")
async def serve_report(run_id: str) -> FileResponse:
    """Serve the Playwright HTML report for a given run."""
    if not SAFE_RUN_ID.match(run_id):
        return JSONResponse({"error": "Invalid run_id"}, status_code=400)
    report_file = (TEST_RESULTS_DIR / run_id / "html-report" / "index.html").resolve()
    if not str(report_file).startswith(str(TEST_RESULTS_DIR.resolve())):
        return JSONResponse({"error": "Access denied"}, status_code=403)
    if not report_file.exists():
        return JSONResponse({"error": "Report not found"}, status_code=404)
    return FileResponse(str(report_file), media_type="text/html")


# ---------------------------------------------------------------------------
# Eval endpoints
# ---------------------------------------------------------------------------


@app.post("/api/eval/notify", dependencies=[Depends(require_auth)])
async def eval_notify(body: dict = {}) -> JSONResponse:
    """Called by the eval runner after an eval completes. Broadcasts to all dashboards."""
    global _eval_status
    agent = body.get("agent", "unknown")
    if agent not in ALLOWED_EVAL_AGENTS:
        agent = "unknown"
    await broadcast_to_dashboard(json.dumps({"event": "eval:agent:complete", "agent": agent}))
    await broadcast_to_dashboard(json.dumps({"event": "eval:updated", "agent": agent}))
    # Track completion and reset state when all running agents complete
    if _eval_status["state"] == "running":
        if agent not in _eval_status["completed"]:
            _eval_status["completed"].append(agent)
        # Check if all known agents are done (for CLI runs we don't know the full list,
        # so reset to idle after 10s of no new agent starts)
    return JSONResponse({"status": "notified"})


@app.post("/api/eval/run/start-external", dependencies=[Depends(require_auth)])
async def eval_start_external(body: dict = {}) -> JSONResponse:
    """Called by CLI eval runner to show running state on dashboard."""
    global _eval_status
    agents = body.get("agents", [])
    if _eval_status["state"] != "running":
        _eval_status = {"state": "running", "current_agent": None, "completed": [], "queued": []}
    await broadcast_to_dashboard(json.dumps({"event": "eval:start", "agents": agents}))
    return JSONResponse({"status": "started"})


@app.post("/api/eval/run/progress", dependencies=[Depends(require_auth)])
async def eval_progress_external(body: dict = {}) -> JSONResponse:
    """Called by CLI eval runner to report scenario progress."""
    agent = body.get("agent", "unknown")
    if agent not in ALLOWED_EVAL_AGENTS:
        agent = "unknown"
    current = body.get("current", 0)
    total = body.get("total", 0)
    _eval_status["progress"][agent] = {"current": current, "total": total}
    _eval_status["last_activity"] = time.time()
    await broadcast_to_dashboard(json.dumps({"event": "eval:log", "agent": agent, "line": f"[{current}/{total}] scenario"}))
    return JSONResponse({"status": "ok"})


@app.post("/api/eval/run/agent-complete-external", dependencies=[Depends(require_auth)])
async def eval_agent_complete_external(body: dict = {}) -> JSONResponse:
    """Called by CLI eval runner when an agent eval finishes. Resets state when all done."""
    global _eval_status
    agent = body.get("agent", "unknown")
    if agent not in ALLOWED_EVAL_AGENTS:
        agent = "unknown"
    if _eval_status["state"] == "running":
        if agent not in _eval_status["completed"]:
            _eval_status["completed"].append(agent)
        # If no more agents are running (all completed), reset to idle
        all_agents = {"triage", "planner", "generator", "healer"}
        if all_agents.issubset(set(_eval_status["completed"])) or _eval_status["current_agent"] == agent:
            _eval_status["state"] = "idle"
            _eval_status["progress"] = {}
            _eval_status["current_agent"] = None
            await broadcast_to_dashboard(json.dumps({
                "event": "eval:complete",
                "completed": len(_eval_status["completed"]),
                "failed": 0,
            }))
    return JSONResponse({"status": "completed"})


@app.post("/api/eval/run/agent-start-external", dependencies=[Depends(require_auth)])
async def eval_agent_start_external(body: dict = {}) -> JSONResponse:
    """Called by CLI eval runner when a specific agent eval begins."""
    global _eval_status
    agent = body.get("agent", "unknown")
    if agent not in ALLOWED_EVAL_AGENTS:
        agent = "unknown"
    if _eval_status["state"] != "running":
        _eval_status = {"state": "running", "current_agent": agent, "completed": [], "queued": [], "progress": {}, "last_activity": time.time()}
    _eval_status["current_agent"] = agent
    _eval_status["last_activity"] = time.time()
    await broadcast_to_dashboard(json.dumps({"event": "eval:agent:start", "agent": agent}))
    return JSONResponse({"status": "started"})


@app.post("/api/health/notify", dependencies=[Depends(require_auth)])
async def health_notify(body: dict = {}) -> JSONResponse:
    """Called after a health report is computed. Broadcasts to all dashboards."""
    run_id = body.get("run_id", "unknown")
    await broadcast_to_dashboard(json.dumps({"event": "health:updated", "run_id": run_id}))
    return JSONResponse({"status": "notified"})


# ---------------------------------------------------------------------------
# Eval runner (trigger evals from dashboard)
# ---------------------------------------------------------------------------

_eval_status: dict = {"state": "idle", "current_agent": None, "completed": [], "queued": [], "progress": {}, "last_activity": 0}


@app.post("/api/eval/run", dependencies=[Depends(require_auth)])
async def run_eval(body: dict = {}):
    global _eval_status
    if _eval_status["state"] == "running":
        return JSONResponse({"error": "Eval already running"}, status_code=409)

    agents = body.get("agents", [])
    run_all = body.get("all", False)
    if run_all:
        agents = ["triage", "planner", "generator", "healer"]

    # Validate agent names against allowlist to prevent code injection
    agents = [a for a in agents if a in ALLOWED_EVAL_AGENTS]
    if not agents:
        return JSONResponse({"error": "No valid agents specified"}, status_code=400)

    _eval_status = {"state": "running", "current_agent": None, "completed": [], "queued": list(agents), "progress": {}, "last_activity": time.time()}
    asyncio.create_task(_execute_eval_run(agents))
    return JSONResponse({"status": "started", "agents": agents})


@app.get("/api/eval/run/status")
async def eval_run_status():
    # Auto-reset stale running state (no activity for 5 minutes)
    if _eval_status["state"] == "running" and _eval_status["last_activity"] > 0:
        if time.time() - _eval_status["last_activity"] > 300:
            _eval_status["state"] = "idle"
            _eval_status["progress"] = {}
            _eval_status["current_agent"] = None
    return JSONResponse(content=_eval_status)


@app.post("/api/eval/stop", dependencies=[Depends(require_auth)])
async def stop_eval():
    global _eval_status
    if _eval_status["state"] == "running":
        _eval_status["state"] = "stopped"
        cancelled = list(_eval_status["queued"])
        _eval_status["queued"] = []
        await broadcast_to_dashboard(json.dumps({
            "event": "eval:complete",
            "completed": len(_eval_status["completed"]),
            "cancelled": cancelled,
        }))
        _eval_status["state"] = "idle"
        _eval_status["progress"] = {}
        _eval_status["current_agent"] = None
        return JSONResponse({"status": "stopped", "cancelled": cancelled})
    return JSONResponse({"status": "not_running"})


async def _execute_eval_run(agents: list[str]):
    global _eval_status

    await broadcast_to_dashboard(json.dumps({"event": "eval:start", "agents": agents}))

    # Broadcast start for all agents
    _eval_status["queued"] = []
    _eval_status["current_agent"] = "all" if len(agents) > 1 else agents[0]
    for agent in agents:
        await broadcast_to_dashboard(json.dumps({"event": "eval:agent:start", "agent": agent}))

    # Run all agents in parallel as separate subprocesses
    async def _run_one(agent: str):
        try:
            cmd = [
                sys.executable, "-u", "-c",
                f"import os; os.environ['EVAL_DASHBOARD_SUBPROCESS']='1'; "
                f"from dotenv import load_dotenv; load_dotenv(os.path.join(os.getcwd(), '.env')); "
                f"import logging; logging.basicConfig(level=logging.INFO, format='%(message)s'); "
                f"import asyncio; from qa_agent.eval.eval_runner import run_{agent}_eval; asyncio.run(run_{agent}_eval())"
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
            )

            agent_completed = False
            import re as _re
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                if decoded:
                    await broadcast_to_dashboard(json.dumps({"event": "eval:log", "agent": agent, "line": decoded}))
                    # Track progress and detect when all scenarios done
                    m = _re.search(r"\[(\d+)/(\d+)\]", decoded)
                    if m:
                        _eval_status["progress"][agent] = {"current": int(m.group(1)), "total": int(m.group(2))}
                    if m and int(m.group(1)) >= int(m.group(2)) and not agent_completed:
                        agent_completed = True
                        _eval_status["completed"].append(agent)
                        await broadcast_to_dashboard(json.dumps({"event": "eval:agent:complete", "agent": agent}))

            await proc.wait()
            # If we never saw progress markers, complete now
            if not agent_completed:
                _eval_status["completed"].append(agent)
                await broadcast_to_dashboard(json.dumps({"event": "eval:agent:complete", "agent": agent}))

        except Exception as e:
            await broadcast_to_dashboard(json.dumps({"event": "eval:agent:error", "agent": agent, "error": str(e)}))

    await asyncio.gather(*[_run_one(agent) for agent in agents])

    _eval_status["state"] = "idle"
    _eval_status["progress"] = {}
    _eval_status["current_agent"] = None
    _eval_status["queued"] = []

    await broadcast_to_dashboard(json.dumps({
        "event": "eval:complete",
        "completed": len(_eval_status["completed"]),
        "failed": len(agents) - len(_eval_status["completed"]),
    }))


@app.get("/api/eval/{agent}/latest")
async def eval_agent_latest(agent: str) -> JSONResponse:
    agent_dir = EVAL_DIR / agent
    files = _sorted_json_files(agent_dir)
    if not files:
        return JSONResponse(content={})
    data = _read_json(files[-1])
    return JSONResponse(content=data or {})


@app.get("/api/eval/summary")
async def eval_summary() -> JSONResponse:
    agents = ["triage", "planner", "generator", "healer"]
    summary: dict[str, Any] = {}

    for agent in agents:
        agent_dir = EVAL_DIR / agent
        files = _sorted_json_files(agent_dir)
        if not files:
            summary[agent] = {"score": None, "passed": None}
            continue

        data = _read_json(files[-1])
        if not data or not isinstance(data, dict):
            summary[agent] = {"score": None, "passed": None}
            continue

        key = f"{agent}_accuracy"
        score_obj = data.get(key, {})
        # Fallback for older generator reports that don't have generator_accuracy
        if agent == "generator" and not score_obj:
            score_obj = data.get("locator_quality", {})

        score = score_obj.get("score") if isinstance(score_obj, dict) else None
        passed = data.get("passed")

        # Cumulative token/cost across all eval runs (odometer — only goes up)
        total_tokens = 0
        total_cost = 0.0
        for f in files:
            report = _read_json(f)
            if not report or not isinstance(report, dict):
                continue
            tu = report.get("token_usage", {})
            if isinstance(tu, dict):
                total_tokens += tu.get("total_tokens", 0) or 0
                total_cost += tu.get("cost_usd", 0.0) or 0.0

        summary[agent] = {
            "score": score,
            "passed": passed,
            "tokens": total_tokens if total_tokens > 0 else None,
            "cost": round(total_cost, 4) if total_cost > 0 else None,
        }

    return JSONResponse(content=summary)


# ---------------------------------------------------------------------------
# ECC Agent Eval endpoints
# ---------------------------------------------------------------------------

ECC_DETECTION_AGENTS = [
    "security-reviewer", "code-reviewer", "silent-failure-hunter",
    "python-reviewer", "typescript-reviewer", "fastapi-reviewer",
    "performance-optimizer",
]
ECC_GENERATIVE_AGENTS = [
    "planner-ecc", "tdd-guide", "build-error-resolver",
    "e2e-runner", "refactor-cleaner",
]
ECC_ALL_AGENTS = ECC_DETECTION_AGENTS + ECC_GENERATIVE_AGENTS

_ecc_eval_status: dict = {"state": "idle", "current_agent": None, "completed": [], "progress": {}, "last_activity": 0}


@app.get("/api/eval/ecc/scores")
async def ecc_eval_scores() -> JSONResponse:
    """Return latest scorecard for all 12 ECC agents."""
    summary: dict[str, Any] = {}
    for agent in ECC_ALL_AGENTS:
        agent_dir = ECC_EVAL_DIR / agent
        files = _sorted_json_files(agent_dir)
        if not files:
            summary[agent] = {"score": None, "passed": None, "tier": "detection" if agent in ECC_DETECTION_AGENTS else "generative"}
            continue
        data = _read_json(files[-1])
        if not data or not isinstance(data, dict):
            summary[agent] = {"score": None, "passed": None, "tier": "detection" if agent in ECC_DETECTION_AGENTS else "generative"}
            continue

        tier = data.get("tier", "detection")
        scores = data.get("scores", {})
        if tier == "detection":
            score = scores.get("recall")
        else:
            score = scores.get("quality")

        total_tokens = 0
        for f in files:
            report = _read_json(f)
            if report and isinstance(report, dict):
                total_tokens += report.get("token_estimate", 0) or 0

        summary[agent] = {
            "score": score,
            "passed": data.get("passed"),
            "tier": tier,
            "scores": scores,
            "tokens": total_tokens if total_tokens > 0 else None,
            "timestamp": data.get("timestamp"),
        }
    return JSONResponse(content=summary)


@app.get("/api/eval/ecc/scores/{agent}")
async def ecc_eval_agent_scores(agent: str) -> JSONResponse:
    """Return latest scorecard for a specific ECC agent."""
    if agent not in ECC_ALL_AGENTS:
        return JSONResponse({"error": "Unknown agent"}, status_code=400)
    agent_dir = ECC_EVAL_DIR / agent
    files = _sorted_json_files(agent_dir)
    if not files:
        return JSONResponse(content={})
    data = _read_json(files[-1])
    return JSONResponse(content=data or {})


@app.get("/api/eval/ecc/history/{agent}")
async def ecc_eval_agent_history(agent: str) -> JSONResponse:
    """Return historical scorecards for trend display."""
    if agent not in ECC_ALL_AGENTS:
        return JSONResponse({"error": "Unknown agent"}, status_code=400)
    agent_dir = ECC_EVAL_DIR / agent
    files = _sorted_json_files(agent_dir)
    history = []
    for f in files[-10:]:  # Last 10 runs
        data = _read_json(f)
        if data and isinstance(data, dict):
            history.append({
                "eval_run_id": data.get("eval_run_id"),
                "timestamp": data.get("timestamp"),
                "passed": data.get("passed"),
                "scores": data.get("scores"),
            })
    return JSONResponse(content=history)


@app.post("/api/eval/ecc/run", dependencies=[Depends(require_auth)])
async def run_ecc_eval_endpoint(body: dict = {}):
    """Trigger ECC agent eval run from dashboard."""
    global _ecc_eval_status
    if _ecc_eval_status["state"] == "running":
        return JSONResponse({"error": "ECC eval already running"}, status_code=409)

    agents = [a for a in body.get("agents", []) if a in ECC_ALL_AGENTS]
    run_all = body.get("all", False)
    tier = body.get("tier")
    if run_all:
        agents = list(ECC_ALL_AGENTS)
    elif tier == "detection":
        agents = list(ECC_DETECTION_AGENTS)
    elif tier == "generative":
        agents = list(ECC_GENERATIVE_AGENTS)

    if not agents:
        return JSONResponse({"error": "No valid agents specified"}, status_code=400)

    _ecc_eval_status = {"state": "running", "current_agent": None, "completed": [], "progress": {}, "last_activity": time.time()}
    asyncio.create_task(_execute_ecc_eval_run(agents))
    return JSONResponse({"status": "started", "agents": agents})


async def _execute_ecc_eval_run(agents: list[str]):
    """Run ECC evals sequentially (each agent is expensive)."""
    global _ecc_eval_status
    await broadcast_to_dashboard(json.dumps({"event": "ecc_eval:start", "agents": agents}))

    for agent in agents:
        _ecc_eval_status["current_agent"] = agent
        _ecc_eval_status["last_activity"] = time.time()
        await broadcast_to_dashboard(json.dumps({"event": "ecc_eval:agent:start", "agent": agent}))

        try:
            cmd = [
                sys.executable, "-u", "-c",
                f"from dotenv import load_dotenv; load_dotenv('.env'); "
                f"import logging; logging.basicConfig(level=logging.INFO, format='%(message)s', stream=__import__('sys').stdout); "
                f"import asyncio; from qa_agent.eval.ecc.ecc_eval_runner import run_ecc_eval; "
                f"result = asyncio.run(run_ecc_eval(agents=['{agent}'])); "
                f"import json; print(json.dumps(result.get('results', {{}}).get('{agent}', {{}})))"
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
            )

            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                if decoded:
                    await broadcast_to_dashboard(json.dumps({"event": "ecc_eval:log", "agent": agent, "line": decoded}))

            await proc.wait()
            _ecc_eval_status["completed"].append(agent)
            await broadcast_to_dashboard(json.dumps({"event": "ecc_eval:agent:complete", "agent": agent}))

        except Exception as e:
            await broadcast_to_dashboard(json.dumps({"event": "ecc_eval:agent:error", "agent": agent, "error": str(e)}))

    _ecc_eval_status["state"] = "idle"
    _ecc_eval_status["current_agent"] = None
    await broadcast_to_dashboard(json.dumps({
        "event": "ecc_eval:complete",
        "completed": len(_ecc_eval_status["completed"]),
        "total": len(agents),
    }))


@app.post("/api/eval/ecc/stop", dependencies=[Depends(require_auth)])
async def stop_ecc_eval():
    global _ecc_eval_status
    _ecc_eval_status["state"] = "idle"
    _ecc_eval_status["current_agent"] = None
    await broadcast_to_dashboard(json.dumps({"event": "ecc_eval:complete", "completed": len(_ecc_eval_status.get("completed", [])), "total": 0}))
    return JSONResponse({"status": "stopped"})


# ---------------------------------------------------------------------------
# Audit endpoint
# ---------------------------------------------------------------------------


@app.get("/api/audit/summary")
async def audit_summary() -> JSONResponse:
    files = _sorted_json_files(AUDIT_DIR)
    if not files:
        return JSONResponse(content={"total_runs": 0, "total_tokens": 0, "total_cost": 0.0, "per_node_averages": {}})

    total_runs = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0
    runs_list: list[dict[str, Any]] = []

    for f in files:
        data = _read_json(f)
        if not data or not isinstance(data, dict):
            continue
        total_runs += 1
        inp = data.get("total_input_tokens") or 0
        out = data.get("total_output_tokens") or 0
        cost = data.get("estimated_cost_usd") or 0.0
        total_input_tokens += inp
        total_output_tokens += out
        total_cost += cost
        runs_list.append({
            "run_id": data.get("run_id", f.stem),
            "total_input_tokens": inp,
            "total_output_tokens": out,
            "estimated_cost_usd": round(cost, 6),
        })

    return JSONResponse(
        content={
            "total_runs": total_runs,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cost": round(total_cost, 6),
            "runs": runs_list,
        }
    )


# ---------------------------------------------------------------------------
# Test runner endpoints
# ---------------------------------------------------------------------------


@app.post("/api/tests/run", dependencies=[Depends(require_auth)])
async def run_tests(body: dict = {}):
    global _test_process, _test_run_status
    if _test_process and _test_process.returncode is None:
        return JSONResponse({"error": "Tests already running"}, status_code=409)

    specs = [s for s in body.get("specs", []) if s in ALLOWED_SPECS]
    try:
        workers = max(1, min(int(body.get("workers", 3)), MAX_WORKERS))
    except (TypeError, ValueError):
        workers = 3
    try:
        retries = max(0, min(int(body.get("retries", 0)), MAX_RETRIES))
    except (TypeError, ValueError):
        retries = 0
    heal = bool(body.get("heal", False))

    run_id = datetime.now(tz=timezone.utc).strftime("%m_%d_%Y_%H-%M-%S")
    _test_run_status = {"state": "running", "run_id": run_id, "started_at": datetime.now(tz=timezone.utc).isoformat()}

    asyncio.create_task(_execute_test_run(specs, workers, retries, heal, run_id))
    return JSONResponse({"status": "started", "run_id": run_id})


@app.get("/api/tests/status")
async def test_status():
    return JSONResponse(content=_test_run_status)


@app.get("/api/tests/lastrun")
async def test_lastrun():
    """Return the last completed run's log lines for late-joining clients."""
    return JSONResponse(content={"log": _last_run_log})


@app.post("/api/tests/clear", dependencies=[Depends(require_auth)])
async def clear_tests():
    global _test_run_status
    _test_run_status = {"state": "cleared", "run_id": None, "started_at": None}
    _last_run_log.clear()
    await broadcast_to_dashboard(json.dumps({"event": "runner:clear"}))
    return JSONResponse({"status": "cleared"})


@app.post("/api/tests/stop", dependencies=[Depends(require_auth)])
async def stop_tests():
    global _test_process, _test_run_status
    if _test_process and _test_process.returncode is None:
        _test_process.terminate()
        _test_run_status["state"] = "stopped"
        return JSONResponse({"status": "stopped"})
    return JSONResponse({"status": "not_running"})


async def _execute_test_run(specs: list, workers: int, retries: int, heal: bool, run_id: str):
    global _test_process, _test_run_status

    # Clean temp dir
    if TEST_RESULTS_TMP.exists():
        shutil.rmtree(TEST_RESULTS_TMP)

    # Build command
    cmd = ["npx", "playwright", "test", f"--workers={workers}", f"--retries={retries}"]
    if specs:
        cmd.extend([f"tests_generated/{s}" if not s.startswith("tests_generated/") else s for s in specs])

    _last_run_log.clear()
    await broadcast_to_dashboard(json.dumps({"event": "runner:start", "run_id": run_id, "specs": specs or ["all"]}))

    try:
        _test_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
        )

        # Stream output line by line
        while True:
            line = await _test_process.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip()
            if decoded:
                _last_run_log.append(decoded)
                await broadcast_to_dashboard(json.dumps({"event": "runner:log", "line": decoded}))

        exit_code = await _test_process.wait()

        # Move results to timestamped folder
        dest = TEST_RESULTS_DIR / run_id
        if TEST_RESULTS_TMP.exists():
            dest.mkdir(parents=True, exist_ok=True)
            for item in TEST_RESULTS_TMP.iterdir():
                target = dest / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)
            shutil.rmtree(TEST_RESULTS_TMP)

        # Compute health score
        results_json = dest / "results.json"
        if results_json.exists():
            try:
                from qa_agent.health import compute_health_from_json
                compute_health_from_json(results_json, dest)

                # Copy to health-reports
                health_reports = PROJECT_ROOT / "health-reports"
                health_reports.mkdir(exist_ok=True)
                health_json = dest / "health.json"
                health_md = dest / "health.md"
                if health_json.exists():
                    shutil.copy2(health_json, health_reports / f"{run_id}.json")
                if health_md.exists():
                    shutil.copy2(health_md, health_reports / f"{run_id}.md")

                # Git commit
                subprocess.run(["git", "add", "health-reports/"], cwd=str(PROJECT_ROOT), capture_output=True, timeout=10)
                subprocess.run(["git", "commit", "-m", f"Health report: {run_id} (via dashboard)"], cwd=str(PROJECT_ROOT), capture_output=True, timeout=10)
                subprocess.run(["git", "push"], cwd=str(PROJECT_ROOT), capture_output=True, timeout=30)
            except Exception as e:
                await broadcast_to_dashboard(json.dumps({"event": "runner:log", "line": f"[Health] Error: {e}"}))

        # Broadcast health update directly (don't HTTP self-call)
        await broadcast_to_dashboard(json.dumps({"event": "health:updated", "run_id": run_id}))

        _test_run_status["state"] = "complete"
        _test_run_status["exit_code"] = exit_code
        await broadcast_to_dashboard(json.dumps({"event": "runner:end", "exit_code": exit_code, "run_id": run_id}))

        # Self-healing
        if heal and exit_code != 0 and results_json.exists():
            _test_run_status["state"] = "healing"
            await broadcast_to_dashboard(json.dumps({"event": "runner:healing", "message": "Self-healing in progress..."}))
            try:
                from qa_agent.triage_runner import run_self_healing
                summary = await run_self_healing(results_json)
                await broadcast_to_dashboard(json.dumps({"event": "runner:healed", "healed": summary.get("healed", 0), "skipped": summary.get("unknown", 0) + summary.get("app_defects", 0)}))
            except Exception as e:
                await broadcast_to_dashboard(json.dumps({"event": "runner:log", "line": f"[Heal] Error: {e}"}))

        _test_run_status["state"] = "idle"

    except Exception as e:
        _test_run_status["state"] = "error"
        _test_run_status["error"] = str(e)
        await broadcast_to_dashboard(json.dumps({"event": "runner:end", "exit_code": -1, "error": str(e)}))


# ---------------------------------------------------------------------------
# WebSocket endpoints
# ---------------------------------------------------------------------------


@app.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket) -> None:
    """Browser dashboard client."""
    await websocket.accept()
    dashboard_connections.append(websocket)
    try:
        while True:
            # Keep the connection alive; browsers may send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in dashboard_connections:
            dashboard_connections.remove(websocket)


@app.websocket("/ws/tests")
async def ws_tests(websocket: WebSocket) -> None:
    """Playwright reporter pushes test events here; we fan-out to dashboards."""
    # Authenticate via query param if token is set
    if DASHBOARD_API_TOKEN:
        token = websocket.query_params.get("token", "")
        if token != DASHBOARD_API_TOKEN:
            await websocket.close(code=4001, reason="Unauthorized")
            return
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            # Validate message is JSON with an allowed event type
            try:
                parsed = json.loads(message)
                if not isinstance(parsed, dict) or parsed.get("event") not in ALLOWED_WS_EVENTS:
                    continue  # silently drop invalid messages
            except (json.JSONDecodeError, TypeError):
                continue
            await broadcast_to_dashboard(message)
    except WebSocketDisconnect:
        pass
