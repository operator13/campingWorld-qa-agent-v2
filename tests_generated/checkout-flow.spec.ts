import { test, expect, type Page } from '@playwright/test';
import { HomePage } from '../page-objects/HomePage';
import { SearchResultsPage } from '../page-objects/SearchResultsPage';
import { ProductDetailPage } from '../page-objects/ProductDetailPage';
import { CartPage } from '../page-objects/CartPage';
import { CheckoutPage } from '../page-objects/CheckoutPage';

/**
 * Helper: adds a product to the cart from the home page search.
 * Returns the product title that was added.
 */
async function addProductToCart(page: Page, searchTerm = 'tent'): Promise<string> {
  const homePage = new HomePage(page);
  const searchResults = new SearchResultsPage(page);
  const productDetail = new ProductDetailPage(page);

  await homePage.navigate();
  await homePage.searchFor(searchTerm);

  // Wait for search results to load
  await page.waitForLoadState('domcontentloaded');
  await searchResults.clickFirstProduct();

  // Wait for PDP to load
  await page.waitForLoadState('domcontentloaded');

  const productTitle = await productDetail.getProductTitle();

  await productDetail.addToCart();
  await productDetail.waitForCartConfirmation();

  return productTitle.trim();
}

test.describe('Checkout Flow — Camping World', () => {
  // ─────────────────────────────────────────────────────────────
  // tc-checkout-01: Add item to cart from product page
  // ─────────────────────────────────────────────────────────────
  test.describe('Cart', () => {
    test(
      'tc-checkout-01: User can add an item to the cart from a product page @smoke @cart @checkout-flow',
      async ({ page }) => {
        const homePage = new HomePage(page);
        const searchResults = new SearchResultsPage(page);
        const productDetail = new ProductDetailPage(page);

        // Step 1: Navigate to Camping World
        await homePage.navigate();
        await expect(page).toHaveURL(/campingworld\.com/);

        // Step 2: Search for a product
        await homePage.searchFor('tent');
        await page.waitForLoadState('domcontentloaded');

        // Step 3: Click the first product result
        await searchResults.clickFirstProduct();
        await page.waitForLoadState('domcontentloaded');

        // Capture product title before adding to cart
        const productTitle = await productDetail.getProductTitle();
        expect(productTitle.length).toBeGreaterThan(0);

        // Step 4: Verify 'Add to Cart' button is visible
        await expect(productDetail.addToCartButton).toBeVisible({ timeout: 10000 });

        // Step 5 & 6: Click 'Add to Cart'
        await productDetail.addToCart();

        // Step 7: Wait for cart confirmation feedback
        await productDetail.waitForCartConfirmation();

        // Assertion: A confirmation message/modal/toast is displayed
        const confirmationLocator = page.locator(
          '[class*="modal"], [class*="toast"], [class*="alert"], [role="dialog"], [role="alert"]'
        ).filter({ hasText: /added|cart|success/i }).first();

        // Also check for cart counter update or URL change as fallback signals
        const cartCounterLocator = page
          .getByTestId('cart-count')
          .or(page.locator('[aria-label*="cart"]').filter({ hasText: /[1-9]/ }))
          .or(page.locator('[class*="cart"][class*="count"]'));

        // At least one of: confirmation UI visible OR cart counter > 0
        const confirmationVisible = await confirmationLocator
          .isVisible()
          .catch(() => false);
        const cartCounterVisible = await cartCounterLocator
          .first()
          .isVisible()
          .catch(() => false);

        expect(
          confirmationVisible || cartCounterVisible,
          'Expected either a cart confirmation message or an updated cart counter to be visible'
        ).toBe(true);
      }
    );
  });

  // ─────────────────────────────────────────────────────────────
  // tc-checkout-02: View cart and proceed to checkout
  // ─────────────────────────────────────────────────────────────
  test.describe('Checkout', () => {
    test(
      'tc-checkout-02: User can view cart and proceed to checkout @smoke @checkout @checkout-flow',
      async ({ page }) => {
        const homePage = new HomePage(page);
        const cartPage = new CartPage(page);
        const checkoutPage = new CheckoutPage(page);

        // Prerequisite: Add an item to the cart (tc-checkout-01 flow)
        const addedProductTitle = await addProductToCart(page, 'tent');

        // Step 2: Click the cart icon to navigate to the cart page
        await homePage.clickCartIcon();
        await page.waitForLoadState('domcontentloaded');

        // Step 3: Verify cart page URL
        await expect(page).toHaveURL(/\/cart|\/checkout\/cart/i, { timeout: 10000 });

        // Step 4: Confirm the added item is listed in the cart
        const itemCount = await cartPage.getCartItemCount();
        expect(itemCount, 'Cart should contain at least one item').toBeGreaterThan(0);

        // Verify item name is visible somewhere on the cart page
        if (addedProductTitle) {
          // Use a partial match in case the title is truncated
          const titleWords = addedProductTitle.split(' ').slice(0, 3).join(' ');
          const itemNameLocator = page.getByText(new RegExp(titleWords, 'i'));
          await expect(itemNameLocator.first()).toBeVisible({ timeout: 8000 });
        }

        // Verify price is visible
        await expect(cartPage.cartItemPrices.first()).toBeVisible({ timeout: 8000 });

        // Step 5 & 6: Locate and click 'Proceed to Checkout'
        await expect(cartPage.proceedToCheckoutButton.first()).toBeVisible({ timeout: 8000 });
        await cartPage.proceedToCheckout();

        // Step 7: Wait for navigation to checkout page
        await page.waitForLoadState('domcontentloaded');

        // Assertion: URL matches a checkout pattern
        await expect(page).toHaveURL(
          /\/checkout|\/checkout\/login|\/checkout\/shipping|\/checkout\/cart/i,
          { timeout: 15000 }
        );

        // Assertion: Checkout page loads without errors (no 5xx page)
        const pageContent = await page.content();
        expect(pageContent).not.toMatch(/500|internal server error|something went wrong/i);

        // Assertion: Some checkout-related heading or content is visible
        const checkoutHeadingLocator = page
          .getByRole('heading', { name: /checkout|sign in|shipping|order/i })
          .or(page.getByText(/checkout|sign in|shipping address/i).first());
        await expect(checkoutHeadingLocator.first()).toBeVisible({ timeout: 10000 });
      }
    );
  });
});
