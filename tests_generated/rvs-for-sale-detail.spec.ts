import { test, expect } from './fixtures';
import { RvsForSaleDetailPage } from '../page_objects/RvsForSaleDetailPage';

test.describe('RV Detail Page', () => {
  let rvDetailPage: RvsForSaleDetailPage;

  test.beforeEach(async ({ page }) => {
    rvDetailPage = new RvsForSaleDetailPage(page);
    await rvDetailPage.navigate();
  });

  test('RV detail page loads on rv.campingworld.com', async ({ page }) => {
    await expect(page).toHaveURL(/rv\.campingworld\.com/);
  });

  test('detail page URL is different from the listing page', async ({ page }) => {
    await expect(page).not.toHaveURL(/\/rvs-for-sale$/);
  });

  test('main content area is visible', async () => {
    await expect(rvDetailPage.mainContent).toBeVisible();
  });

  test('RV title heading is visible', async () => {
    await expect(rvDetailPage.rvTitle).toBeVisible();
  });

  test('RV title is not empty', async () => {
    const text = await rvDetailPage.rvTitle.textContent();
    expect(text?.trim()).not.toBe('');
  });

  test('price information is displayed', async () => {
    await expect(rvDetailPage.rvPrice).toBeVisible();
  });

  test('main RV image is visible', async () => {
    await expect(rvDetailPage.mainImage).toBeVisible();
  });

  test('RV subdomain header has Search RVs input', async () => {
    await expect(rvDetailPage.searchRvsInput).toBeVisible();
  });

  test('Store Locator link is in the RV subdomain header', async () => {
    await expect(rvDetailPage.storeLocatorLink).toBeVisible();
  });

  test('RV detail page has multiple headings', async () => {
    const headings = rvDetailPage.page.getByRole('main').getByRole('heading');
    const count = await headings.count();
    expect(count).toBeGreaterThan(0);
  });
});
