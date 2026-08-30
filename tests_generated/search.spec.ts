import { test, expect } from './fixtures';
import { SearchPage } from '../page_objects/SearchPage';

test.describe('Search Results', () => {
  let searchPage: SearchPage;

  test.beforeEach(async ({ page }) => {
    searchPage = new SearchPage(page);
    await searchPage.navigate('tent');
  });

  test('search results page loads for query "tent"', async ({ page }) => {
    await expect(page).toHaveURL(/tent|search/i);
  });

  test('main content area is visible', async () => {
    await expect(searchPage.mainContent).toBeVisible();
  });

  test('Add To Cart buttons are present in search results', async () => {
    const count = await searchPage.getAddToCartCount();
    expect(count).toBeGreaterThan(0);
  });

  test('first Add To Cart button is enabled', async () => {
    await expect(searchPage.addToCartButtons.first()).toBeEnabled();
  });

  test('product prices are displayed in results', async () => {
    await expect(searchPage.productPrices.first()).toBeVisible();
  });

  test('search input is visible in header', async () => {
    await expect(searchPage.searchInput).toBeVisible();
  });

  test('product links are present in main content', async ({ page }) => {
    // Wait for product links with .html hrefs to appear
    const productLink = page.getByRole('main').locator('a[href*=".html"]').first();
    await expect(productLink).toBeVisible({ timeout: 15_000 });
    const count = await page.getByRole('main').locator('a[href*=".html"]').count();
    expect(count).toBeGreaterThan(0);
  });

  test('product links point to product pages', async ({ page }) => {
    const productLink = page.getByRole('main').locator('a[href*=".html"]').first();
    await expect(productLink).toBeVisible();
    const href = await productLink.getAttribute('href');
    expect(href).toMatch(/\.html/);
  });

  test('search for a different term shows new results', async ({ page }) => {
    await searchPage.navigate('sleeping bag');
    await expect(page).toHaveURL(/sleeping.bag|search/i);
    await expect(searchPage.mainContent).toBeVisible();
  });
});
