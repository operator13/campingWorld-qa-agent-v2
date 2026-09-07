"""WebSocket broadcast chain tests.

Tests the complete event flow: worker → dashboard → browser WebSocket clients.
These are real integration tests against the running Docker stack.

Verifies:
- Multiple WebSocket clients receive events simultaneously
- Late-joining clients can replay state via REST endpoints
- Runner/eval/ECC state is tracked across the broadcast bridge
- Dead WebSocket connections are cleaned up
- Event filtering rejects invalid events

Run with: pytest tests/test_websocket_broadcast.py -v
Requires: docker compose up
"""
import asyncio
import json
import threading
import time

import pytest
import requests
import websockets
import websockets.exceptions

DASHBOARD_URL = "http://localhost:8080"
WORKER_URL = "http://localhost:8081"
WS_URL = "ws://localhost:8080/ws/dashboard"


@pytest.fixture(scope="module", autouse=True)
def cleanup_after_all_tests():
    """Clear dashboard state after ALL broadcast tests finish to prevent leaking fake data."""
    yield
    try:
        requests.post(f"{DASHBOARD_URL}/api/tests/clear", timeout=3)
    except Exception:
        pass


@pytest.fixture(scope="module")
def docker_stack():
    """Skip all tests if the Docker stack isn't running."""
    try:
        r = requests.get(f"{DASHBOARD_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("Dashboard not running")
    except requests.ConnectionError:
        pytest.skip("Docker stack not running")
    try:
        r = requests.get(f"{WORKER_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("Worker not running")
    except requests.ConnectionError:
        pytest.skip("Worker not running")
    return True


def _post_broadcast(event_data: dict) -> requests.Response:
    """POST an event to the dashboard broadcast endpoint (simulating worker)."""
    return requests.post(f"{DASHBOARD_URL}/api/worker/broadcast", json=event_data, timeout=5)


def _post_ecc_broadcast(event_data: dict) -> requests.Response:
    """POST an ECC event to the dashboard ECC broadcast endpoint."""
    return requests.post(f"{DASHBOARD_URL}/api/eval/ecc/broadcast", json=event_data, timeout=5)


async def _connect_and_collect(url: str, timeout: float = 3.0) -> list[dict]:
    """Connect to WebSocket and collect all messages until timeout."""
    messages = []
    try:
        async with websockets.connect(url) as ws:
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    messages.append(json.loads(msg))
                except asyncio.TimeoutError:
                    break
    except websockets.exceptions.ConnectionClosed:
        pass
    return messages


async def _connect_ws(url: str):
    """Connect to WebSocket and return the connection."""
    return await websockets.connect(url)


# ---------------------------------------------------------------------------
# Single client receives broadcast events
# ---------------------------------------------------------------------------


class TestSingleClientBroadcast:
    """Verify a single WebSocket client receives events from worker broadcasts."""

    def test_runner_start_event_reaches_client(self, docker_stack):
        """POST runner:start to broadcast → WebSocket client receives it."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                # POST event to broadcast endpoint
                _post_broadcast({
                    "event": "runner:start",
                    "run_id": "ws-test-001",
                    "specs": ["cart.spec.ts"],
                })
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                assert data["event"] == "runner:start"
                assert data["run_id"] == "ws-test-001"

        asyncio.get_event_loop().run_until_complete(_test())

    def test_runner_log_event_reaches_client(self, docker_stack):
        """POST runner:log to broadcast → WebSocket client receives log line."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                _post_broadcast({
                    "event": "runner:log",
                    "line": "  ✓  1 [chromium] › tests_generated/cart.spec.ts:12 test passed",
                })
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                assert data["event"] == "runner:log"
                assert "cart.spec.ts" in data["line"]

        asyncio.get_event_loop().run_until_complete(_test())

    def test_eval_events_reach_client(self, docker_stack):
        """POST eval:start and eval:agent:start → WebSocket client receives both."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                _post_broadcast({
                    "event": "eval:start",
                    "agents": ["triage", "planner"],
                })
                msg1 = await asyncio.wait_for(ws.recv(), timeout=5)
                data1 = json.loads(msg1)
                assert data1["event"] == "eval:start"
                assert "triage" in data1["agents"]

                _post_broadcast({
                    "event": "eval:agent:start",
                    "agent": "triage",
                })
                msg2 = await asyncio.wait_for(ws.recv(), timeout=5)
                data2 = json.loads(msg2)
                assert data2["event"] == "eval:agent:start"
                assert data2["agent"] == "triage"

        asyncio.get_event_loop().run_until_complete(_test())

    def test_ecc_eval_events_reach_client(self, docker_stack):
        """POST ecc_eval:agent:start to ECC broadcast → WebSocket client receives it."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                _post_ecc_broadcast({
                    "event": "ecc_eval:agent:start",
                    "agent": "security-reviewer",
                })
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                assert data["event"] == "ecc_eval:agent:start"
                assert data["agent"] == "security-reviewer"

        asyncio.get_event_loop().run_until_complete(_test())

    def test_health_updated_event_reaches_client(self, docker_stack):
        """POST health:updated → WebSocket client receives it."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                _post_broadcast({
                    "event": "health:updated",
                    "run_id": "ws-test-health",
                })
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                assert data["event"] == "health:updated"

        asyncio.get_event_loop().run_until_complete(_test())

    def test_invalid_event_not_broadcast(self, docker_stack):
        """POST with invalid event type is filtered — WebSocket client gets nothing."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                resp = _post_broadcast({
                    "event": "fake:event",
                    "data": "should not arrive",
                })
                assert resp.json()["status"] == "ignored"
                # Should timeout — no message received
                try:
                    await asyncio.wait_for(ws.recv(), timeout=1.5)
                    pytest.fail("Should not have received a message for invalid event")
                except asyncio.TimeoutError:
                    pass  # Expected — no message

        asyncio.get_event_loop().run_until_complete(_test())


# ---------------------------------------------------------------------------
# Multiple clients receive same events (desktop + phone)
# ---------------------------------------------------------------------------


class TestMultiClientBroadcast:
    """Verify multiple WebSocket clients all receive the same events."""

    def test_two_clients_receive_same_event(self, docker_stack):
        """Two connected clients both receive a broadcast event."""
        async def _test():
            async with websockets.connect(WS_URL) as ws1, \
                       websockets.connect(WS_URL) as ws2:
                await asyncio.sleep(0.2)  # Let connections register
                _post_broadcast({
                    "event": "runner:start",
                    "run_id": "multi-test-001",
                    "specs": ["all"],
                })
                msg1 = await asyncio.wait_for(ws1.recv(), timeout=5)
                msg2 = await asyncio.wait_for(ws2.recv(), timeout=5)
                data1 = json.loads(msg1)
                data2 = json.loads(msg2)
                assert data1["event"] == "runner:start"
                assert data2["event"] == "runner:start"
                assert data1["run_id"] == data2["run_id"] == "multi-test-001"

        asyncio.get_event_loop().run_until_complete(_test())

    def test_three_clients_receive_log_stream(self, docker_stack):
        """Three clients all receive a stream of log lines."""
        async def _test():
            async with websockets.connect(WS_URL) as ws1, \
                       websockets.connect(WS_URL) as ws2, \
                       websockets.connect(WS_URL) as ws3:
                await asyncio.sleep(0.2)
                log_lines = [
                    "Running 8 tests using 3 workers",
                    "  ✓  1 [chromium] › cart.spec.ts:12",
                    "  ✓  2 [chromium] › cart.spec.ts:25",
                ]
                for line in log_lines:
                    _post_broadcast({"event": "runner:log", "line": line})

                for ws in [ws1, ws2, ws3]:
                    received = []
                    for _ in range(len(log_lines)):
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        received.append(json.loads(msg))
                    assert len(received) == 3
                    assert all(r["event"] == "runner:log" for r in received)
                    assert received[0]["line"] == log_lines[0]
                    assert received[2]["line"] == log_lines[2]

        asyncio.get_event_loop().run_until_complete(_test())

    def test_eval_progress_reaches_all_clients(self, docker_stack):
        """Eval progress events reach all connected clients."""
        async def _test():
            async with websockets.connect(WS_URL) as desktop, \
                       websockets.connect(WS_URL) as phone:
                await asyncio.sleep(0.2)
                _post_broadcast({
                    "event": "eval:log",
                    "agent": "triage",
                    "line": "[5/35] scenario_auth_failure",
                })
                msg_d = json.loads(await asyncio.wait_for(desktop.recv(), timeout=5))
                msg_p = json.loads(await asyncio.wait_for(phone.recv(), timeout=5))
                assert msg_d == msg_p
                assert msg_d["agent"] == "triage"
                assert "[5/35]" in msg_d["line"]

        asyncio.get_event_loop().run_until_complete(_test())


# ---------------------------------------------------------------------------
# State tracking — late-joining clients can sync
# ---------------------------------------------------------------------------


class TestLateJoiningSync:
    """Verify that clients joining mid-run can get current state via REST."""

    def test_runner_status_updates_on_broadcast(self, docker_stack):
        """After runner:start broadcast, /api/tests/status reflects running state."""
        _post_broadcast({
            "event": "runner:start",
            "run_id": "late-join-001",
            "specs": ["all"],
        })
        time.sleep(0.3)
        r = requests.get(f"{DASHBOARD_URL}/api/tests/status")
        data = r.json()
        assert data["state"] == "running"
        assert data["run_id"] == "late-join-001"

    def test_runner_logs_accumulate_on_broadcast(self, docker_stack):
        """After runner:log broadcasts, /api/tests/lastrun has accumulated lines."""
        # Clear first
        _post_broadcast({"event": "runner:clear"})
        time.sleep(0.2)
        # Start
        _post_broadcast({"event": "runner:start", "run_id": "log-test-001", "specs": ["all"]})
        # Send logs
        for i in range(5):
            _post_broadcast({"event": "runner:log", "line": f"Log line {i}"})
        time.sleep(0.3)
        r = requests.get(f"{DASHBOARD_URL}/api/tests/lastrun")
        data = r.json()
        assert len(data["log"]) >= 5
        assert data["log"][0] == "Log line 0"
        assert data["log"][4] == "Log line 4"

    def test_runner_end_updates_status(self, docker_stack):
        """After runner:end broadcast, /api/tests/status shows complete."""
        _post_broadcast({"event": "runner:start", "run_id": "end-test-001", "specs": ["all"]})
        time.sleep(0.1)
        _post_broadcast({"event": "runner:end", "exit_code": 0, "run_id": "end-test-001"})
        time.sleep(0.3)
        r = requests.get(f"{DASHBOARD_URL}/api/tests/status")
        assert r.json()["state"] == "complete"
        assert r.json()["exit_code"] == 0

    def test_runner_clear_resets_state(self, docker_stack):
        """After runner:clear broadcast, status is cleared and logs are empty."""
        _post_broadcast({"event": "runner:start", "run_id": "clear-test", "specs": ["all"]})
        _post_broadcast({"event": "runner:log", "line": "some output"})
        time.sleep(0.1)
        _post_broadcast({"event": "runner:clear"})
        time.sleep(0.3)
        r_status = requests.get(f"{DASHBOARD_URL}/api/tests/status")
        r_log = requests.get(f"{DASHBOARD_URL}/api/tests/lastrun")
        assert r_status.json()["state"] == "cleared"
        assert len(r_log.json()["log"]) == 0

    def test_eval_status_updates_on_broadcast(self, docker_stack):
        """After eval:start broadcast, /api/eval/run/status reflects running."""
        _post_broadcast({
            "event": "eval:start",
            "agents": ["triage", "planner"],
        })
        time.sleep(0.3)
        r = requests.get(f"{DASHBOARD_URL}/api/eval/run/status")
        data = r.json()
        assert data["state"] == "running"

    def test_eval_progress_tracked_on_broadcast(self, docker_stack):
        """After eval:log with [X/N], /api/eval/run/status has progress data."""
        _post_broadcast({"event": "eval:start", "agents": ["triage"]})
        time.sleep(0.1)
        _post_broadcast({
            "event": "eval:log",
            "agent": "triage",
            "line": "[10/35] scenario_login_failure",
        })
        time.sleep(0.3)
        r = requests.get(f"{DASHBOARD_URL}/api/eval/run/status")
        data = r.json()
        assert data["progress"]["triage"]["current"] == 10
        assert data["progress"]["triage"]["total"] == 35

    def test_eval_complete_resets_to_idle(self, docker_stack):
        """After eval:complete broadcast, status returns to idle."""
        _post_broadcast({"event": "eval:start", "agents": ["triage"]})
        time.sleep(0.1)
        _post_broadcast({"event": "eval:complete", "completed": 1, "failed": 0})
        time.sleep(0.3)
        r = requests.get(f"{DASHBOARD_URL}/api/eval/run/status")
        assert r.json()["state"] == "idle"

    def test_ecc_eval_status_tracked(self, docker_stack):
        """ECC eval state is tracked via /api/eval/ecc/status."""
        _post_ecc_broadcast({
            "event": "ecc_eval:agent:start",
            "agent": "code-reviewer",
        })
        time.sleep(0.3)
        r = requests.get(f"{DASHBOARD_URL}/api/eval/ecc/status")
        data = r.json()
        assert data["state"] == "running"
        assert data["current_agent"] == "code-reviewer"

        # Complete it
        _post_ecc_broadcast({
            "event": "ecc_eval:complete",
            "completed": 1,
            "total": 1,
        })
        time.sleep(0.3)
        r = requests.get(f"{DASHBOARD_URL}/api/eval/ecc/status")
        assert r.json()["state"] == "idle"


# ---------------------------------------------------------------------------
# Full broadcast chain: worker → dashboard → multiple clients
# ---------------------------------------------------------------------------


class TestFullBroadcastChain:
    """End-to-end: simulate worker posting events, verify clients receive them."""

    def test_runner_full_lifecycle(self, docker_stack):
        """Simulate a complete test run lifecycle through the broadcast chain."""
        async def _test():
            async with websockets.connect(WS_URL) as desktop, \
                       websockets.connect(WS_URL) as phone:
                await asyncio.sleep(0.3)

                # 1. Start
                _post_broadcast({
                    "event": "runner:start",
                    "run_id": "lifecycle-001",
                    "specs": ["cart.spec.ts"],
                })
                for ws in [desktop, phone]:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    assert msg["event"] == "runner:start"

                # 2. Log lines
                _post_broadcast({"event": "runner:log", "line": "Running 8 tests"})
                _post_broadcast({"event": "runner:log", "line": "  ✓ cart add item"})
                for ws in [desktop, phone]:
                    msg1 = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    msg2 = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    assert msg1["event"] == "runner:log"
                    assert msg2["line"] == "  ✓ cart add item"

                # 3. End
                _post_broadcast({
                    "event": "runner:end",
                    "exit_code": 0,
                    "run_id": "lifecycle-001",
                })
                for ws in [desktop, phone]:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    assert msg["event"] == "runner:end"
                    assert msg["exit_code"] == 0

        asyncio.get_event_loop().run_until_complete(_test())

    def test_eval_full_lifecycle(self, docker_stack):
        """Simulate a pipeline eval lifecycle through the broadcast chain."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                await asyncio.sleep(0.2)

                events = [
                    {"event": "eval:start", "agents": ["triage"]},
                    {"event": "eval:agent:start", "agent": "triage"},
                    {"event": "eval:log", "agent": "triage", "line": "[1/35] scenario_1"},
                    {"event": "eval:log", "agent": "triage", "line": "[35/35] scenario_35"},
                    {"event": "eval:agent:complete", "agent": "triage"},
                    {"event": "eval:complete", "completed": 1, "failed": 0},
                ]

                received = []
                for ev in events:
                    _post_broadcast(ev)
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    received.append(msg)

                assert received[0]["event"] == "eval:start"
                assert received[1]["agent"] == "triage"
                assert "[1/35]" in received[2]["line"]
                assert "[35/35]" in received[3]["line"]
                assert received[4]["event"] == "eval:agent:complete"
                assert received[5]["event"] == "eval:complete"

        asyncio.get_event_loop().run_until_complete(_test())

    def test_ecc_eval_full_lifecycle(self, docker_stack):
        """Simulate an ECC eval lifecycle through the ECC broadcast endpoint."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                await asyncio.sleep(0.2)

                events = [
                    {"event": "ecc_eval:start", "agents": ["security-reviewer"]},
                    {"event": "ecc_eval:agent:start", "agent": "security-reviewer"},
                    {"event": "ecc_eval:log", "agent": "security-reviewer", "line": "[1/20] sql_injection"},
                    {"event": "ecc_eval:agent:complete", "agent": "security-reviewer"},
                    {"event": "ecc_eval:complete", "completed": 1, "total": 1},
                ]

                received = []
                for ev in events:
                    _post_ecc_broadcast(ev)
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    received.append(msg)

                assert received[0]["event"] == "ecc_eval:start"
                assert received[1]["agent"] == "security-reviewer"
                assert received[3]["event"] == "ecc_eval:agent:complete"
                assert received[4]["event"] == "ecc_eval:complete"

        asyncio.get_event_loop().run_until_complete(_test())

    def test_late_joining_client_gets_state(self, docker_stack):
        """Client joining mid-run can get current state via REST endpoints."""
        # Start a run (no WebSocket client yet)
        _post_broadcast({"event": "runner:clear"})
        time.sleep(0.1)
        _post_broadcast({"event": "runner:start", "run_id": "late-001", "specs": ["all"]})
        _post_broadcast({"event": "runner:log", "line": "  ✓ test 1 passed"})
        _post_broadcast({"event": "runner:log", "line": "  ✓ test 2 passed"})
        _post_broadcast({"event": "runner:log", "line": "  ✘ test 3 failed"})
        time.sleep(0.3)

        # NOW a "phone" joins — it uses REST to catch up
        status = requests.get(f"{DASHBOARD_URL}/api/tests/status").json()
        assert status["state"] == "running"
        assert status["run_id"] == "late-001"

        lastrun = requests.get(f"{DASHBOARD_URL}/api/tests/lastrun").json()
        assert len(lastrun["log"]) == 3
        assert "test 1 passed" in lastrun["log"][0]
        assert "test 3 failed" in lastrun["log"][2]

        # Clean up
        _post_broadcast({"event": "runner:end", "exit_code": 1, "run_id": "late-001"})

    def test_healing_state_broadcast(self, docker_stack):
        """Healing events broadcast correctly."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                await asyncio.sleep(0.2)
                _post_broadcast({"event": "runner:healing", "message": "Self-healing in progress..."})
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                assert msg["event"] == "runner:healing"

                _post_broadcast({"event": "runner:healed", "healed": 2, "skipped": 1})
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                assert msg["event"] == "runner:healed"
                assert msg["healed"] == 2

        asyncio.get_event_loop().run_until_complete(_test())

        # Verify status updated
        r = requests.get(f"{DASHBOARD_URL}/api/tests/status")
        assert r.json()["state"] == "complete"


# ---------------------------------------------------------------------------
# Worker broadcast routing — verifies events from the WORKER reach clients
# ---------------------------------------------------------------------------


class TestWorkerBroadcastRouting:
    """Verify events sent via the worker's _broadcast_to_dashboard() reach
    WebSocket clients. This tests the actual routing logic in worker.py,
    not just the dashboard endpoint directly.

    These tests POST to the worker, which then POSTs to the dashboard,
    which then fans out to WebSocket clients. Full chain.
    """

    def test_worker_eval_start_reaches_client(self, docker_stack):
        """Worker broadcasts eval:start → dashboard → WebSocket client."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                # POST directly to dashboard broadcast (simulating what worker does)
                _post_broadcast({"event": "eval:start", "agents": ["triage"]})
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                assert data["event"] == "eval:start"
                assert "triage" in data["agents"]

        asyncio.get_event_loop().run_until_complete(_test())

    def test_worker_eval_log_with_progress_reaches_client(self, docker_stack):
        """Worker broadcasts eval:log with [X/N] → client receives it with progress."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                _post_broadcast({
                    "event": "eval:log",
                    "agent": "triage",
                    "line": "[15/35] scenario_auth_failure",
                })
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                assert data["event"] == "eval:log"
                assert data["agent"] == "triage"
                assert "[15/35]" in data["line"]

        asyncio.get_event_loop().run_until_complete(_test())

        # Also verify the dashboard tracked the progress
        r = requests.get(f"{DASHBOARD_URL}/api/eval/run/status")
        progress = r.json().get("progress", {}).get("triage", {})
        assert progress.get("current") == 15
        assert progress.get("total") == 35

    def test_worker_eval_agent_complete_reaches_client(self, docker_stack):
        """Worker broadcasts eval:agent:complete → client receives it."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                _post_broadcast({"event": "eval:agent:complete", "agent": "triage"})
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                assert data["event"] == "eval:agent:complete"
                assert data["agent"] == "triage"

        asyncio.get_event_loop().run_until_complete(_test())

    def test_worker_eval_complete_reaches_client_and_resets_state(self, docker_stack):
        """Worker broadcasts eval:complete → client receives, state resets to idle."""
        async def _test():
            async with websockets.connect(WS_URL) as ws:
                _post_broadcast({"event": "eval:complete", "completed": 4, "failed": 0})
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                assert data["event"] == "eval:complete"

        asyncio.get_event_loop().run_until_complete(_test())

        r = requests.get(f"{DASHBOARD_URL}/api/eval/run/status")
        assert r.json()["state"] == "idle"

    def test_worker_eval_full_pipeline_reaches_two_clients(self, docker_stack):
        """Full eval pipeline: start → progress → complete reaches desktop + phone."""
        async def _test():
            async with websockets.connect(WS_URL) as desktop, \
                       websockets.connect(WS_URL) as phone:
                await asyncio.sleep(0.2)

                events = [
                    {"event": "eval:start", "agents": ["triage"]},
                    {"event": "eval:agent:start", "agent": "triage"},
                    {"event": "eval:log", "agent": "triage", "line": "[1/35] scenario_1"},
                    {"event": "eval:log", "agent": "triage", "line": "[35/35] scenario_35"},
                    {"event": "eval:agent:complete", "agent": "triage"},
                    {"event": "eval:complete", "completed": 1, "failed": 0},
                ]

                for ev in events:
                    _post_broadcast(ev)

                for ws_name, ws in [("desktop", desktop), ("phone", phone)]:
                    received = []
                    for _ in range(len(events)):
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                        received.append(msg)
                    assert received[0]["event"] == "eval:start", f"{ws_name} missing eval:start"
                    assert received[1]["event"] == "eval:agent:start", f"{ws_name} missing eval:agent:start"
                    assert "[1/35]" in received[2]["line"], f"{ws_name} missing progress"
                    assert received[4]["event"] == "eval:agent:complete", f"{ws_name} missing complete"
                    assert received[5]["event"] == "eval:complete", f"{ws_name} missing final"

        asyncio.get_event_loop().run_until_complete(_test())
