import { type Page, type Locator } from '@playwright/test';

export class CheckoutPage {
  readonly page: Page;

  // When cart is empty, /checkout redirects to /cart
  // These locators target the empty cart redirect state
  readonly emptyCartHeading: Locator;
  readonly cartLink: Locator;
  readonly addToCartButtons: Locator;
  readonly mainContent: Locator;

  constructor(page: Page) {
    this.page = page;

    // /checkout redirects to /cart when cart is empty
    this.emptyCartHeading = page.getByRole('heading', { name: /your shopping cart is empty/i, level: 3 });
    this.cartLink = page.getByRole('link', { name: /cart/i });
    this.addToCartButtons = page.getByRole('button', { name: /add to cart/i });
    this.mainContent = page.getByRole('main');
  }

  async navigate() {
    await this.page.goto('/checkout');
  }
}
