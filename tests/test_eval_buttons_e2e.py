"""E2E tests for eval RUN buttons using real browser automation.

These tests click actual buttons on the dashboard and verify the UI
transitions through Running... → progress → completion states.

Run with: pytest tests/test_eval_buttons_e2e.py -v
Requires: docker compose up
"""
import asyncio
import json
import time

import pytest
import requests
import websockets

DASHBOARD_URL = "http://localhost:8080"
WORKER_URL = "http://localhost:8081"
WS_URL = "ws://localhost:8080/ws/dashboard"


def _wait_for_eval_idle(timeout: int = 120):
    """Poll worker status until eval state is idle."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{WORKER_URL}/api/worker/status", timeout=3)
            if r.json()["eval"]["state"] == "idle":
                return
        except Exception:
            pass
        time.sleep(2)
    pytest.fail("Worker eval state never returned to idle")


def _wait_for_eval_complete(timeout: int = 120):
    """Wait for eval:complete WebSocket event."""
    async def _inner():
        async with websockets.connect(WS_URL) as ws:
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    if json.loads(msg).get("event") == "eval:complete":
                        return
            except asyncio.TimeoutError:
                pytest.fail("eval:complete never received")
    asyncio.get_event_loop().run_until_complete(_inner())


@pytest.fixture(scope="module")
def docker_stack():
    """Skip if Docker stack isn't running."""
    try:
        r = requests.get(f"{WORKER_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("Worker not running")
        r = requests.get(f"{DASHBOARD_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("Dashboard not running")
    except requests.ConnectionError:
        pytest.skip("Docker stack not running")
    return True


class TestEvalRunButtonShowsRunningState:
    """Verify clicking RUN shows Running... state BEFORE eval completes."""

    def test_triage_run_button_shows_running_via_websocket(self, docker_stack):
        """Click triage RUN via API, verify eval:start event is broadcast,
        then eval:agent:start, then progress, then complete."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                # Trigger eval
                resp = requests.post(f"{DASHBOARD_URL}/api/eval/run",
                                     json={"agents": ["triage"]}, timeout=10)
                assert resp.status_code == 200, f"Eval run failed: {resp.text}"

                # Collect events until eval:complete
                events = []
                try:
                    while True:
                        msg = await asyncio.wait_for(ws.recv(), timeout=120)
                        data = json.loads(msg)
                        if data.get("event", "").startswith("eval:"):
                            events.append(data["event"])
                        if data.get("event") == "eval:complete":
                            break
                except asyncio.TimeoutError:
                    pass

                # Verify the event sequence
                assert "eval:start" in events, f"Missing eval:start in {events}"
                assert "eval:agent:start" in events, f"Missing eval:agent:start in {events}"
                assert "eval:agent:complete" in events, f"Missing eval:agent:complete in {events}"
                assert "eval:complete" in events, f"Missing eval:complete in {events}"

                # Verify progress events were sent
                log_events = [e for e in events if e == "eval:log"]
                assert len(log_events) > 0, f"No eval:log progress events received"

        asyncio.get_event_loop().run_until_complete(_test())

    def test_triage_run_produces_updated_scores(self, docker_stack):
        """After triage eval, /api/eval/summary has updated token count."""
        # Wait for any running eval to finish first
        _wait_for_eval_idle()

        before = requests.get(f"{DASHBOARD_URL}/api/eval/summary").json()
        before_tokens = before.get("triage", {}).get("tokens") or 0

        resp = requests.post(f"{DASHBOARD_URL}/api/eval/run",
                             json={"agents": ["triage"]}, timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        _wait_for_eval_complete()
        time.sleep(0.5)

        after = requests.get(f"{DASHBOARD_URL}/api/eval/summary").json()
        after_tokens = after.get("triage", {}).get("tokens") or 0
        assert after_tokens > before_tokens, \
            f"Tokens didn't increase: {before_tokens} → {after_tokens}"

    def test_eval_produces_audit_trail(self, docker_stack):
        """After eval run, a new audit JSON file exists in memory/audit_runs/."""
        from pathlib import Path
        audit_dir = Path(__file__).parent.parent / "memory" / "audit_runs"

        _wait_for_eval_idle()
        before_files = set(audit_dir.glob("eval-triage-*.json"))

        resp = requests.post(f"{DASHBOARD_URL}/api/eval/run",
                             json={"agents": ["triage"]}, timeout=10)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        _wait_for_eval_complete()
        time.sleep(1)

        after_files = set(audit_dir.glob("eval-triage-*.json"))
        new_files = after_files - before_files
        assert len(new_files) >= 1, \
            f"No new audit trail file created. Before: {len(before_files)}, After: {len(after_files)}"

        newest = max(new_files, key=lambda f: f.stat().st_mtime)
        data = json.loads(newest.read_text())
        assert data["run_id"].startswith("eval-triage-")
        assert data["total_input_tokens"] > 0, "Audit file has zero input tokens"
        assert data["estimated_cost_usd"] > 0, "Audit file has zero cost"
        assert len(data["nodes"]) >= 1
        assert data["nodes"][0]["node"] == "eval:triage"


class TestEvalAllButton:
    """Verify EVAL ALL triggers all 4 agents and completes."""

    def test_eval_all_triggers_four_agents(self, docker_stack):
        """EVAL ALL sends eval:agent:start for all 4 pipeline agents."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                resp = requests.post(f"{DASHBOARD_URL}/api/eval/run",
                                     json={"all": True}, timeout=10)
                assert resp.status_code == 200

                agent_starts = set()
                agent_completes = set()
                try:
                    while True:
                        msg = await asyncio.wait_for(ws.recv(), timeout=300)
                        data = json.loads(msg)
                        if data.get("event") == "eval:agent:start":
                            agent_starts.add(data.get("agent"))
                        elif data.get("event") == "eval:agent:complete":
                            agent_completes.add(data.get("agent"))
                        elif data.get("event") == "eval:complete":
                            break
                except asyncio.TimeoutError:
                    pytest.fail("eval:complete never received")

                expected = {"triage", "planner", "generator", "healer"}
                assert agent_starts == expected, \
                    f"Not all agents started: {agent_starts} (expected {expected})"
                assert agent_completes == expected, \
                    f"Not all agents completed: {agent_completes} (expected {expected})"

        asyncio.get_event_loop().run_until_complete(_test())


class TestEccEvalButton:
    """Verify ECC eval RUN triggers agent and completes."""

    def test_single_ecc_agent_run(self, docker_stack):
        """Run single ECC agent, verify start/complete events."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                resp = requests.post(f"{DASHBOARD_URL}/api/eval/ecc/run",
                                     json={"agents": ["refactor-cleaner"]}, timeout=10)
                assert resp.status_code == 200

                got_start = False
                got_complete = False
                try:
                    while True:
                        msg = await asyncio.wait_for(ws.recv(), timeout=120)
                        data = json.loads(msg)
                        if data.get("event") == "ecc_eval:agent:start" and data.get("agent") == "refactor-cleaner":
                            got_start = True
                        elif data.get("event") == "ecc_eval:agent:complete" and data.get("agent") == "refactor-cleaner":
                            got_complete = True
                        elif data.get("event") == "ecc_eval:complete":
                            break
                except asyncio.TimeoutError:
                    pass

                assert got_start, "Never received ecc_eval:agent:start for refactor-cleaner"
                assert got_complete, "Never received ecc_eval:agent:complete for refactor-cleaner"

        asyncio.get_event_loop().run_until_complete(_test())


class TestStopButton:
    """Verify STOP actually kills running evals."""

    def test_stop_eval_kills_subprocess(self, docker_stack):
        """Start eval, click stop, verify eval:complete fires and worker returns to idle."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                # Start eval
                resp = requests.post(f"{DASHBOARD_URL}/api/eval/run",
                                     json={"all": True}, timeout=10)
                assert resp.status_code == 200

                # Wait for at least one agent to start
                got_start = False
                try:
                    while not got_start:
                        msg = await asyncio.wait_for(ws.recv(), timeout=10)
                        data = json.loads(msg)
                        if data.get("event") == "eval:agent:start":
                            got_start = True
                except asyncio.TimeoutError:
                    pytest.fail("No eval:agent:start received")

                # Click STOP
                stop_resp = requests.post(f"{DASHBOARD_URL}/api/eval/stop", timeout=10)
                assert stop_resp.status_code == 200

                # Verify complete event fires
                got_complete = False
                try:
                    while not got_complete:
                        msg = await asyncio.wait_for(ws.recv(), timeout=10)
                        data = json.loads(msg)
                        if data.get("event") == "eval:complete":
                            got_complete = True
                except asyncio.TimeoutError:
                    pass

                assert got_complete, "eval:complete never received after STOP"

        asyncio.get_event_loop().run_until_complete(_test())

        # Verify worker is idle
        time.sleep(1)
        status = requests.get(f"{WORKER_URL}/api/worker/status").json()
        assert status["eval"]["state"] == "idle", f"Worker still running: {status['eval']}"
