import { type Page, type Locator } from '@playwright/test';

export class SignInPage {
  readonly page: Page;

  // Sign-in form elements
  readonly signInTab: Locator;
  readonly createAccountTab: Locator;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly signInButton: Locator;
  readonly forgotPasswordLink: Locator;
  readonly keepMeSignedInCheckbox: Locator;

  // Header
  readonly logo: Locator;

  constructor(page: Page) {
    this.page = page;

    // Tabs
    this.signInTab = page.getByRole('tab', { name: /sign in/i });
    this.createAccountTab = page.getByRole('tab', { name: /create account/i });

    // Form fields
    this.emailInput = page.getByRole('textbox', { name: /email address/i });
    this.passwordInput = page.getByRole('textbox', { name: /password/i });
    this.signInButton = page.getByRole('tabpanel').getByRole('button', { name: /sign in/i });
    this.forgotPasswordLink = page.getByRole('link', { name: /forgot password/i });
    this.keepMeSignedInCheckbox = page.getByRole('checkbox', { name: /keep me signed in/i });

    // Header
    this.logo = page.getByRole('link', { name: /camping world home/i });
  }

  async navigate() {
    await this.page.goto('/account-login', { timeout: 30_000 });
  }
}
