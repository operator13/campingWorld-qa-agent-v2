"""Eval Worker server — runs evals and tests inside a fully-equipped container.

The Dashboard Server (Container A) proxies RUN requests here.
This server broadcasts progress events back to the Dashboard via HTTP POST,
which then fans them out to browser WebSocket clients.
"""
import asyncio
import json
import logging
import os
import re
import shutil
import signal
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(message)s")
logger = logging.getLogger("worker")

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://dashboard:8080")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", "/app"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
HEALTH_DIR = DATA_DIR / "health-reports"
EVAL_DIR = DATA_DIR / "qa_agent" / "eval" / "reports"
ECC_EVAL_DIR = DATA_DIR / "qa_agent" / "eval" / "ecc" / "reports"
TESTS_DIR = PROJECT_ROOT / "tests_generated"
TEST_RESULTS_TMP = PROJECT_ROOT / "test-results-tmp"
TEST_RESULTS_DIR = DATA_DIR / "test-results"

# ---------------------------------------------------------------------------
# Security constants
# ---------------------------------------------------------------------------

ALLOWED_EVAL_AGENTS = {"triage", "planner", "generator", "healer"}
ALLOWED_ECC_AGENTS = [
    "security-reviewer", "code-reviewer", "silent-failure-hunter",
    "python-reviewer", "typescript-reviewer", "fastapi-reviewer",
    "performance-optimizer",
    "planner-ecc", "tdd-guide", "build-error-resolver",
    "e2e-runner", "refactor-cleaner",
]
ALLOWED_SPECS = {
    "cart.spec.ts", "checkout.spec.ts", "footer.spec.ts", "good-sam.spec.ts",
    "homepage.spec.ts", "nav.spec.ts", "product.spec.ts", "register.spec.ts",
    "rv-parts.spec.ts", "rvs-for-sale-detail.spec.ts", "rvs-for-sale.spec.ts",
    "search.spec.ts", "sign-in.spec.ts", "store-locator.spec.ts",
}
MAX_WORKERS = 10
MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

GRACEFUL_SHUTDOWN_TIMEOUT = 60  # seconds to wait for running evals


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup/shutdown lifecycle for the worker."""
    logger.info("Worker starting (API key: %s)", "present" if ANTHROPIC_API_KEY else "MISSING")
    yield
    # Graceful shutdown
    logger.info("Worker shutting down...")
    _shutdown_event.set()
    if _eval_status["state"] == "running" or _ecc_eval_status["state"] == "running":
        logger.info("Waiting up to %ds for running evals to finish...", GRACEFUL_SHUTDOWN_TIMEOUT)
        deadline = time.time() + GRACEFUL_SHUTDOWN_TIMEOUT
        while time.time() < deadline:
            if _eval_status["state"] != "running" and _ecc_eval_status["state"] != "running":
                logger.info("All evals finished before shutdown deadline")
                break
            await asyncio.sleep(1)
        else:
            logger.warning("Shutdown deadline reached — force stopping")
    if _test_process and _test_process.returncode is None:
        _test_process.terminate()
        logger.info("Terminated running test process")


app = FastAPI(title="QA Eval Worker", lifespan=lifespan)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_eval_status: dict[str, Any] = {
    "state": "idle",
    "current_agent": None,
    "completed": [],
    "progress": {},
    "last_activity": 0,
}
_ecc_eval_status: dict[str, Any] = {
    "state": "idle",
    "current_agent": None,
    "completed": [],
    "progress": {},
    "last_activity": 0,
}
_test_process: asyncio.subprocess.Process | None = None
_test_run_status: dict[str, Any] = {"state": "idle", "run_id": None}

# Track running eval subprocesses for cancellation
_eval_processes: list[asyncio.subprocess.Process] = []
_ecc_eval_processes: list[asyncio.subprocess.Process] = []

# Graceful shutdown
_shutdown_event = asyncio.Event()
_startup_time = time.time()


# ---------------------------------------------------------------------------
# Dashboard broadcast helper
# ---------------------------------------------------------------------------

async def _broadcast_to_dashboard(event_data: dict[str, Any]) -> None:
    """POST an event to the Dashboard for WebSocket fan-out.

    All events go through /api/worker/broadcast (runner/eval/health) or
    /api/eval/ecc/broadcast (ECC events). The dashboard handles state
    tracking and WebSocket fan-out in those endpoints.

    Best-effort: if the dashboard is down, we log and continue.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            event = event_data.get("event", "")
            if event.startswith("ecc_eval:"):
                url = f"{DASHBOARD_URL}/api/eval/ecc/broadcast"
            else:
                url = f"{DASHBOARD_URL}/api/worker/broadcast"
            await client.post(url, json=event_data)
    except Exception as e:
        logger.warning("Dashboard broadcast failed (continuing): %s", e)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
@app.get("/api/worker/health")
async def health_check() -> JSONResponse:
    """Worker health check — reports API key presence, CLI availability, uptime."""
    cli_available = shutil.which("claude") is not None
    node_available = shutil.which("node") is not None
    playwright_available = shutil.which("npx") is not None

    return JSONResponse(content={
        "status": "ok",
        "api_key": bool(ANTHROPIC_API_KEY),
        "cli": cli_available,
        "node": node_available,
        "playwright": playwright_available,
        "uptime_seconds": round(time.time() - _startup_time, 1),
        "eval_state": _eval_status["state"],
        "ecc_eval_state": _ecc_eval_status["state"],
        "test_state": _test_run_status["state"],
    })


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

@app.get("/api/worker/status")
async def worker_status() -> JSONResponse:
    """Current worker status — running agent, progress, queue."""
    return JSONResponse(content={
        "eval": _eval_status,
        "ecc_eval": _ecc_eval_status,
        "test": _test_run_status,
    })


# ---------------------------------------------------------------------------
# Pipeline Agent Eval endpoints
# ---------------------------------------------------------------------------

@app.post("/api/worker/eval/run")
async def run_pipeline_eval(body: dict = {}) -> JSONResponse:
    """Trigger pipeline agent eval (triage, planner, generator, healer)."""
    global _eval_status

    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    if _eval_status["state"] == "running":
        raise HTTPException(status_code=409, detail="Pipeline eval already running")

    agents: list[str] = []
    if body.get("all"):
        agents = list(ALLOWED_EVAL_AGENTS)
    else:
        agent = body.get("agent")
        agents_list = body.get("agents", [])
        if agent and agent in ALLOWED_EVAL_AGENTS:
            agents = [agent]
        elif agents_list:
            agents = [a for a in agents_list if a in ALLOWED_EVAL_AGENTS]

    if not agents:
        raise HTTPException(status_code=400, detail="No valid agents specified")

    _eval_status = {
        "state": "running",
        "current_agent": None,
        "completed": [],
        "progress": {},
        "last_activity": time.time(),
    }
    asyncio.create_task(_execute_pipeline_eval(agents))
    return JSONResponse({"status": "started", "agents": agents})


async def _execute_pipeline_eval(agents: list[str]) -> None:
    """Run pipeline evals as parallel subprocesses."""
    global _eval_status

    await _broadcast_to_dashboard({"event": "eval:start", "agents": agents})

    _eval_status["current_agent"] = "all" if len(agents) > 1 else agents[0]
    for agent in agents:
        await _broadcast_to_dashboard({"event": "eval:agent:start", "agent": agent})

    async def _run_one(agent: str) -> None:
        try:
            if _eval_status["state"] != "running":
                return  # Stopped
            cmd = [
                sys.executable, "-u", "-c",
                f"import os; os.environ['EVAL_DASHBOARD_SUBPROCESS']='1'; "
                f"from dotenv import load_dotenv; load_dotenv(os.path.join(os.getcwd(), '.env')); "
                f"import logging; logging.basicConfig(level=logging.INFO, format='%(message)s'); "
                f"import asyncio; from qa_agent.eval.eval_runner import run_{agent}_eval; "
                f"asyncio.run(run_{agent}_eval())",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
            )
            _eval_processes.append(proc)

            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                if decoded:
                    await _broadcast_to_dashboard({
                        "event": "eval:log", "agent": agent, "line": decoded,
                    })
                    m = re.search(r"\[(\d+)/(\d+)\]", decoded)
                    if m:
                        current, total = int(m.group(1)), int(m.group(2))
                        _eval_status["progress"][agent] = {"current": current, "total": total}

            # Wait for subprocess to exit — scorecard is saved to disk on exit
            await proc.wait()
            _eval_status["completed"].append(agent)
            await _broadcast_to_dashboard({
                "event": "eval:agent:complete", "agent": agent,
            })

        except Exception as e:
            logger.error("Pipeline eval error for %s: %s", agent, e)
            await _broadcast_to_dashboard({
                "event": "eval:agent:error", "agent": agent, "error": str(e),
            })

    await asyncio.gather(*[_run_one(a) for a in agents])

    _eval_processes.clear()
    _eval_status["state"] = "idle"
    _eval_status["progress"] = {}
    _eval_status["current_agent"] = None

    await _broadcast_to_dashboard({
        "event": "eval:complete",
        "completed": len(_eval_status["completed"]),
        "failed": len(agents) - len(_eval_status["completed"]),
    })


# ---------------------------------------------------------------------------
# ECC Agent Eval endpoints
# ---------------------------------------------------------------------------

@app.post("/api/worker/eval/ecc/run")
async def run_ecc_eval(body: dict = {}) -> JSONResponse:
    """Trigger ECC development agent evals."""
    global _ecc_eval_status

    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    if _ecc_eval_status["state"] == "running":
        raise HTTPException(status_code=409, detail="ECC eval already running")

    agents: list[str] = []
    if body.get("all"):
        agents = list(ALLOWED_ECC_AGENTS)
    elif body.get("tier") == "detection":
        agents = ALLOWED_ECC_AGENTS[:7]
    elif body.get("tier") == "generative":
        agents = ALLOWED_ECC_AGENTS[7:]
    else:
        agents = [a for a in body.get("agents", []) if a in ALLOWED_ECC_AGENTS]

    if not agents:
        raise HTTPException(status_code=400, detail="No valid agents specified")

    _ecc_eval_status = {
        "state": "running",
        "current_agent": None,
        "completed": [],
        "progress": {},
        "last_activity": time.time(),
    }
    asyncio.create_task(_execute_ecc_eval(agents))
    return JSONResponse({"status": "started", "agents": agents})


async def _execute_ecc_eval(agents: list[str]) -> None:
    """Run ECC evals as parallel subprocesses."""
    global _ecc_eval_status

    await _broadcast_to_dashboard({"event": "ecc_eval:start", "agents": agents})

    for agent in agents:
        await _broadcast_to_dashboard({"event": "ecc_eval:agent:start", "agent": agent})

    async def _run_one(agent: str) -> None:
        try:
            if _ecc_eval_status["state"] != "running":
                return  # Stopped
            cmd = [
                sys.executable, "-u", "-c",
                f"from dotenv import load_dotenv; load_dotenv('.env'); "
                f"import logging; logging.basicConfig(level=logging.INFO, format='%(message)s', stream=__import__('sys').stdout); "
                f"import asyncio; from qa_agent.eval.ecc.ecc_eval_runner import run_ecc_eval; "
                f"result = asyncio.run(run_ecc_eval(agents=['{agent}'])); "
                f"import json; print(json.dumps(result.get('results', {{}}).get('{agent}', {{}})))",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(PROJECT_ROOT),
            )
            _ecc_eval_processes.append(proc)

            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                if decoded:
                    await _broadcast_to_dashboard({
                        "event": "ecc_eval:log", "agent": agent, "line": decoded,
                    })

            await proc.wait()
            _ecc_eval_status["completed"].append(agent)
            _ecc_eval_status["last_activity"] = time.time()
            await _broadcast_to_dashboard({
                "event": "ecc_eval:agent:complete", "agent": agent,
            })

        except Exception as e:
            logger.error("ECC eval error for %s: %s", agent, e)
            await _broadcast_to_dashboard({
                "event": "ecc_eval:agent:error", "agent": agent, "error": str(e),
            })

    await asyncio.gather(*[_run_one(a) for a in agents])

    _ecc_eval_processes.clear()
    _ecc_eval_status["state"] = "idle"
    _ecc_eval_status["current_agent"] = None

    await _broadcast_to_dashboard({
        "event": "ecc_eval:complete",
        "completed": len(_ecc_eval_status["completed"]),
        "total": len(agents),
    })


# ---------------------------------------------------------------------------
# Eval Stop endpoints
# ---------------------------------------------------------------------------


@app.post("/api/worker/eval/stop")
async def stop_pipeline_eval() -> JSONResponse:
    """Kill all running pipeline eval subprocesses."""
    global _eval_status
    killed = 0
    for proc in _eval_processes:
        if proc.returncode is None:
            proc.terminate()
            killed += 1
    _eval_processes.clear()
    _eval_status["state"] = "idle"
    _eval_status["progress"] = {}
    _eval_status["current_agent"] = None
    await _broadcast_to_dashboard({
        "event": "eval:complete",
        "completed": len(_eval_status.get("completed", [])),
        "failed": 0,
    })
    return JSONResponse({"status": "stopped", "killed": killed})


@app.post("/api/worker/eval/ecc/stop")
async def stop_ecc_eval() -> JSONResponse:
    """Kill all running ECC eval subprocesses."""
    global _ecc_eval_status
    killed = 0
    for proc in _ecc_eval_processes:
        if proc.returncode is None:
            proc.terminate()
            killed += 1
    _ecc_eval_processes.clear()
    _ecc_eval_status["state"] = "idle"
    _ecc_eval_status["current_agent"] = None
    await _broadcast_to_dashboard({
        "event": "ecc_eval:complete",
        "completed": len(_ecc_eval_status.get("completed", [])),
        "total": 0,
    })
    return JSONResponse({"status": "stopped", "killed": killed})


# ---------------------------------------------------------------------------
# Test Runner endpoints
# ---------------------------------------------------------------------------

@app.post("/api/worker/test/run")
async def run_tests(body: dict = {}) -> JSONResponse:
    """Run Playwright tests inside the worker container."""
    global _test_process, _test_run_status

    if _test_process and _test_process.returncode is None:
        raise HTTPException(status_code=409, detail="Tests already running")

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


@app.post("/api/worker/test/stop")
async def stop_tests() -> JSONResponse:
    """Stop running tests."""
    global _test_process, _test_run_status
    if _test_process and _test_process.returncode is None:
        _test_process.terminate()
        _test_run_status["state"] = "stopped"
        return JSONResponse({"status": "stopped"})
    return JSONResponse({"status": "not_running"})


async def _execute_test_run(
    specs: list[str], workers: int, retries: int, heal: bool, run_id: str
) -> None:
    """Execute Playwright tests and stream results to dashboard."""
    global _test_process, _test_run_status

    if TEST_RESULTS_TMP.exists():
        shutil.rmtree(TEST_RESULTS_TMP)

    cmd = ["npx", "playwright", "test", f"--workers={workers}", f"--retries={retries}"]
    if specs:
        cmd.extend([f"tests_generated/{s}" if not s.startswith("tests_generated/") else s for s in specs])

    await _broadcast_to_dashboard({
        "event": "runner:start", "run_id": run_id, "specs": specs or ["all"],
    })

    try:
        _test_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
        )

        while True:
            line = await _test_process.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip()
            if decoded:
                await _broadcast_to_dashboard({"event": "runner:log", "line": decoded})

        exit_code = await _test_process.wait()

        # Move results to timestamped folder in shared volume
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

                health_reports = HEALTH_DIR
                health_reports.mkdir(parents=True, exist_ok=True)
                health_json = dest / "health.json"
                health_md = dest / "health.md"
                if health_json.exists():
                    shutil.copy2(health_json, health_reports / f"{run_id}.json")
                if health_md.exists():
                    shutil.copy2(health_md, health_reports / f"{run_id}.md")
            except Exception as e:
                logger.error("Health computation error: %s", e)
                await _broadcast_to_dashboard({"event": "runner:log", "line": f"[Health] Error: {e}"})

        await _broadcast_to_dashboard({"event": "health:updated", "run_id": run_id})

        _test_run_status["state"] = "complete"
        _test_run_status["exit_code"] = exit_code
        await _broadcast_to_dashboard({"event": "runner:end", "exit_code": exit_code, "run_id": run_id})

        # Self-healing
        if heal and exit_code != 0 and results_json.exists():
            _test_run_status["state"] = "healing"
            await _broadcast_to_dashboard({"event": "runner:healing", "message": "Self-healing in progress..."})
            try:
                from qa_agent.triage_runner import run_self_healing
                summary = await run_self_healing(results_json)
                await _broadcast_to_dashboard({
                    "event": "runner:healed",
                    "healed": summary.get("healed", 0),
                    "skipped": summary.get("unknown", 0) + summary.get("app_defects", 0),
                })
            except Exception as e:
                logger.error("Self-healing error: %s", e)
                await _broadcast_to_dashboard({"event": "runner:log", "line": f"[Heal] Error: {e}"})

        _test_run_status["state"] = "idle"

    except Exception as e:
        _test_run_status["state"] = "error"
        _test_run_status["error"] = str(e)
        await _broadcast_to_dashboard({"event": "runner:end", "exit_code": -1, "error": str(e)})


