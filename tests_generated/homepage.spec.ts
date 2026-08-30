import { test, expect } from './fixtures';
import { HomepagePage } from '../page_objects/HomepagePage';

test.describe('Homepage', () => {
  let homepage: HomepagePage;

  test.beforeEach(async ({ page }) => {
    homepage = new HomepagePage(page);
    await homepage.navigate();
  });

  test('hero banner is visible', async () => {
    await expect(homepage.heroBanner).toBeVisible();
  });

  test('logo is visible in navigation', async () => {
    await expect(homepage.logo).toBeVisible();
  });

  test('main navigation is visible', async () => {
    await expect(homepage.mainNav).toBeVisible();
  });

  test('shop by category menu button is visible', async () => {
    await expect(homepage.shopByCategoryButton).toBeVisible();
  });

  test('deals & services menu button is visible', async () => {
    await expect(homepage.dealsAndServicesButton).toBeVisible();
  });

  test('sign in button is visible in navigation', async () => {
    await expect(homepage.signInButton).toBeVisible();
  });

  test('cart link is visible in navigation', async () => {
    await expect(homepage.cartLink).toBeVisible();
  });

  test('find a store link is visible', async () => {
    await expect(homepage.storeLocatorLink).toBeVisible();
  });

  test('search bar accepts input and navigates to results on submit', async ({ page }) => {
    await homepage.search('tent');
    await expect(page).toHaveURL(/tent/i, { timeout: 15_000 });
  });

  test('search bar accepts input and navigates to results on Enter key', async ({ page }) => {
    await homepage.searchAndPressEnter('sleeping bag');
    await expect(page).toHaveURL(/sleeping(%20|\+| )bag/i, { timeout: 15_000 });
  });

  test('main content area is visible', async () => {
    await expect(homepage.mainContent).toBeVisible();
  });

  test('footer is visible and contains links', async () => {
    await expect(homepage.footer).toBeVisible();
    const linkCount = await homepage.footerLinks.count();
    expect(linkCount).toBeGreaterThan(0);
  });

  test('footer social links are present', async () => {
    const count = await homepage.footerSocialLinks.count();
    expect(count).toBeGreaterThan(0);
  });
});
