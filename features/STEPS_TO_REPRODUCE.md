# Feature: Steps to Reproduce in Test Reports

> Add human-readable AND technical steps to reproduce to every test failure, attached to the Playwright HTML report so anyone — technical or non-technical — can understand what happened.

**Status:** PLANNED
**Priority:** High
**Depends on:** Playwright test suite, fixtures, Page Object Model

---

## The Problem

When a test fails, the Playwright HTML report shows:
- **Error message** — technical (e.g., `expect(locator).toBeVisible() failed`)
- **Test Steps** — Playwright internals (e.g., `Expect "toBeVisible" getByRole('main') — search.spec.ts:55`)
- **Screenshot** — visual state at failure
- **Code snippet** — the failing line

What's missing: **Steps to Reproduce** written so a non-technical person (QA manager, product owner, stakeholder) can understand what was tested and where it broke. Currently you need to read TypeScript code and Playwright locators to understand the failure.

---

## The Solution

Add a **dual-format "Steps to Reproduce"** attachment to every failed test in the Playwright HTML report:

### Human-Readable Steps (for non-tech folks)

```
Steps to Reproduce:
1. Open the Search page (campingworld.com/search?q=sleeping+bag)
2. Wait for the page to load and dismiss any popups
3. Verify the URL contains "sleeping bag" or "search"  ✓
4. Verify the main content area is visible  ✗ FAILED

Expected: Main content area should be visible on the page
Actual: Element not found within 10 seconds

Environment: Chromium, campingworld.com (live site)
```

### Technical Steps (for engineers)

```
Technical Steps:
1. page.goto('/search?q=sleeping%20bag', { waitUntil: 'domcontentloaded' })
2. dismissPopups(page) — cookie banner + email modal handling
3. expect(page).toHaveURL(/sleeping.bag|search/i)  ✓  (7ms)
4. expect(searchPage.mainContent).toBeVisible()  ✗  (10.0s timeout)
   Locator: page.getByRole('main')
   Error: element(s) not found

Page Object: SearchPage (page_objects/SearchPage.ts)
Spec File: search.spec.ts:55
```

### How They Appear in the Report

Both are attached as text files to the test result, appearing in the HTML report alongside the existing "Screenshots" and "Attachments" sections:

```
┌─────────────────────────────────────────────────────────┐
│  search for a different term shows new results          │
│  search.spec.ts:52                                      │
│  ✗ Run                                                  │
│                                                         │
│  ▸ Errors                                               │
│    Error: expect(locator).toBeVisible() failed          │
│                                                         │
│  ▸ Test Steps                                           │
│    ✓ Before Hooks (5.6s)                                │
│    ✓ Navigate to "/search?q=sleeping%20bag" (758ms)     │
│    ...                                                  │
│    ✗ Expect "toBeVisible" getByRole('main') (10.0s)     │
│                                                         │
│  ▸ Steps to Reproduce                        ← NEW     │
│    ┌─────────────────────────────────────────────────┐  │
│    │ Human-Readable:                                 │  │
│    │ 1. Open the Search page (searching for          │  │
│    │    "sleeping bag")                               │  │
│    │ 2. Wait for page to load, dismiss popups        │  │
│    │ 3. Verify URL contains search term  ✓           │  │
│    │ 4. Verify main content area visible  ✗ FAILED   │  │
│    │                                                 │  │
│    │ Expected: Main content visible                  │  │
│    │ Actual: Not found within 10s                    │  │
│    └─────────────────────────────────────────────────┘  │
│    ┌─────────────────────────────────────────────────┐  │
│    │ Technical:                                      │  │
│    │ 1. page.goto('/search?q=sleeping%20bag')        │  │
│    │ 2. dismissPopups(page)                          │  │
│    │ 3. expect(page).toHaveURL(...)  ✓  (7ms)       │  │
│    │ 4. expect(mainContent).toBeVisible()  ✗ (10s)  │  │
│    │    Locator: page.getByRole('main')              │  │
│    └─────────────────────────────────────────────────┘  │
│                                                         │
│  ▸ Screenshots                                          │
│    📷 screenshot                                        │
│                                                         │
│  ▸ Attachments                                          │
│    📎 error-context                                     │
│    📎 steps-to-reproduce          ← NEW                 │
│    📎 steps-to-reproduce-technical ← NEW                │
└─────────────────────────────────────────────────────────┘
```

---

## Architecture

### How It Works

Playwright supports custom attachments via `testInfo.attach()` in `afterEach` hooks. When a test fails, we:

1. **Extract the test steps** from `testInfo.steps` (Playwright tracks every action)
2. **Map technical steps to human language** using a translation layer
3. **Attach both versions** as text files to the test result
4. **HTML report renders them** automatically in the Attachments section

### Implementation in fixtures.ts

```typescript
import { test as base, type Page, type TestInfo } from '@playwright/test';

// Step translator: technical Playwright actions → human language
const STEP_TRANSLATIONS: Record<string, (step: any) => string> = {
  'page.goto': (s) => `Open the page (${s.params?.url || 'unknown URL'})`,
  'expect.toBeVisible': (s) => `Verify "${s.params?.expression || 'element'}" is visible on the page`,
  'expect.toHaveURL': (s) => `Verify the page URL matches the expected pattern`,
  'expect.toHaveText': (s) => `Verify the text content matches expected value`,
  'expect.toBeEnabled': (s) => `Verify the element is enabled and clickable`,
  'expect.toHaveCount': (s) => `Verify the expected number of elements are present`,
  'locator.click': (s) => `Click on "${s.params?.expression || 'element'}"`,
  'locator.fill': (s) => `Type "${s.params?.value || '...'}" into the field`,
  'locator.scrollIntoViewIfNeeded': (s) => `Scroll to make the element visible`,
  'locator.waitFor': (s) => `Wait for the element to appear on the page`,
  'page.keyboard.press': (s) => `Press the "${s.params?.key || '...'}" key`,
};

function generateHumanSteps(testInfo: TestInfo): string {
  // ... translate steps to human language
}

function generateTechnicalSteps(testInfo: TestInfo): string {
  // ... format steps with locators, timings, pass/fail
}
```

### afterEach Hook

```typescript
test.afterEach(async ({}, testInfo) => {
  if (testInfo.status !== 'passed') {
    // Generate and attach human-readable steps
    const humanSteps = generateHumanSteps(testInfo);
    await testInfo.attach('steps-to-reproduce', {
      body: humanSteps,
      contentType: 'text/plain',
    });

    // Generate and attach technical steps
    const technicalSteps = generateTechnicalSteps(testInfo);
    await testInfo.attach('steps-to-reproduce-technical', {
      body: technicalSteps,
      contentType: 'text/plain',
    });
  }
});
```

---

## Step Translation Rules

### Human-Readable Mapping

| Playwright Action | Human Language |
|------------------|---------------|
| `page.goto('/search?q=tent')` | "Open the Search page (searching for 'tent')" |
| `page.goto('/cart')` | "Open the Shopping Cart page" |
| `page.goto('/sign-in')` | "Open the Sign In page" |
| `expect(locator).toBeVisible()` | "Verify [element name] is visible on the page" |
| `expect(locator).toBeEnabled()` | "Verify [element name] is enabled and clickable" |
| `expect(page).toHaveURL(...)` | "Verify the page URL matches the expected pattern" |
| `expect(count).toBeGreaterThan(0)` | "Verify at least one [element] is present" |
| `locator.click()` | "Click on [element name]" |
| `locator.fill('value')` | "Type 'value' into the [field name]" |
| `locator.scrollIntoViewIfNeeded()` | "Scroll down to make [element] visible" |
| `dismissPopups()` | "Wait for page to load and dismiss any popups" |
| `locator.waitFor()` | "Wait for [element] to appear on the page" |

### Element Name Extraction

Derive human-readable element names from locators:

| Locator | Human Name |
|---------|-----------|
| `getByRole('button', { name: 'Add to Cart' })` | "the Add to Cart button" |
| `getByRole('main')` | "the main content area" |
| `getByTestId('checkout-btn')` | "the checkout button" |
| `getByText('Sign In')` | "the Sign In text" |
| `getByLabel('Email')` | "the Email field" |
| `page.locator('.product-card')` | "product card element" |

### URL to Page Name Mapping

| URL Pattern | Page Name |
|-------------|----------|
| `/search?q=*` | "Search page (searching for '[query]')" |
| `/cart` | "Shopping Cart page" |
| `/checkout` | "Checkout page" |
| `/sign-in` or `/account` | "Sign In page" |
| `/register` | "Registration page" |
| `/store-locator` | "Store Locator page" |
| `*.html` | "Product page ([product name])" |
| `/` or `/shop` | "Homepage" |
| `/rv-parts` | "RV Parts page" |
| `/good-sam` | "Good Sam page" |

### Pass/Fail Indicators

- Steps that passed: `✓` suffix
- Step that failed: `✗ FAILED` suffix
- Steps after failure: not shown (test stopped)

### Failure Context

After the steps, include:

```
Expected: [what should have happened]
Actual: [what actually happened]
Environment: [browser], [site URL]
Duration: [total test time]
```

---

## Files to Modify

| File | Change |
|------|--------|
| `tests_generated/fixtures.ts` | Add `afterEach` hook with step generation + attachment |

### No New Files Needed

Everything lives in the existing `fixtures.ts` — it already provides the custom `test` export used by all 14 spec files. Adding the `afterEach` hook here means all tests automatically get steps to reproduce on failure.

---

## Build Phases

### Phase SR1 — Human-Readable Steps (~0.5 day)

| # | Task |
|---|------|
| 1 | Add `afterEach` hook in `fixtures.ts` that fires on test failure |
| 2 | Build step translator: Playwright actions → human language |
| 3 | Build URL → page name mapper for campingworld.com routes |
| 4 | Build locator → element name extractor (getByRole, getByTestId, etc.) |
| 5 | Attach human-readable steps as `steps-to-reproduce` text attachment |
| 6 | Include Expected/Actual/Environment footer |

### Phase SR2 — Technical Steps (~0.5 day)

| # | Task |
|---|------|
| 1 | Format technical steps with exact locators, timings, pass/fail status |
| 2 | Include page object file reference and spec file line number |
| 3 | Attach as `steps-to-reproduce-technical` text attachment |
| 4 | Include DOM snapshot reference if available |

### Phase SR3 — Testing + Polish (~0.5 day)

| # | Task |
|---|------|
| 1 | Run full test suite — verify attachments appear in HTML reports |
| 2 | Intentionally fail a test — verify both step formats are correct |
| 3 | Verify attachments render properly in Playwright HTML report |
| 4 | Verify steps are readable by non-technical audience (review with stakeholder) |
| 5 | Test across all 14 spec files — ensure no spec breaks |

---

## Future: Dashboard Integration

Once steps to reproduce are in the Playwright JSON results, they can be surfaced on the dashboard:

- **Human Review Notifications panel** — show human-readable steps alongside the failure
- **Run History** — click a failed test to see steps to reproduce
- **Triage reports** — include steps in the enriched triage report

This is not in scope for Phase 1 — dashboard integration would be a separate spec.

---

## Success Criteria

1. Every failed test has a `steps-to-reproduce` attachment in the HTML report
2. Human-readable steps are understandable by non-technical users
3. Technical steps include exact locators, timings, and pass/fail status
4. The failing step is clearly marked with `✗ FAILED`
5. Expected vs Actual is included at the bottom
6. No test execution performance impact (steps generated only on failure)
7. Works across all 14 spec files without per-spec changes
8. Attachments render properly in the Playwright HTML report viewer
