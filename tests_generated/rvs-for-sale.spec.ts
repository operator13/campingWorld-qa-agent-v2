import { test, expect } from './fixtures';
import { RvsForSalePage } from '../page_objects/RvsForSalePage';

test.describe('RV Listings Page', () => {
  let rvsForSalePage: RvsForSalePage;

  test.beforeEach(async ({ page }) => {
    rvsForSalePage = new RvsForSalePage(page);
    await rvsForSalePage.navigate();
  });

  test('RVs for sale page loads on rv.campingworld.com', async ({ page }) => {
    await expect(page).toHaveURL(/rv\.campingworld\.com/);
  });

  test('main content area is visible', async () => {
    await expect(rvsForSalePage.mainContent).toBeVisible();
  });

  test('page has a primary heading', async () => {
    await expect(rvsForSalePage.pageHeading).toBeVisible();
  });

  test('RV listing cards are displayed', async () => {
    const count = await rvsForSalePage.getListingCount();
    expect(count).toBeGreaterThan(0);
  });

  test('first listing card is visible', async () => {
    await expect(rvsForSalePage.listingCards.first()).toBeVisible();
  });

  test('listing cards contain price information', async () => {
    await expect(rvsForSalePage.listingCardPrices).toBeVisible();
  });

  test('listing cards contain images', async () => {
    await expect(rvsForSalePage.listingCardImages).toBeVisible();
  });

  test('RV subdomain header has Search RVs input', async () => {
    await expect(rvsForSalePage.searchRvsInput).toBeVisible();
  });

  test('Store Locator link is in the RV subdomain header', async () => {
    await expect(rvsForSalePage.storeLocatorLink).toBeVisible();
  });

  test('clicking a listing card navigates to a detail page', async ({ page }) => {
    await rvsForSalePage.listingCards.first().click();
    await expect(page).toHaveURL(/\/rv\//);
  });
});
