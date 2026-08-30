import { type Page, type Locator } from '@playwright/test';

export class RegisterPage {
  readonly page: Page;

  // Tabs on the account-login page
  readonly signInTab: Locator;
  readonly createAccountTab: Locator;

  // Header
  readonly logo: Locator;
  readonly mainContent: Locator;

  constructor(page: Page) {
    this.page = page;

    this.signInTab = page.getByRole('tab', { name: /sign in/i });
    this.createAccountTab = page.getByRole('tab', { name: /create account/i });
    this.mainContent = page.getByRole('main');
    this.logo = page.getByRole('link', { name: /camping world home/i });
  }

  async navigate() {
    await this.page.goto('/account-login', { timeout: 30_000 });
  }

  async switchToCreateAccount() {
    await this.createAccountTab.click();
  }
}
