import { test, expect } from './fixtures';
import { StoreLocatorPage } from '../page_objects/StoreLocatorPage';

test.describe('Store Locator', () => {
  let storeLocator: StoreLocatorPage;

  test.beforeEach(async ({ page }) => {
    storeLocator = new StoreLocatorPage(page);
    await storeLocator.navigate();
  });

  test('page redirects to rv.campingworld.com/locations', async ({ page }) => {
    await expect(page).toHaveURL(/rv\.campingworld\.com\/locations/);
  });

  test('page heading is visible', async () => {
    await expect(storeLocator.pageHeading).toBeVisible();
  });

  test('map region is visible', async () => {
    await expect(storeLocator.mapRegion).toBeVisible();
  });

  test('location input is visible', async () => {
    await storeLocator.locationInput.scrollIntoViewIfNeeded();
    await expect(storeLocator.locationInput).toBeVisible();
  });

  test('location input is enabled', async () => {
    await storeLocator.locationInput.scrollIntoViewIfNeeded();
    await expect(storeLocator.locationInput).toBeEnabled();
  });

  test('View Filters button is visible', async () => {
    await storeLocator.viewFiltersButton.scrollIntoViewIfNeeded();
    await expect(storeLocator.viewFiltersButton).toBeVisible();
  });

  test('View State Directory link is visible', async () => {
    await storeLocator.viewStateDirectoryLink.scrollIntoViewIfNeeded();
    await expect(storeLocator.viewStateDirectoryLink).toBeVisible();
  });

  test('featured dealership section is present', async () => {
    await storeLocator.featuredHeading.scrollIntoViewIfNeeded();
    await expect(storeLocator.featuredHeading).toBeVisible();
  });

  test('Store Locator text is in the header', async () => {
    await expect(storeLocator.storeLocatorLink).toBeVisible();
  });

  test('search RVs input is in the header', async () => {
    await expect(storeLocator.searchRvsInput).toBeVisible();
  });
});
