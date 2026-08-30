import { type Page, type Locator } from '@playwright/test';

export class RvPartsPage {
  readonly page: Page;

  // /rv-parts currently 404s — these locators target the 404 page
  readonly mainContent: Locator;
  readonly pageHeading: Locator;
  readonly logo: Locator;
  readonly searchInput: Locator;
  readonly footer: Locator;

  constructor(page: Page) {
    this.page = page;

    this.mainContent = page.getByRole('main');
    this.pageHeading = page.getByRole('heading').first();
    this.logo = page.getByRole('link', { name: /camping world home/i });
    this.searchInput = page.getByRole('searchbox', { name: /submit/i });
    this.footer = page.getByRole('contentinfo');
  }

  async navigate() {
    await this.page.goto('/rv-parts');
  }
}
