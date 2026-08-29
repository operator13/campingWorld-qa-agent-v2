# Feature: Camping World DOM Orchestrator

> A standalone agent that uses Playwright MCP to crawl campingworld.com, snapshot page DOMs, and auto-generate TypeScript Page Object Model files and Playwright test specs — covering the full site without Figma or Jira input.

**Status:** IN PROGRESS (Phase O1 complete — 15%)
**Priority:** High
**Depends on:** Core framework (Phases 0-4), existing Playwright MCP client (`qa_agent/mcp/playwright_client.py`)

---

## The Problem

The existing LangGraph pipeline requires Figma designs or Jira tickets as input to generate tests. Camping World's full production site (campingworld.com) has dozens of page types and hundreds of interactive elements that have no Figma frames or Jira stories. There is no automated way to bootstrap comprehensive test coverage from the live site itself.

## The Solution

A lightweight orchestrator (standalone async Python module, not a LangGraph graph) that:
1. Navigates campingworld.com pages using Playwright MCP tools
2. Snapshots each page's DOM structure via `browser_snapshot`
3. Feeds DOM snapshots to an LLM to generate Page Object classes
4. Feeds POMs + page context to an LLM to generate test specs
5. Writes output in the exact same format the existing Executor expects (`page_objects/` and `tests_generated/`)

The orchestrator is organized as a **site map** of page types, each processed independently. It runs incrementally — you can target one page type or the full site.

---

## Overall Progress: 15%

| Phase | Description | Status | % |
|-------|-------------|--------|---|
| O1 | Foundation — crawler, site map, popup handler | **DONE** | 15% |
| O2 | POM Generation — DOM→TypeScript page objects | PENDING | 15→35% |
| O3 | Test Generation — POM→Playwright test specs | PENDING | 35→55% |
| O4 | Full Site Coverage — all 16 page types | PENDING | 55→75% |
| O5 | CLI + Orchestration Loop — wire it all together | PENDING | 75→90% |
| O6 | Hardening — edge cases, memory, responsive | PENDING | 90→100% |

---

## A. Architecture

```
┌─────────────────┐
│   Site Map       │  (declarative config of all page types + URLs)
└────────┬────────┘
         │
         ▼
┌───────────────────────┐
│  Page Crawler         │  Playwright MCP: navigate → dismiss popups → snapshot
└───────────┬───────────┘
            │  DOM snapshot (accessibility tree)
            ▼
┌───────────────────────┐
│  POM Generator        │  LLM (Sonnet): DOM → TypeScript page object class
└───────────┬───────────┘
            │  POM source code
            ▼
┌───────────────────────┐
│  Test Generator       │  LLM (Sonnet): POM + context → Playwright test spec
└───────────┬───────────┘
            │  Test file source code
            ▼
┌───────────────────────┐
│  File Writer          │  Writes to page_objects/ + tests_generated/
└───────────────────────┘
```

### Key Design Decisions

1. **Standalone module, not a graph node.** The orchestrator lives in `qa_agent/orchestrator/` and is invoked via `qa-agent crawl`. It does not participate in the LangGraph pipeline.

2. **Playwright MCP for DOM access.** Uses the existing `qa_agent/mcp/playwright_client.py` to connect to the Playwright MCP server. The MCP tools provide `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_find`, etc.

3. **Same output format as Generator.** Writes to `page_objects/` and `tests_generated/` using the exact same TypeScript conventions defined in `qa_agent/prompts/GENERATOR.md`: `getByRole()` > `getByTestId()` > `getByText()` locator priority, one class per route, `test.describe()` blocks importing page objects.

4. **Site map is declarative.** A Python dict defines every page type, its URL pattern, prerequisites, and auth requirements. Easy to add pages incrementally.

5. **Handles dynamic content.** For pages that require interaction to reach (search results, PDPs, cart with items), the crawler executes prerequisite actions via `browser_click`, `browser_fill_form`, etc. before snapshotting.

---

## B. Playwright MCP Tools Used

| Step | MCP Tool | Purpose |
|------|----------|---------|
| Navigate | `browser_navigate` | Load target URL |
| Dismiss popups | `browser_snapshot` + `browser_click` | Detect/close cookie banners, promo modals |
| Interact | `browser_click`, `browser_fill_form`, `browser_type` | Search, add to cart, fill forms |
| Capture DOM | `browser_snapshot` | Get accessibility tree |
| Find elements | `browser_find` | Locate specific elements by text/role |
| Wait | `browser_wait_for` | SPA transitions, lazy-loaded content |
| Responsive | `browser_resize` | Desktop (1280x720) vs mobile (375x812) |
| Screenshot | `browser_take_screenshot` | Visual evidence for debugging |
| Keyboard | `browser_press_key` | Escape to close modals, Tab for a11y |
| Dialogs | `browser_handle_dialog` | Alert/confirm dialogs during auth |

---

## C. Phase O1 — Foundation (0% → 15%)

**Goal:** Crawler skeleton + site map + popup handler. Prove we can navigate and snapshot one page.

| # | File | Contents |
|---|------|----------|
| 1 | `qa_agent/orchestrator/__init__.py` | Package init |
| 2 | `qa_agent/orchestrator/site_map.py` | `SITE_MAP` dict — all 16 page types with URL, auth, prerequisites, priority |
| 3 | `qa_agent/orchestrator/crawler.py` | `PageCrawler` — navigate, dismiss popups, snapshot, return `PageSnapshot` |
| 4 | `qa_agent/orchestrator/models.py` | Pydantic: `PageConfig`, `PageSnapshot`, `CrawlResult`, `GeneratedOutput` |
| 5 | `qa_agent/orchestrator/popup_handler.py` | Detect/dismiss cookie consent, promo modals, newsletter popups |
| 6 | `qa_agent/prompts/DOM_TO_POM.md` | System prompt: DOM accessibility tree → TypeScript POM class |
| 7 | `qa_agent/prompts/POM_TO_TESTS.md` | System prompt: POM + context → Playwright test spec |

**PageConfig model:**
```python
class PageConfig(BaseModel):
    name: str
    url: str
    route: str
    requires_auth: bool = False
    priority: int = 1  # 1=highest
    regions: list[str] = []
    prerequisites: list[dict] = []  # actions before snapshot
    dynamic_url: bool = False
    sample_urls: list[str] = []
```

**Crawler core logic:**
```python
class PageCrawler:
    async def crawl_page(self, config: PageConfig) -> PageSnapshot:
        # 1. Navigate to URL
        # 2. Wait for page load
        # 3. Dismiss popups (cookie, promo, newsletter)
        # 4. Execute prerequisites (hover, click, fill)
        # 5. Snapshot DOM (accessibility tree)
        # 6. Screenshot for reference
        return PageSnapshot(...)
```

**Exit gate:** `qa-agent crawl --page homepage --dry` navigates to campingworld.com, dismisses popups, prints DOM snapshot.

---

## D. Phase O2 — POM Generation (15% → 35%)

**Goal:** DOM snapshot → TypeScript Page Object class. Cover homepage, global nav, search.

| # | File | Contents |
|---|------|----------|
| 1 | `qa_agent/orchestrator/pom_generator.py` | `POMGenerator` — calls LLM with DOM_TO_POM.md prompt, returns POM source |
| 2 | `qa_agent/orchestrator/pom_validator.py` | Validates: has `export class`, resilient locators, `navigate()`, no CSS selectors, no `expect()` |

**POM output format (matches existing Generator convention):**
```typescript
import { type Page, type Locator } from '@playwright/test';

export class HomepagePage {
  readonly page: Page;
  readonly heroBanner: Locator;
  readonly searchInput: Locator;
  readonly cartIcon: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heroBanner = page.getByRole('img', { name: /hero/i });
    this.searchInput = page.getByRole('searchbox');
    this.cartIcon = page.getByRole('link', { name: /cart/i });
  }

  async navigate() { await this.page.goto('/'); }
  async search(query: string) {
    await this.searchInput.fill(query);
    await this.searchInput.press('Enter');
  }
}
```

**Locator priority:** `getByRole()` > `getByTestId()` > `getByText()` > `getByLabel()` — NEVER CSS selectors.

**POM validation rules:**
1. Contains `export class` statement
2. Constructor accepts `page: Page`
3. All locators use `getByRole`, `getByTestId`, `getByText`, or `getByLabel`
4. Has a `navigate()` method
5. Imports from `@playwright/test`
6. No test assertions (`expect(`) in page object code

**Pages covered:** Homepage, Global Navigation, Search Results.

**Exit gate:** Valid POM files for 3 page types, all pass `pom_validator`.

---

## E. Phase O3 — Test Generation (35% → 55%)

**Goal:** POM + page context → Playwright test spec. Add PLP and PDP coverage.

| # | File | Contents |
|---|------|----------|
| 1 | `qa_agent/orchestrator/test_generator.py` | `TestGenerator` — calls LLM with POM_TO_TESTS.md, returns test spec |
| 2 | `qa_agent/orchestrator/test_validator.py` | Validates: imports POM, `test.describe()`, `beforeEach`, web-first assertions |
| 3 | `qa_agent/orchestrator/scenario_templates.py` | Per-page-type test scenario lists |

**Test output format:**
```typescript
import { test, expect } from '@playwright/test';
import { HomepagePage } from '../page_objects/HomepagePage';

test.describe('Homepage', () => {
  let homepage: HomepagePage;
  test.beforeEach(async ({ page }) => {
    homepage = new HomepagePage(page);
    await homepage.navigate();
  });

  test('hero banner is visible', async ({ page }) => {
    await expect(homepage.heroBanner).toBeVisible();
  });

  test('search bar accepts input and submits', async ({ page }) => {
    await homepage.search('tent');
    await expect(page).toHaveURL(/search/);
  });
});
```

**Scenario templates (per page type):**

| Page Type | Example Scenarios |
|-----------|-------------------|
| Homepage | Hero banner visible, nav links clickable, search works, featured products display, footer present |
| Search Results | Results display, no-results message, filters work, sort changes order, pagination, click→PDP |
| PLP | Breadcrumb accurate, product cards with image/name/price, filter by price/brand, sort, pagination |
| PDP | Title/price visible, image gallery, add-to-cart clickable, quantity selector, reviews, related products |
| Cart | Items displayed, quantity update, remove item, subtotal, proceed to checkout, empty state |
| Checkout | Form fields render, validation errors, order summary correct, NO real submission |
| Sign In | Email/password fields, invalid login error, register link, forgot password |
| Account | Dashboard renders, order history, account settings (auth required) |
| Store Locator | Zip search, results with address/phone, map visible, store detail |
| RV Listings | Search results, filter by type/price/year, listing cards, click→detail |
| Good Sam | Membership tiers, sign-up CTA |
| Financing | Calculator or application form |
| Footer | All links present, privacy/terms navigate, social links |

**Pages added:** Product Listing Page (PLP), Product Detail Page (PDP).

**Exit gate:** Valid POM + test files for 5 page types, all pass validators.

---

## F. Phase O4 — Full Site Coverage (55% → 75%)

**Goal:** Cover all remaining page types with handlers for auth, cart state, and dynamic URLs.

| # | File | Contents |
|---|------|----------|
| 1 | `qa_agent/orchestrator/auth_handler.py` | Login via `browser_fill_form`, session reuse, auth-redirect detection |
| 2 | `qa_agent/orchestrator/cart_handler.py` | Add item to cart before snapshotting cart/checkout |
| 3 | `qa_agent/orchestrator/dynamic_page_resolver.py` | Discover real product/store/RV URLs by crawling listing pages |

**All 16 page types:**

| Page Type | Route | POM Class | Auth? | Prerequisites |
|-----------|-------|-----------|-------|---------------|
| Homepage | `/` | `HomepagePage` | No | None |
| Global Nav | `/` (nav) | `GlobalNavPage` | No | Hover on nav |
| Search Results | `/search?q=...` | `SearchResultsPage` | No | Type query |
| Product Listing | `/rv-parts/...` | `ProductListingPage` | No | Navigate to category |
| Product Detail | `/product/...` | `ProductDetailPage` | No | Resolve dynamic URL |
| Shopping Cart | `/cart` | `CartPage` | No | Add item first |
| Checkout | `/checkout` | `CheckoutPage` | Mixed | Item in cart |
| Sign In | `/sign-in` | `SignInPage` | No | None |
| Registration | `/register` | `RegisterPage` | No | None |
| Account Dashboard | `/account` | `AccountPage` | Yes | Login first |
| Store Locator | `/store-locator` | `StoreLocatorPage` | No | None |
| RV Listings | `/rvs-for-sale` | `RvListingsPage` | No | None |
| RV Detail | `/rvs-for-sale/...` | `RvDetailPage` | No | Resolve dynamic URL |
| Good Sam | `/good-sam` | `GoodSamPage` | No | None |
| Financing | `/financing` | `FinancingPage` | No | None |
| Footer / Legal | `/privacy-policy` etc. | `FooterPage` | No | None |

**Checkout safety:** Tests stop at form validation — NO real order submission.

**Exit gate:** POM + test files for all 16 page types.

---

## G. Phase O5 — CLI + Orchestration Loop (75% → 90%)

**Goal:** Wire everything together with CLI, progress tracking, and file writing.

| # | File | Contents |
|---|------|----------|
| 1 | `qa_agent/orchestrator/orchestrator.py` | Main `Orchestrator` — iterates site map, calls crawler→POM→tests→writer |
| 2 | `qa_agent/orchestrator/file_writer.py` | Writes to `page_objects/` + `tests_generated/` with naming convention |
| 3 | `qa_agent/orchestrator/progress.py` | JSON checkpoint — done/pending/failed, supports resume |

**CLI commands (added to `qa_agent/cli.py`):**
```
qa-agent crawl                     # full site
qa-agent crawl --page homepage     # single page
qa-agent crawl --page homepage,pdp # multiple pages
qa-agent crawl --resume            # resume from checkpoint
qa-agent crawl --dry               # snapshot only, no generation
qa-agent crawl --auth              # include auth-gated pages
```

**Orchestrator core loop:**
```python
class Orchestrator:
    async def crawl_site(self, pages=None, include_auth=False):
        for config in targets:
            if self.progress.is_done(config.name):
                continue
            # 1. Crawl page → DOM snapshot
            # 2. Generate POM → TypeScript class
            # 3. Validate POM
            # 4. Generate test spec
            # 5. Validate test spec
            # 6. Write files to disk
            # 7. Mark progress
```

**File naming convention (matches existing Executor):**
- POM: `page_objects/HomepagePage.ts`
- Test: `tests_generated/homepage.spec.ts`

**Exit gate:** `qa-agent crawl --page homepage` produces both files.

---

## H. Phase O6 — Hardening & Memory (90% → 100%)

**Goal:** Edge cases, memory integration, responsive crawling.

| # | File | Contents |
|---|------|----------|
| 1 | `qa_agent/orchestrator/memory_integration.py` | Update `memory/APP_STRUCTURE.md` with discovered routes/elements |
| 2 | `qa_agent/orchestrator/responsive_crawler.py` | Crawl at desktop (1280x720) + mobile (375x812) viewports |

**Edge case handling:**

| Edge Case | Strategy |
|-----------|----------|
| Cookie consent | Popup handler clicks "accept" |
| Promo modal | Popup handler clicks close/X |
| Newsletter popup | Same as promo modal |
| Lazy-loaded content | Scroll + `browser_wait_for` |
| CAPTCHA | Skip page, log "requires manual crawl" |
| Rate limiting / 403 | Retry with backoff, max 3 |
| 404 pages | Log error, continue to next page |
| SPA transitions | `browser_wait_for` on expected content |

**Memory integration:** After each page is processed, update `memory/APP_STRUCTURE.md` with discovered routes, element counts, testids — allowing the existing Healer and Generator to benefit.

**Exit gate:** Full site crawl → 16 POM files + 16 test specs, all validated, memory updated.

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Page types covered | >= 16 |
| Test scenarios per page | >= 5 average |
| Total test scenarios | >= 80 |
| POM validation pass rate | 100% |
| Test validation pass rate | 100% |
| CSS selectors in output | 0 |
| Crawl success rate | >= 90% |
| Time for full crawl | < 30 min |
| Memory routes updated | All 16 in APP_STRUCTURE.md |

---

## Assumptions

- Camping World's site is publicly accessible (no VPN or IP-gating for non-auth pages)
- Playwright MCP can handle campingworld.com without being blocked
- Test credentials provided via `APP_TEST_USER` / `APP_TEST_PASS` env vars for auth-gated pages
- `browser_snapshot` returns an accessibility tree sufficient to identify interactive elements
- Checkout testing stops at form validation — no real orders submitted
- Dynamic URLs (products, stores, RV listings) can be discovered by crawling listing pages first

## Not in Scope

- Running the generated tests (existing Executor does this)
- Self-healing locators (existing Healer does this)
- Visual regression testing (separate feature spec)
- API-level testing (separate feature spec)
- Real payment processing
- Native mobile app testing
