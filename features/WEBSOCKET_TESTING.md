# Feature: WebSocket Testing

> Test real-time WebSocket features (live updates, chat, notifications) using Playwright's `page.on('websocket')` — for apps that use them.

**Status:** PLANNED
**Priority:** Low (only relevant for apps with WebSocket features)
**Depends on:** Core framework (Phases 0-4)

---

## The Problem

Apps with real-time features (chat, live dashboards, collaborative editing, notifications) use WebSockets. The current framework only tests HTTP request/response flows. WebSocket bugs — dropped connections, missing messages, out-of-order updates — are invisible.

## The Solution

Extend the Executor to intercept, assert on, and simulate WebSocket traffic using Playwright's built-in WebSocket API.

---

## A. What WebSocket Tests Cover

| Scenario | How it's tested |
|----------|----------------|
| **Connection established** | Assert WebSocket opens on page load |
| **Message received** | Wait for specific message content/shape |
| **Message sent** | Trigger a UI action and assert the outbound WS message |
| **Reconnection** | Simulate disconnect, verify auto-reconnect |
| **Message ordering** | Verify messages arrive in expected sequence |
| **Error handling** | Close the socket server-side, verify UI shows error state |

### Playwright WebSocket API

```typescript
page.on('websocket', (ws) => {
  ws.on('framereceived', (frame) => {
    console.log('Received:', frame.payload);
  });
  ws.on('framesent', (frame) => {
    console.log('Sent:', frame.payload);
  });
  ws.on('close', () => {
    console.log('WebSocket closed');
  });
});
```

---

## B. Architecture

### WebSocket capture in Executor

The Executor already runs Playwright against the live app. WebSocket interception is added as a listener:

1. Attach `page.on('websocket')` before navigating
2. Collect all WS frames during the test
3. Include WS traffic in `RunResult` for Triage analysis

### Test generation

The Generator produces WebSocket-aware tests when the plan includes real-time features:

```typescript
test('chat message appears in real-time', async ({ page }) => {
  const wsPromise = page.waitForEvent('websocket');
  await page.goto('/chat');
  const ws = await wsPromise;

  const messagePromise = new Promise(resolve => {
    ws.on('framereceived', frame => {
      const data = JSON.parse(frame.payload);
      if (data.type === 'message') resolve(data);
    });
  });

  await page.getByRole('textbox').fill('Hello');
  await page.getByRole('button', { name: 'Send' }).click();

  const received = await messagePromise;
  expect(received.text).toBe('Hello');
});
```

---

## C. Build Phases

### Phase WS1 — WebSocket capture + basic assertions
| # | Task | Status |
|---|------|--------|
| 1 | WebSocket frame capture in Executor via `page.on('websocket')` | TODO |
| 2 | Include WS traffic summary in `RunResult` | TODO |
| 3 | Generator: produce WS-aware tests for routes with real-time features | TODO |
| 4 | Prompt update: WS test patterns and examples for the Generator | TODO |

**Tests:**
- Unit: WS frame capture collects sent/received frames
- Unit: Generator produces valid WS test code
- Integration: WS test against a sample chat app passes

**Done when:** Routes with WebSocket features get tests that assert on WS messages.

### Phase WS2 — Resilience testing
| # | Task | Status |
|---|------|--------|
| 1 | Simulate WS disconnect via `ws.close()` | TODO |
| 2 | Assert reconnection behavior | TODO |
| 3 | Test message ordering under reconnection | TODO |
| 4 | Triage rubric extension: WS-specific failure patterns | TODO |

**Done when:** WebSocket resilience scenarios (disconnect, reconnect, ordering) are tested.

---

## D. Assumptions

- Only for web apps that use WebSockets — feature is opt-in via config.
- Uses Playwright's built-in WebSocket API — no external tools.
- WebSocket URLs are discovered from network traffic during test runs.
- The app's WS server must be running and accessible from the test environment.

## E. Not in Scope

- Server-Sent Events (SSE) testing
- gRPC streaming
- WebSocket load testing (concurrent connections)
- WebSocket security testing (origin validation, auth)
