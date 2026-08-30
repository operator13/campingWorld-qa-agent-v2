import { type Page, type Locator } from '@playwright/test';

export class HomePage {
  readonly page: Page;
  readonly searchInput: Locator;
  readonly searchButton: Locator;

  constructor(page: Page) {
    this.page = page;
    // Prefer known testid 'search-input' from memory
    this.searchInput = page.getByTestId('search-input');
    // Fallback chain handled in actions via multiple strategies
    this.searchButton = page.getByRole('button', { name: /search/i });
  }

  async navigate() {
    await this.page.goto('https://www.campingworld.com', { waitUntil: 'domcontentloaded' });
  }

  async getSearchInput(): Promise<Locator> {
    // Try testid first (from memory), then role, then placeholder
    const byTestId = this.page.getByTestId('search-input');
    if (await byTestId.isVisible().catch(() => false)) return byTestId;
    const byRole = this.page.getByRole('searchbox');
    if (await byRole.isVisible().catch(() => false)) return byRole;
    return this.page.getByPlaceholder(/search/i);
  }

  async clickSearchInput() {
    const input = await this.getSearchInput();
    await input.click();
  }

  async typeSearchQuery(query: string) {
    const input = await this.getSearchInput();
    await input.fill(query);
  }

  async submitSearch() {
    const input = await this.getSearchInput();
    await input.press('Enter');
  }

  async searchFor(query: string) {
    await this.typeSearchQuery(query);
    await this.submitSearch();
  }

  async getSearchInputValue(): Promise<string> {
    const input = await this.getSearchInput();
    return input.inputValue();
  }
}
