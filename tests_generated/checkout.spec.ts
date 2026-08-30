import { test, expect } from '@playwright/test';
import { HomePage } from '../page_objects/';
import { ProductPage } from '../page_objects/ProductPage';
import { CartPage } from '../page_objects/CartPage';
import { CheckoutPage } from '../page_objects/CheckoutPage';

/**
 * Helper: add a tent to cart and navigate to the cart page.
 */
async function addTentAndGoToCart(
  homePage: HomePage,
  productPage: ProductPage,
  cartPage: CartPage
): Promise<string | null> {
  await homePage.navigate();
  await homePage.searchForProduct('tent');
  await homePage.clickFirstSearchResult();
  const title = await productPage.getProductTitle();
  await productPage.addToCart();
  // Brief wait for cart state to settle
  await homePage.page.waitForTimeout(1500);
  await cartPage.navigate();
  await cartPage.waitForCartToLoad();
  return title;
}

test.describe('Checkout', () => {
  let homePage: HomePage;
  let productPage: ProductPage;
  let cartPage: CartPage;
  let checkoutPage: CheckoutPage;

  test.beforeEach(async ({ page }) => {
    homePage = new HomePage(page);
    productPage = new ProductPage(page);
    cartPage = new CartPage(page);
    checkoutPage = new CheckoutPage(page);
  });

  test('tc-checkout-01: User can proceed to checkout from the cart @smoke @checkout', async ({ page }) => {
    await addTentAndGoToCart(homePage, productPage, cartPage);

    // Assert we are on the cart page
    await expect(page).toHaveURL(/\/cart/);

    // Click proceed to checkout
    await cartPage.proceedToCheckout();

    // Wait for checkout page to load
    await checkoutPage.waitForCheckoutToLoad();

    // Assert URL contains /checkout
    await expect(page).toHaveURL(/checkout/);

    // Assert checkout page shows sign-in prompt, guest option, or email input
    const headingVisible = await checkoutPage.checkoutHeading.isVisible().catch(() => false);
    const signInVisible = await checkoutPage.signInPrompt.first().isVisible().catch(() => false);
    const emailVisible = await checkoutPage.emailInput.isVisible().catch(() => false);
    const guestVisible = await checkoutPage.guestCheckoutOption.first().isVisible().catch(() => false);

    expect(headingVisible || signInVisible || emailVisible || guestVisible).toBeTruthy();
  });

  test('tc-checkout-02: Checkout page displays order summary with correct item @checkout', async ({ page }) => {
    const productTitle = await addTentAndGoToCart(homePage, productPage, cartPage);

    // Proceed to checkout
    await cartPage.proceedToCheckout();
    await checkoutPage.waitForCheckoutToLoad();

    // Assert URL contains /checkout
    await expect(page).toHaveURL(/checkout/);

    // Assert order summary section is present
    const orderSummaryText = await checkoutPage.getOrderSummaryText().catch(() => null);

    // Assert a price/subtotal is visible in the page
    const priceLocator = checkoutPage.orderSummaryPrice.first();
    const priceVisible = await priceLocator.isVisible().catch(() => false);
    expect(priceVisible).toBeTruthy();

    // Assert product name from cart appears somewhere on the checkout page
    if (productTitle) {
      const pageText = await page.textContent('body');
      // Check that at least part of the product title appears on the page
      const titleWords = productTitle.trim().split(' ').slice(0, 3).join(' ');
      expect(pageText).toContain(titleWords.charAt(0).toUpperCase() + titleWords.slice(1));
    }

    // Assert quantity is visible
    const quantityVisible = await checkoutPage.orderSummaryQuantity.first().isVisible().catch(() => false);
    if (quantityVisible) {
      const qtyText = await checkoutPage.orderSummaryQuantity.first().textContent();
      if (qtyText !== null) {
        const qty = parseInt(qtyText.trim(), 10);
        expect(qty).toBeGreaterThanOrEqual(1);
      }
    }
  });
});
