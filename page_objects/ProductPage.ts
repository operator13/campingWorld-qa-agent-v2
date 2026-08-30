import { type Page, type Locator } from '@playwright/test';

export class ProductPage {
  readonly page: Page;
  readonly addToCartButton: Locator;
  readonly productTitle: Locator;
  readonly cartConfirmationModal: Locator;
  readonly cartConfirmationToast: Locator;

  constructor(page: Page) {
    this.page = page;
    this.addToCartButton = page.getByRole('button', { name: /add to cart/i });
    this.productTitle = page.getByRole('heading', { level: 1 });
    // Cart confirmation feedback — modal or toast
    this.cartConfirmationModal = page.getByRole('dialog');
    this.cartConfirmationToast = page.getByRole('alert');
  }

  async addToCart() {
    await this.addToCartButton.waitFor({ state: 'visible', timeout: 10000 });
    await this.addToCartButton.click();
  }

  async getProductTitle(): Promise<string | null> {
    await this.productTitle.waitFor({ state: 'visible', timeout: 10000 });
    return await this.productTitle.textContent();
  }

  async waitForCartConfirmation() {
    // Wait for either a modal dialog or an alert/toast to appear
    await Promise.race([
      this.cartConfirmationModal.waitFor({ state: 'visible', timeout: 10000 }),
      this.cartConfirmationToast.waitFor({ state: 'visible', timeout: 10000 }),
    ]);
  }
}
