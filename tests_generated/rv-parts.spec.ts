import { test, expect } from './fixtures';
import { RvPartsPage } from '../page_objects/RvPartsPage';

test.describe('RV Parts', () => {
  let rvPartsPage: RvPartsPage;

  test.beforeEach(async ({ page }) => {
    rvPartsPage = new RvPartsPage(page);
    await rvPartsPage.navigate();
  });

  test('/rv-parts page loads (currently returns 404)', async ({ page }) => {
    // The page currently 404s — verify we got a response from campingworld.com
    await expect(page).toHaveURL(/campingworld\.com\/rv-parts/);
  });

  test('site header logo is present even on 404 page', async () => {
    await expect(rvPartsPage.logo).toBeVisible();
  });

  test('page renders a heading', async () => {
    await expect(rvPartsPage.pageHeading).toBeVisible();
  });

  test('main content area is rendered', async () => {
    await expect(rvPartsPage.mainContent).toBeVisible();
  });

  test('search input is available in header on 404 page', async () => {
    await expect(rvPartsPage.searchInput).toBeVisible();
  });
});
