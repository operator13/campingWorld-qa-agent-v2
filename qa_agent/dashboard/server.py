import json
import os
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
