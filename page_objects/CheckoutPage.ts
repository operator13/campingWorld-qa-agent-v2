import { type Page, type Locator } from '@playwright/test';

export class CheckoutPage {
  readonly page: Page;
  readonly checkoutHeading: Locator;
  readonly emailInput: Locator;
  readonly guestCheckoutOption: Locator;
  readonly signInPrompt: Locator;
  readonly orderSummary: Locator;
  readonly orderSummaryItemName: Locator;
  readonly orderSummaryPrice: Locator;
  readonly orderSummaryQuantity: Locator;
  readonly placeOrderButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.checkoutHeading = page.getByTestId('checkout-heading');
    this.emailInput = page.getByTestId('checkout-email');
    // Guest checkout / sign-in options
    this.guestCheckoutOption = page.getByRole('button', { name: /guest/i }).or(
      page.getByRole('link', { name: /guest/i })
    );
    this.signInPrompt = page.getByRole('heading', { name: /sign in/i }).or(
      page.getByText(/sign in/i)
    );
    // Order summary section
    this.orderSummary = page.getByRole('region', { name: /order summary/i }).or(
      page.getByText(/order summary/i).locator('..')
    );
    this.orderSummaryItemName = page.getByTestId('cart-item-name').or(
      page.getByRole('cell', { name: /tent/i })
    );
    this.orderSummaryPrice = page.getByTestId('cart-item-price').or(
      page.getByText(/\$[\d,.]+/)
    );
    this.orderSummaryQuantity = page.getByTestId('cart-item-quantity');
    // Avoid drifted 'Submit' — use 'Place Order'
    this.placeOrderButton = page.getByRole('button', { name: 'Place Order' });
  }

  async navigate() {
    await this.page.goto('https://www.campingworld.com/checkout');
  }

  async waitForCheckoutToLoad() {
    await this.page.waitForURL(/checkout/, { timeout: 15000 });
    // Wait for either the heading, sign-in prompt, or email input
    await Promise.race([
      this.checkoutHeading.waitFor({ state: 'visible', timeout: 15000 }),
      this.signInPrompt.first().waitFor({ state: 'visible', timeout: 15000 }),
      this.emailInput.waitFor({ state: 'visible', timeout: 15000 }),
    ]);
  }

  async fillEmail(email: string) {
    await this.emailInput.fill(email);
  }

  async isCheckoutPageVisible(): Promise<boolean> {
    const url = this.page.url();
    return url.includes('/checkout');
  }

  async getOrderSummaryText(): Promise<string | null> {
    return await this.orderSummary.textContent();
  }
}
