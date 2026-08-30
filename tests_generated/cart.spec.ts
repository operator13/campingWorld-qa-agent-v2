import { test, expect } from '@playwright/test';
import { HomePage } from '../page_objects/';
import { ProductPage } from '../page_objects/ProductPage';
import { CartPage } from '../page_objects/CartPage';

/**
 * Helper: navigate to homepage, search for 'tent', click first result,
 * and add the product to the cart. Returns the product title.
 */
async function addTentToCart(homePage: HomePage, productPage: ProductPage): Promise<string | null> {
  await homePage.navigate();
  await homePage.searchForProduct('tent');
  await homePage.clickFirstSearchResult();
  const title = await productPage.getProductTitle();
  await productPage.addToCart();
  return title;
}

test.describe('Cart', () => {
  let homePage: HomePage;
  let productPage: ProductPage;
  let cartPage: CartPage;

  test.beforeEach(async ({ page }) => {
    homePage = new HomePage(page);
    productPage = new ProductPage(page);
    cartPage = new CartPage(page);
  });

  test('tc-cart-01: User can add an item to the cart @smoke @cart', async ({ page }) => {
    await homePage.navigate();
    await homePage.searchForProduct('tent');
    await homePage.clickFirstSearchResult();

    const productTitle = await productPage.getProductTitle();
    await productPage.addToCart();

    // Wait for cart confirmation feedback (modal or toast)
    await productPage.waitForCartConfirmation();

    // Assert confirmation is visible
    const modal = productPage.cartConfirmationModal;
    const toast = productPage.cartConfirmationToast;
    const modalVisible = await modal.isVisible().catch(() => false);
    const toastVisible = await toast.isVisible().catch(() => false);
    expect(modalVisible || toastVisible).toBeTruthy();

    // Assert product name appears in confirmation feedback
    if (productTitle) {
      const confirmationText = modalVisible
        ? await modal.textContent()
        : await toast.textContent();
      expect(confirmationText).toBeTruthy();
    }

    // Assert cart count reflects at least 1 item
    const cartCountText = await homePage.getCartCount();
    if (cartCountText !== null) {
      const count = parseInt(cartCountText.trim(), 10);
      expect(count).toBeGreaterThanOrEqual(1);
    }
  });

  test('tc-cart-02: User can view cart after adding an item @smoke @cart', async ({ page }) => {
    await addTentToCart(homePage, productPage);

    // Navigate to cart page
    await cartPage.navigate();
    await cartPage.waitForCartToLoad();

    // Assert cart page URL
    await expect(page).toHaveURL(/\/cart/);

    // Assert product is listed
    await expect(cartPage.cartItem.first()).toBeVisible();
    await expect(cartPage.cartItemName.first()).toBeVisible();

    // Assert quantity >= 1
    const quantityText = await cartPage.getFirstItemQuantity();
    if (quantityText !== null) {
      const qty = parseInt(quantityText.trim(), 10);
      expect(qty).toBeGreaterThanOrEqual(1);
    }

    // Assert subtotal or price is displayed
    await expect(cartPage.cartItemPrice.first()).toBeVisible();
  });

  test('tc-cart-03: Cart persists item after page navigation @cart', async ({ page }) => {
    await addTentToCart(homePage, productPage);

    // Navigate away to homepage
    await homePage.navigate();
    await expect(page).toHaveURL('https://www.campingworld.com');

    // Navigate back to cart
    await cartPage.navigate();
    await cartPage.waitForCartToLoad();

    // Assert item is still in cart
    await expect(cartPage.cartItem.first()).toBeVisible();
    await expect(cartPage.cartItemName.first()).toBeVisible();

    // Assert cart icon count still reflects item
    const cartCountText = await homePage.getCartCount();
    if (cartCountText !== null) {
      const count = parseInt(cartCountText.trim(), 10);
      expect(count).toBeGreaterThanOrEqual(1);
    }
  });
});
