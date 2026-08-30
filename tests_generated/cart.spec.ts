import { test, expect } from './fixtures';
import { CartPage } from '../page_objects/CartPage';

test.describe('Shopping Cart', () => {
  let cartPage: CartPage;

  test.beforeEach(async ({ page }) => {
    cartPage = new CartPage(page);
    await cartPage.navigate();
  });

  test('cart page loads and shows empty cart heading', async () => {
    await expect(cartPage.emptyCartHeading).toBeVisible();
  });

  test('empty cart heading text is correct', async ({ page }) => {
    await expect(cartPage.emptyCartHeading).toHaveText(/your shopping cart is empty/i);
  });

  test('page URL is /cart', async ({ page }) => {
    await expect(page).toHaveURL(/\/cart/);
  });

  test('logo is visible on cart page', async () => {
    await expect(cartPage.logo).toBeVisible();
  });

  test('Top Picks section shows Add To Cart buttons on empty cart', async () => {
    const count = await cartPage.addToCartButtons.count();
    expect(count).toBeGreaterThan(0);
  });

  test('Add To Cart buttons in Top Picks carousel are enabled', async () => {
    await expect(cartPage.addToCartButtons.first()).toBeEnabled();
  });

  test('cart link in header is visible', async () => {
    await expect(cartPage.cartLink).toBeVisible();
  });

  test('isCartEmpty returns true on empty cart page', async () => {
    const isEmpty = await cartPage.isCartEmpty();
    expect(isEmpty).toBe(true);
  });
});
