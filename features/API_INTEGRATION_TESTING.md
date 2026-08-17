# Feature: API / Integration-Level Tests

> Generate and run API-level tests alongside UI E2E tests — faster feedback, broader coverage, and testing the contract between frontend and backend.

**Status:** PLANNED
**Priority:** Medium
**Depends on:** Core framework (Phases 0-4)

---

## The Problem

UI E2E tests are slow (browser startup, page loads, animations) and brittle (DOM changes). Many bugs live in the API layer — wrong response codes, missing fields, broken validation — and are cheaper to catch with direct HTTP calls. Currently the framework only generates browser-based tests.

## The Solution

Extend the Generator to produce **API test specs** alongside UI tests. API tests validate the backend contract (endpoints, payloads, status codes, schemas) while UI tests validate the user experience. Both run in the same pipeline.

---

## A. What API Tests Cover

| Layer | What's tested | How |
|-------|--------------|-----|
| **Contract** | Response shape matches expected schema (fields, types) | JSON Schema validation |
| **Status codes** | Correct 2xx/4xx/5xx for valid/invalid requests | Assert on `response.status` |
| **Validation** | Required fields, format rules, boundary values | Send malformed payloads |
| **Auth** | Protected endpoints reject unauthenticated requests | Call without token |
| **CRUD** | Create/Read/Update/Delete operations work end-to-end | Sequential API calls |
| **Error responses** | Error bodies have consistent structure and messages | Assert on error shape |

---

## B. Architecture

### API spec discovery

The Planner identifies API endpoints from:
1. **Network traffic** captured during UI test runs (Playwright `page.on('request')`)
2. **OpenAPI/Swagger spec** if available (config: `OPENAPI_SPEC_URL`)
3. **Acceptance criteria** that mention API behavior ("the endpoint should return...")

### Test generation

The Generator produces two types of output:
```
tests_generated/
  checkout.spec.ts          # UI test (existing)
  checkout.api.spec.ts      # API test (new)
```

API tests use Playwright's `request` API (built-in, no extra deps):
```typescript
import { test, expect } from '@playwright/test';

test.describe('Checkout API', () => {
  test('POST /api/checkout returns 200 with valid payload', async ({ request }) => {
    const response = await request.post('/api/checkout', {
      data: { email: 'test@example.com', items: [{ id: 1, qty: 1 }] }
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty('orderId');
  });
});
```

---

## C. Build Phases

### Phase API1 — Network capture + API test generation
| # | Task | Status |
|---|------|--------|
| 1 | Capture network requests during Executor UI runs via `page.on('request')` | TODO |
| 2 | Filter to API calls (exclude static assets, analytics, etc.) | TODO |
| 3 | Store captured endpoints in state: `api_endpoints` | TODO |
| 4 | Extend Generator to produce `.api.spec.ts` files from captured endpoints | TODO |
| 5 | Generator prompt update: API test generation rules and examples | TODO |

**Tests:**
- Unit: network capture extracts API endpoints from request log
- Unit: Generator produces valid API test files from endpoint data
- Contract: generated API specs compile with `npx playwright test --list`

**Done when:** A UI test run automatically discovers API endpoints and generates companion API tests.

### Phase API2 — OpenAPI spec integration
| # | Task | Status |
|---|------|--------|
| 1 | Fetch and parse OpenAPI/Swagger spec from configured URL | TODO |
| 2 | Generate API tests from OpenAPI operations (one test per endpoint) | TODO |
| 3 | Schema validation: assert response body matches OpenAPI schema | TODO |
| 4 | Negative tests: send payloads that violate the schema, expect 4xx | TODO |

**Done when:** If an OpenAPI spec is available, full contract tests are generated automatically.

### Phase API3 — API-specific triage + reporting
| # | Task | Status |
|---|------|--------|
| 1 | Triage rubric extension: API failure patterns (status code mismatch, schema drift, timeout) | TODO |
| 2 | API test results in Metrics DB with endpoint-level tracking | TODO |
| 3 | API coverage report: which endpoints are tested vs untested | TODO |

**Done when:** API failures are triaged correctly; coverage dashboard shows endpoint-level metrics.

---

## D. Assumptions

- API tests use Playwright's built-in `request` API — no Axios, no Supertest.
- API endpoints are discovered from network traffic or OpenAPI spec — not hardcoded.
- API tests run in the same `npx playwright test` invocation as UI tests.
- Auth tokens for API tests are obtained from the same login flow used by UI tests (`storageState`).

## E. Not in Scope

- GraphQL-specific testing (query/mutation validation)
- gRPC or WebSocket APIs (separate feature: WEBSOCKET_TESTING.md)
- Performance/load testing of APIs
- Contract testing between microservices (Pact-style)
