import { test as base, type Page } from '@playwright/test';

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

/**
 * Extended test fixture that auto-dismisses popups after each page navigation.
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

export { expect } from '@playwright/test';
