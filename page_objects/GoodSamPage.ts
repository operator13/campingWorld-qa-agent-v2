import { type Page, type Locator } from '@playwright/test';

export class GoodSamPage {
  readonly page: Page;

  readonly pageHeading: Locator;
  readonly mainContent: Locator;
  readonly breadcrumb: Locator;
  readonly footer: Locator;

  constructor(page: Page) {
    this.page = page;

    this.pageHeading = page.getByRole('heading', { level: 1 });
    this.mainContent = page.getByRole('main');
    this.breadcrumb = page.getByRole('navigation', { name: /breadcrumb/i });
    this.footer = page.getByRole('contentinfo');
  }

  async navigate() {
    await this.page.goto('/good-sam');
  }
}
