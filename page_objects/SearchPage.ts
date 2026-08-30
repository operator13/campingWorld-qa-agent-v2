import { type Page, type Locator } from '@playwright/test';

export class SearchResultsPage {
  readonly page: Page;
  readonly productCards: Locator;
  readonly firstProductCard: Locator;
  readonly firstProductLink: Locator;

  constructor(page: Page) {
    this.page = page;
    // Prefer known testid 'product-card' from memory
    this.productCards = page.getByTestId('product-card');
    this.firstProductCard = page.getByTestId('product-card').first();
    this.firstProductLink = page.getByTestId('product-card').first().getByRole('link');
  }

  async waitForResults() {
    await this.page.waitForLoadState('domcontentloaded');
  }

  async getProductCount(): Promise<number> {
    return this.productCards.count();
  }

  async getFirstProductName(): Promise<string> {
    // Try heading inside card, then any link text
    const heading = this.firstProductCard.getByRole('heading');
    if (await heading.isVisible().catch(() => false)) {
      return heading.innerText();
    }
    return this.firstProductCard.getByRole('link').first().innerText();
  }

  async getFirstProductPrice(): Promise<string> {
    return this.firstProductCard.getByText(/\$[\d,]+\.\d{2}/).first().innerText();
  }

  async clickFirstProduct() {
    const link = this.firstProductCard.getByRole('link').first();
    await link.click();
  }

  async getNoResultsMessage(): Promise<Locator> {
    // Common no-results patterns
    const byText = this.page.getByText(/no results|0 results|no products found|did not match/i);
    return byText;
  }

  async hasErrorMessage(): Promise<boolean> {
    const error = this.page.getByText(/error|something went wrong|500/i);
    return error.isVisible().catch(() => false);
  }

  async getAllProductTitles(): Promise<string[]> {
    const count = await this.productCards.count();
    const titles: string[] = [];
    for (let i = 0; i < count; i++) {
      const card = this.productCards.nth(i);
      const heading = card.getByRole('heading');
      if (await heading.isVisible().catch(() => false)) {
        titles.push(await heading.innerText());
      } else {
        const link = card.getByRole('link').first();
        if (await link.isVisible().catch(() => false)) {
          titles.push(await link.innerText());
        }
      }
    }
    return titles;
  }
}
