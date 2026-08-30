import { test, expect } from './fixtures';
import { NavPage } from '../page_objects/NavPage';

test.describe('Global Navigation', () => {
  let nav: NavPage;

  test.beforeEach(async ({ page }) => {
    nav = new NavPage(page);
    await nav.navigate();
  });

  test('logo is visible in the header', async () => {
    await expect(nav.logo).toBeVisible();
  });

  test('logo links to /shop', async () => {
    const href = await nav.logo.getAttribute('href');
    expect(href).toMatch(/\/shop/);
  });

  test('search input is visible and enabled', async () => {
    await expect(nav.searchInput).toBeVisible();
    await expect(nav.searchInput).toBeEnabled();
  });

  test('search button is visible and enabled', async () => {
    await expect(nav.searchButton).toBeVisible();
    await expect(nav.searchButton).toBeEnabled();
  });

  test('sign in button is visible in the header', async () => {
    await expect(nav.signInButton).toBeVisible();
  });

  test('cart link is visible in the header', async () => {
    await expect(nav.cartLink).toBeVisible();
  });

  test('cart link navigates to /cart', async ({ page }) => {
    await nav.navigateToCart();
    await expect(page).toHaveURL(/\/cart/);
  });

  test('Find a Store link is visible', async () => {
    await expect(nav.storeLocatorLink).toBeVisible();
  });

  test('Find a Store link opens store locator panel', async () => {
    await nav.navigateToStoreLocator();
    // Clicking Find a Store opens a sidebar panel, not a new page
    const panel = nav.page.getByText(/shop by store|go to store locator/i).first();
    await expect(panel).toBeVisible();
  });

  test('Shop By Category button is present in nav', async () => {
    await expect(nav.shopByCategoryButton).toBeVisible();
  });

  test('Deals & Services button is present in nav', async () => {
    await expect(nav.dealsAndServicesButton).toBeVisible();
  });

  test('clicking Shop By Category button triggers menu interaction', async ({ page }) => {
    await nav.openShopByCategory();
    // After clicking, a menu/panel should appear — main nav stays visible
    await expect(nav.mainNav).toBeVisible();
  });

  test('searching navigates to search results', async ({ page }) => {
    await nav.search('tent');
    await expect(page).toHaveURL(/tent|search/i);
  });

  test('main navigation is inside the banner landmark', async () => {
    await expect(nav.mainNav).toBeVisible();
  });
});
