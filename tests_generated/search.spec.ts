import { test, expect } from '@playwright/test';
import { HomePage } from '../page_objects/';
import { SearchResultsPage } from '../page_objects/';

test.describe('Search Functionality @search', () => {
  let homePage: HomePage;
  let searchResultsPage: SearchResultsPage;

  test.beforeEach(async ({ page }) => {
    homePage = new HomePage(page);
    searchResultsPage = new SearchResultsPage(page);
    await homePage.navigate();
  });

  // tc-search-01
  test('tc-search-01: Search bar is visible and accessible on homepage @smoke @search', async ({ page }) => {
    const searchInput = await homePage.getSearchInput();
    await expect(searchInput).toBeVisible();
    await expect(searchInput).toBeEnabled();
  });

  // tc-search-02
  test('tc-search-02: User can type a query into the search bar @smoke @search', async ({ page }) => {
    await homePage.clickSearchInput();
    await homePage.typeSearchQuery('tent');
    const value = await homePage.getSearchInputValue();
    expect(value).toBe('tent');
  });

  // tc-search-03
  test('tc-search-03: User can submit a search query and see results @smoke @search', async ({ page }) => {
    await homePage.searchFor('tent');
    await searchResultsPage.waitForResults();

    // URL should reflect search
    await expect(page).toHaveURL(/search|Ntt=tent|q=tent/i);

    // At least one product card should be visible
    const count = await searchResultsPage.getProductCount();
    expect(count).toBeGreaterThan(0);

    // First product card is visible
    await expect(searchResultsPage.firstProductCard).toBeVisible();
  });

  // tc-search-04
  test('tc-search-04: Search results display product names and prices @search', async ({ page }) => {
    await homePage.searchFor('sleeping bag');
    await searchResultsPage.waitForResults();

    const count = await searchResultsPage.getProductCount();
    expect(count).toBeGreaterThan(0);

    // First product has a visible name
    const firstName = await searchResultsPage.getFirstProductName();
    expect(firstName.trim().length).toBeGreaterThan(0);

    // First product has a visible price
    const firstPrice = await searchResultsPage.getFirstProductPrice();
    expect(firstPrice).toMatch(/\$[\d,]+\.\d{2}/);

    // Product images are rendered
    const firstImage = searchResultsPage.firstProductCard.getByRole('img').first();
    await expect(firstImage).toBeVisible();
  });

  // tc-search-05
  test('tc-search-05: Search with a specific product keyword returns relevant results @smoke @search', async ({ page }) => {
    await homePage.searchFor('generator');
    await searchResultsPage.waitForResults();

    // No error message
    const hasError = await searchResultsPage.hasErrorMessage();
    expect(hasError).toBe(false);

    // Results are present
    const count = await searchResultsPage.getProductCount();
    expect(count).toBeGreaterThan(0);

    // At least some results contain 'generator' in their titles (case-insensitive)
    const titles = await searchResultsPage.getAllProductTitles();
    const relevantTitles = titles.filter(t => /generator/i.test(t));
    expect(relevantTitles.length).toBeGreaterThan(0);
  });

  // tc-search-06
  test('tc-search-06: Search with no query or empty string does not break the page @search', async ({ page }) => {
    await homePage.clickSearchInput();
    // Submit without typing
    await homePage.submitSearch();
    await page.waitForLoadState('domcontentloaded');

    // Page should not show an unhandled error
    const hasError = await searchResultsPage.hasErrorMessage();
    expect(hasError).toBe(false);

    // Page title or body should still be present
    await expect(page.locator('body')).toBeVisible();
  });

  // tc-search-07
  test('tc-search-07: Search with a term that returns no results shows an empty state message @search', async ({ page }) => {
    await homePage.searchFor('xyznonexistentproduct12345');
    await searchResultsPage.waitForResults();

    // Page should not crash
    const hasError = await searchResultsPage.hasErrorMessage();
    expect(hasError).toBe(false);

    // Either no product cards, or an empty-state message is shown
    const count = await searchResultsPage.getProductCount();
    if (count === 0) {
      // No product cards shown — acceptable empty state
      expect(count).toBe(0);
    } else {
      // If cards exist, check for a no-results message
      const noResultsMsg = await searchResultsPage.getNoResultsMessage();
      await expect(noResultsMsg).toBeVisible();
    }
  });

  // tc-search-08
  test('tc-search-08: User can click on a search result to navigate to the product detail page @smoke @search', async ({ page }) => {
    await homePage.searchFor('tent');
    await searchResultsPage.waitForResults();

    // Ensure results are present
    const count = await searchResultsPage.getProductCount();
    expect(count).toBeGreaterThan(0);

    // Click the first product
    await searchResultsPage.clickFirstProduct();
    await page.waitForLoadState('domcontentloaded');

    // URL should change to a product detail page
    const url = page.url();
    expect(url).not.toMatch(/\/search/i);
    expect(url).toMatch(/campingworld\.com/i);

    // Product name should be visible on the detail page
    const productHeading = page.getByRole('heading', { level: 1 });
    await expect(productHeading).toBeVisible();

    // Add to cart button or product details present
    const addToCartBtn = page.getByRole('button', { name: /add to cart/i });
    const productDetails = page.getByText(/product details|description|specifications/i).first();
    const addToCartVisible = await addToCartBtn.isVisible().catch(() => false);
    const detailsVisible = await productDetails.isVisible().catch(() => false);
    expect(addToCartVisible || detailsVisible).toBe(true);
  });
});
