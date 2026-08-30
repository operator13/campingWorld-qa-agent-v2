import { type Page, type Locator } from '@playwright/test';

export class SearchPage {
  readonly page: Page;

  // Results
  readonly productLinks: Locator;
  readonly addToCartButtons: Locator;
  readonly productPrices: Locator;

  // Search box in header (can re-search)
  readonly searchInput: Locator;
  readonly searchButton: Locator;

  // Main content area
  readonly mainContent: Locator;

  constructor(page: Page) {
    this.page = page;

    // Product result links (product titles link to product pages)
    this.productLinks = page.getByRole('main').getByRole('link');

    // Add To Cart buttons on search result cards
    this.addToCartButtons = page.getByRole('button', { name: /add to cart/i });

    // Price text in results
    this.productPrices = page.getByText(/\$[\d,]+(\.\d{2})?/);

    // Header search
    this.searchInput = page.getByRole('searchbox', { name: /submit/i });
    this.searchButton = page.getByRole('button', { name: /submit/i }).first();

    // Main content
    this.mainContent = page.getByRole('main');
  }

  async navigate(query = 'tent') {
    await this.page.goto(`/search?q=${encodeURIComponent(query)}`);
    // Wait for Algolia search results to load
    await this.addToCartButtons.first().waitFor({ state: 'visible', timeout: 15_000 }).catch(() => {});
  }

  async search(query: string) {
    await this.searchInput.fill(query);
    await this.searchButton.click();
  }

  async getAddToCartCount(): Promise<number> {
    return await this.addToCartButtons.count();
  }
}
