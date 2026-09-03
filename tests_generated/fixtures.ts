import { test as base, type Page, type TestInfo } from '@playwright/test';

/**
 * Dismiss all known popups on campingworld.com and rv.campingworld.com.
 * Runs multiple passes to catch popups that load at different times:
 *   Pass 1: Cookie consent banner (loads ~2s after page)
 *   Pass 2-4: Email signup modal (loads ~3-5s after page)
 */
async function dismissPopups(page: Page) {
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.waitForTimeout(attempt === 0 ? 2000 : 1500);

    // 1. Cookie consent banner — <a> with class cc-btn cc-dismiss
    try {
      const ccDismiss = page.locator('a.cc-btn.cc-dismiss, .cc-dismiss, #onetrust-accept-btn-handler');
      if (await ccDismiss.first().isVisible({ timeout: 500 })) {
        await ccDismiss.first().click({ force: true });
        await page.waitForTimeout(500);
        continue; // Keep polling for more popups
      }
    } catch { /* no cookie banner */ }

    // 2. Cookie fallback — any button/link with text "Close"
    try {
      const closeBtn = page.locator('button, a').filter({ hasText: /^Close$/ });
      if (await closeBtn.first().isVisible({ timeout: 500 })) {
        await closeBtn.first().click({ force: true });
        await page.waitForTimeout(500);
        continue;
      }
    } catch { /* no close button */ }

    // 3. Email signup modal — "No Thanks" link
    try {
      const noThanks = page.locator('text=No Thanks').first();
      if (await noThanks.isVisible({ timeout: 500 })) {
        await noThanks.click({ force: true });
        await page.waitForTimeout(300);
        continue;
      }
    } catch { /* no email modal */ }

    // 4. Email signup modal — X close button (top-right)
    try {
      const modalClose = page.locator('[class*="modal"] button[aria-label="Close"], [class*="modal"] button:has(svg), .modal-close, button.close-modal').first();
      if (await modalClose.isVisible({ timeout: 500 })) {
        await modalClose.click({ force: true });
        await page.waitForTimeout(300);
        continue;
      }
    } catch { /* no modal X button */ }

    // 5. Escape key fallback then stop
    try { await page.keyboard.press('Escape'); } catch { /* ignore */ }
    break;
  }
}

// ---------------------------------------------------------------------------
// URL → Human-readable page name
// ---------------------------------------------------------------------------
const URL_TO_PAGE_NAME: Record<string, string> = {
  '/cart': 'Shopping Cart page',
  '/checkout': 'Checkout page',
  '/sign-in': 'Sign In page',
  '/account': 'Sign In page',
  '/register': 'Registration page',
  '/store-locator': 'Store Locator page',
  '/rv-parts': 'RV Parts page',
  '/good-sam': 'Good Sam page',
  '/shop': 'Homepage',
};

function urlToPageName(url: string): string {
  // Check query params for search
  if (url.includes('/search')) {
    const match = url.match(/[?&]q=([^&]+)/);
    if (match) return `Search page (searching for "${decodeURIComponent(match[1]).replace(/\+/g, ' ')}")`;
    return 'Search page';
  }
  // Check known routes
  for (const [route, name] of Object.entries(URL_TO_PAGE_NAME)) {
    if (url.includes(route)) return name;
  }
  // Product page (.html)
  if (url.includes('.html')) {
    const slug = url.split('/').pop()?.replace('.html', '').replace(/-/g, ' ') || 'product';
    return `Product page (${slug})`;
  }
  // RV subdomain
  if (url.includes('rv.campingworld')) return 'RVs For Sale page';
  // Homepage
  if (url === '/' || url === '') return 'Homepage';
  return `page at ${url}`;
}

// ---------------------------------------------------------------------------
// Locator → Human-readable element name
// ---------------------------------------------------------------------------
function locatorToHumanName(locatorStr: string): string {
  // getByRole('button', { name: 'Add to Cart' }) → "the Add to Cart button"
  const rolePattern = new RegExp("getByRole\\(['\"]([\\w]+)['\"](?:,\\s*\\{[^}]*name:\\s*[/'\"]([^/'\"]+)[/'\"]\\/)?");
  const roleMatch = locatorStr.match(rolePattern);
  if (roleMatch) {
    const role = roleMatch[1];
    const name = roleMatch[2];
    if (name) return `the "${name}" ${role}`;
    if (role === 'main') return 'the main content area';
    if (role === 'navigation') return 'the navigation area';
    if (role === 'heading') return 'the heading';
    if (role === 'searchbox') return 'the search input';
    return `the ${role} element`;
  }
  // getByTestId('checkout-btn') → "the checkout button"
  const testIdMatch = locatorStr.match(/getByTestId\(['"]([^'"]+)['"]\)/);
  if (testIdMatch) return `the "${testIdMatch[1]}" element`;
  // getByText('Sign In') → "the Sign In text"
  const textMatch = locatorStr.match(/getByText\(['"]([^'"]+)['"]\)/);
  if (textMatch) return `the "${textMatch[1]}" text`;
  // getByLabel('Email') → "the Email field"
  const labelMatch = locatorStr.match(/getByLabel\(['"]([^'"]+)['"]\)/);
  if (labelMatch) return `the "${labelMatch[1]}" field`;
  // Fallback
  return 'the element';
}

// ---------------------------------------------------------------------------
// Playwright action → Human-readable step
// ---------------------------------------------------------------------------
function stepToHuman(title: string, category: string): string {
  // Navigation
  if (title.includes('page.goto')) {
    const urlMatch = title.match(/goto\(['"]([^'"]+)['"]/);
    if (urlMatch) return `Open the ${urlToPageName(urlMatch[1])}`;
    return 'Navigate to the page';
  }
  // Popup dismissal
  if (title.includes('dismissPopups') || title.includes('Wait for timeout')) {
    return 'Wait for the page to load and dismiss any popups';
  }
  // Assertions
  if (title.includes('toBeVisible')) {
    const name = locatorToHumanName(title);
    return `Verify ${name} is visible on the page`;
  }
  if (title.includes('toHaveURL')) return 'Verify the page URL matches the expected pattern';
  if (title.includes('toHaveText')) return 'Verify the text content matches the expected value';
  if (title.includes('toBeEnabled')) {
    const name = locatorToHumanName(title);
    return `Verify ${name} is enabled and clickable`;
  }
  if (title.includes('toHaveCount')) return 'Verify the expected number of elements are present';
  if (title.includes('toBeGreaterThan')) return 'Verify at least one element is present';
  if (title.includes('toMatch')) return 'Verify the value matches the expected pattern';
  // Interactions
  if (title.includes('.click')) {
    const name = locatorToHumanName(title);
    return `Click on ${name}`;
  }
  if (title.includes('.fill')) {
    const valMatch = title.match(/fill\(['"]([^'"]*)['"]\)/);
    const name = locatorToHumanName(title);
    if (valMatch) return `Type "${valMatch[1]}" into ${name}`;
    return `Type into ${name}`;
  }
  if (title.includes('scrollIntoViewIfNeeded')) {
    const name = locatorToHumanName(title);
    return `Scroll down to make ${name} visible`;
  }
  if (title.includes('.waitFor')) {
    const name = locatorToHumanName(title);
    return `Wait for ${name} to appear on the page`;
  }
  if (title.includes('keyboard.press')) {
    const keyMatch = title.match(/press\(['"]([^'"]+)['"]\)/);
    return `Press the "${keyMatch?.[1] || '...'}" key`;
  }
  // Before/After hooks
  if (category === 'hook' && title.includes('Before')) return 'Set up the test (navigate to the page)';
  if (category === 'hook' && title.includes('After')) return 'Clean up after test';
  // Wait for selector
  if (title.includes('waitFor') || title.includes('Wait for selector')) {
    return 'Wait for page content to load';
  }
  // Fallback
  return title;
}

// ---------------------------------------------------------------------------
// Generate Steps to Reproduce from TestInfo
// ---------------------------------------------------------------------------
function generateHumanSteps(testInfo: TestInfo): string {
  const lines: string[] = ['Steps to Reproduce:', ''];
  const steps = (testInfo as any)._steps || [];
  let stepNum = 1;
  let failedStep = '';

  // Extract URL from the test for context
  const titleParts = testInfo.titlePath;
  const suiteName = titleParts.length > 1 ? titleParts[titleParts.length - 2] : '';

  // Walk through steps
  for (const step of steps) {
    const title = step.title || '';
    const category = step.category || '';
    const error = step.error;

    // Skip internal Playwright steps
    if (category === 'pw:api' && !title.includes('expect') && !title.includes('goto') &&
        !title.includes('click') && !title.includes('fill') && !title.includes('waitFor') &&
        !title.includes('scrollInto') && !title.includes('keyboard')) continue;
    if (title === 'Worker Cleanup') continue;
    if (title === 'After Hooks') continue;

    const humanStep = stepToHuman(title, category);
    // Deduplicate consecutive identical steps
    if (lines.length > 0 && lines[lines.length - 1].includes(humanStep)) continue;

    const status = error ? '  ✗ FAILED' : '  ✓';
    lines.push(`${stepNum}. ${humanStep}${status}`);
    stepNum++;

    if (error) {
      failedStep = humanStep;
      break; // Stop after the failing step
    }
  }

  lines.push('');

  // Add Expected vs Actual
  if (testInfo.error) {
    const errMsg = testInfo.error.message || '';
    let expected = 'The step above should have succeeded';
    let actual = 'It failed';

    if (errMsg.includes('toBeVisible')) {
      expected = 'Element should be visible on the page';
      actual = `Element was not found within ${testInfo.project?.expect?.timeout || 10000 / 1000}s`;
    } else if (errMsg.includes('toHaveURL')) {
      expected = 'Page URL should match the expected pattern';
      actual = 'URL did not match';
    } else if (errMsg.includes('toBeEnabled')) {
      expected = 'Element should be enabled and clickable';
      actual = 'Element was disabled or not found';
    } else if (errMsg.includes('toBeGreaterThan') || errMsg.includes('toHaveCount')) {
      const receivedMatch = errMsg.match(/Received:\s*(\d+)/);
      expected = 'At least one element should be present';
      actual = `Found ${receivedMatch?.[1] || '0'} elements`;
    } else if (errMsg.includes('Timeout')) {
      expected = 'Page should have loaded within the timeout';
      actual = `Timed out after ${testInfo.timeout / 1000}s`;
    }

    lines.push(`Expected: ${expected}`);
    lines.push(`Actual: ${actual}`);
  }

  lines.push('');
  lines.push(`Test: ${testInfo.title}`);
  lines.push(`Suite: ${suiteName}`);
  lines.push(`Browser: ${testInfo.project.name}`);
  lines.push(`Site: campingworld.com`);
  lines.push(`Duration: ${((testInfo.duration || 0) / 1000).toFixed(1)}s`);

  return lines.join('\n');
}

function generateTechnicalSteps(testInfo: TestInfo): string {
  const lines: string[] = ['Technical Steps:', ''];
  const steps = (testInfo as any)._steps || [];
  let stepNum = 1;

  for (const step of steps) {
    const title = step.title || '';
    const category = step.category || '';
    const duration = step.duration ? `(${(step.duration / 1000).toFixed(1)}s)` : '';
    const error = step.error;

    if (title === 'Worker Cleanup') continue;

    const status = error ? '✗' : '✓';
    lines.push(`${stepNum}. ${status} ${title} ${duration}`);

    if (error) {
      const errMsg = error.message || '';
      // Extract locator info
      const locatorMatch = errMsg.match(/Locator:\s*(.+)/);
      if (locatorMatch) lines.push(`   Locator: ${locatorMatch[1]}`);
      // Extract timeout
      const timeoutMatch = errMsg.match(/Timeout:\s*(\d+)ms/);
      if (timeoutMatch) lines.push(`   Timeout: ${timeoutMatch[1]}ms`);
      // Error type
      const errorType = errMsg.split('\n')[0] || '';
      lines.push(`   Error: ${errorType}`);
      break;
    }
    stepNum++;
  }

  lines.push('');
  lines.push(`Spec File: ${testInfo.file?.split('/').pop() || 'unknown'}:${testInfo.line || '?'}`);
  lines.push(`Test: ${testInfo.title}`);
  lines.push(`Project: ${testInfo.project.name}`);
  lines.push(`Duration: ${((testInfo.duration || 0) / 1000).toFixed(1)}s`);
  lines.push(`Retries: ${testInfo.retry}/${testInfo.project.retries}`);

  return lines.join('\n');
}

/**
 * Extended test fixture that auto-dismisses popups after each page navigation
 * and attaches "Steps to Reproduce" on test failure.
 */
export const test = base.extend({
  page: async ({ page }, use) => {
    page.on('dialog', async (dialog) => {
      await dialog.dismiss();
    });

    const originalGoto = page.goto.bind(page);
    page.goto = async (url: string, options?: Parameters<Page['goto']>[1]) => {
      const response = await originalGoto(url, {
        waitUntil: 'domcontentloaded',
        timeout: 30_000,
        ...options,
      });
      await dismissPopups(page);
      return response;
    };

    await use(page);
  },
});

// Attach Steps to Reproduce on failure
test.afterEach(async ({}, testInfo) => {
  if (testInfo.status !== 'passed' && testInfo.status !== 'skipped') {
    try {
      const humanSteps = generateHumanSteps(testInfo);
      await testInfo.attach('steps-to-reproduce', {
        body: humanSteps,
        contentType: 'text/plain',
      });

      const technicalSteps = generateTechnicalSteps(testInfo);
      await testInfo.attach('steps-to-reproduce-technical', {
        body: technicalSteps,
        contentType: 'text/plain',
      });
    } catch {
      // Don't let step generation failure mask the actual test failure
    }
  }
});

export { expect } from '@playwright/test';
