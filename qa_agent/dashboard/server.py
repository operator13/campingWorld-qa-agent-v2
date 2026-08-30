import asyncio
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Directory resolution
# ---------------------------------------------------------------------------

DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).resolve().parent.parent.parent))
HEALTH_DIR = Path(DATA_DIR) / "health-reports"
EVAL_DIR = Path(DATA_DIR) / "qa_agent" / "eval" / "reports"
AUDIT_DIR = Path(DATA_DIR) / "memory" / "audit_runs"

STATIC_DIR = Path(__file__).resolve().parent / "static"

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="QA Command Center")

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
    # Prefer the latest full run (all domains) over a partial run
    for f in reversed(files):
        data = _read_json(f)
        if data and isinstance(data, dict):
            domains = data.get("domains", [])
            if len(domains) >= 10:  # full run has 14 domains, partial has fewer
                return JSONResponse(content=data)
    # Fallback to most recent if no full run found
    data = _read_json(files[-1])
    return JSONResponse(content=data or {})


@app.get("/api/health/history")
async def health_history() -> JSONResponse:
    files = _sorted_json_files(HEALTH_DIR)
    recent = files[-20:]
    results = []
    for f in recent:
        data = _read_json(f)
        if not data or not isinstance(data, dict):
            continue
        results.append(
            {
                "run_id": data.get("run_id"),
                "timestamp": data.get("timestamp"),
                "overall_score": data.get("overall_score"),
                "overall_status": data.get("overall_status"),
                "total_passed": data.get("total_passed"),
                "total_failed": data.get("total_failed"),
                "total_tests": data.get("total_tests"),
            }
        )
    return JSONResponse(content=results)


# ---------------------------------------------------------------------------
# Eval endpoints
# ---------------------------------------------------------------------------


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

        if agent == "generator":
            score_obj = data.get("locator_quality", {})
        else:
            key = f"{agent}_accuracy"
            score_obj = data.get(key, {})

        score = score_obj.get("score") if isinstance(score_obj, dict) else None
        passed = data.get("passed")
        summary[agent] = {"score": score, "passed": passed, "tokens": None, "cost": None}

    # Enrich with per-agent token/cost from latest audit run with real data
    audit_files = _sorted_json_files(AUDIT_DIR)
    for af in reversed(audit_files):
        audit_data = _read_json(af)
        if not audit_data or not isinstance(audit_data, dict):
            continue
        # Skip runs with no real token data
        if not audit_data.get("total_input_tokens"):
            continue
        nodes = audit_data.get("nodes", [])
        if isinstance(nodes, list):
            for node in nodes:
                name = node.get("node", "")
                inp = node.get("input_tokens") or 0
                out = node.get("output_tokens") or 0
                cost = node.get("cost_usd") or 0.0
                if name in summary and (inp + out) > 0:
                    summary[name]["tokens"] = inp + out
                    summary[name]["cost"] = round(cost, 4)
        break  # Only use the latest run with real data

    return JSONResponse(content=summary)


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


@app.post("/api/tests/run")
async def run_tests(body: dict = {}):
    global _test_process, _test_run_status
    if _test_process and _test_process.returncode is None:
        return JSONResponse({"error": "Tests already running"}, status_code=409)

    specs = body.get("specs", [])  # list of spec filenames, empty = all
    workers = body.get("workers", 3)
    retries = body.get("retries", 0)
    heal = body.get("heal", False)

    run_id = datetime.now(tz=timezone.utc).strftime("%m_%d_%Y_%H-%M-%S")
    _test_run_status = {"state": "running", "run_id": run_id, "started_at": datetime.now(tz=timezone.utc).isoformat()}

    asyncio.create_task(_execute_test_run(specs, workers, retries, heal, run_id))
    return JSONResponse({"status": "started", "run_id": run_id})


@app.get("/api/tests/status")
async def test_status():
    return JSONResponse(content=_test_run_status)


@app.post("/api/tests/clear")
async def clear_tests():
    global _test_run_status
    _test_run_status = {"state": "cleared", "run_id": None, "started_at": None}
    await broadcast_to_dashboard(json.dumps({"event": "runner:clear"}))
    return JSONResponse({"status": "cleared"})


@app.post("/api/tests/stop")
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
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            await broadcast_to_dashboard(message)
    except WebSocketDisconnect:
        pass
