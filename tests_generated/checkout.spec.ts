import { test, expect } from './fixtures';
import { CheckoutPage } from '../page_objects/CheckoutPage';

test.describe('Checkout', () => {
  let checkoutPage: CheckoutPage;

  test.beforeEach(async ({ page }) => {
    checkoutPage = new CheckoutPage(page);
    await checkoutPage.navigate();
  });

  test('visiting /checkout with empty cart redirects to /cart', async ({ page }) => {
    // /checkout redirects to /cart when cart is empty
    await expect(page).toHaveURL(/\/cart/);
  });

  test('redirected cart page shows empty cart heading', async () => {
    await expect(checkoutPage.emptyCartHeading).toBeVisible();
  });

  test('redirected cart page shows main content', async () => {
    await expect(checkoutPage.mainContent).toBeVisible();
  });

  test('cart link in header is visible after redirect', async () => {
    await expect(checkoutPage.cartLink).toBeVisible();
  });
});
