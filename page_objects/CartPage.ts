import { type Page, type Locator } from '@playwright/test';

export class CartPage {
  readonly page: Page;
  readonly cartItem: Locator;
  readonly cartItemName: Locator;
  readonly cartItemPrice: Locator;
  readonly cartItemQuantity: Locator;
  readonly checkoutButton: Locator;
  readonly subtotal: Locator;

  constructor(page: Page) {
    this.page = page;
    this.cartItem = page.getByTestId('cart-item');
    this.cartItemName = page.getByTestId('cart-item-name');
    this.cartItemPrice = page.getByTestId('cart-item-price');
    this.cartItemQuantity = page.getByTestId('cart-item-quantity');
    // Checkout button — try button first, then link
    this.checkoutButton = page.getByRole('button', { name: /checkout/i }).or(
      page.getByRole('link', { name: /checkout/i })
    );
    this.subtotal = page.getByText(/subtotal/i);
  }

  async navigate() {
    await this.page.goto('https://www.campingworld.com/cart');
  }

  async waitForCartToLoad() {
    await this.cartItem.first().waitFor({ state: 'visible', timeout: 15000 });
  }

  async proceedToCheckout() {
    await this.checkoutButton.first().waitFor({ state: 'visible', timeout: 10000 });
    await this.checkoutButton.first().click();
  }

  async getFirstItemName(): Promise<string | null> {
    await this.cartItemName.first().waitFor({ state: 'visible', timeout: 10000 });
    return await this.cartItemName.first().textContent();
  }

  async getFirstItemQuantity(): Promise<string | null> {
    await this.cartItemQuantity.first().waitFor({ state: 'visible', timeout: 10000 });
    return await this.cartItemQuantity.first().textContent();
  }
}
