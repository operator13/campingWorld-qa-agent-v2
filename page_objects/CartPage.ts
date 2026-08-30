import { type Page, type Locator } from '@playwright/test';

export class CartPage {
  readonly page: Page;

  // Empty State
  readonly emptyCartHeading: Locator;

  // Top Picks carousel (visible on empty cart)
  readonly addToCartButtons: Locator;

  // Header elements reachable from cart
  readonly cartLink: Locator;
  readonly logo: Locator;

  constructor(page: Page) {
    this.page = page;

    // Empty State — heading level 3 per live site
    this.emptyCartHeading = page.getByRole('heading', { name: /your shopping cart is empty/i, level: 3 });

    // Top Picks carousel "Add To Cart" buttons present on empty cart page
    this.addToCartButtons = page.getByRole('button', { name: /add to cart/i });

    // Standard header elements
    this.cartLink = page.getByRole('link', { name: /cart/i });
    this.logo = page.getByRole('link', { name: /camping world home/i });
  }

  async navigate() {
    await this.page.goto('/cart');
  }

  async isCartEmpty(): Promise<boolean> {
    // Try the heading first, fall back to any text containing "empty" on the page
    const headingVisible = await this.emptyCartHeading.isVisible().catch(() => false);
    if (headingVisible) return true;
    const emptyText = this.page.getByText(/shopping cart is empty/i).first();
    return await emptyText.isVisible().catch(() => false);
  }
}
