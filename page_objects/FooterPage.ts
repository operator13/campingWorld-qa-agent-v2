import { type Page, type Locator } from '@playwright/test';

export class FooterPage {
  readonly page: Page;

  // Footer container
  readonly footer: Locator;

  // Common footer links
  readonly privacyPolicyLink: Locator;
  readonly termsOfUseLink: Locator;
  readonly accessibilityLink: Locator;
  readonly doNotSellLink: Locator;
  readonly contactUsLink: Locator;
  readonly careersLink: Locator;
  readonly aboutUsLink: Locator;

  // Social links — no accessible names; target by href
  readonly facebookLink: Locator;
  readonly instagramLink: Locator;
  readonly youtubeLink: Locator;
  readonly twitterLink: Locator;
  readonly pinterestLink: Locator;

  // Privacy policy page elements (at /privacy-policy)
  readonly legalHeading: Locator;
  readonly legalContentBody: Locator;
  readonly lastUpdatedText: Locator;

  constructor(page: Page) {
    this.page = page;

    // Footer landmark
    this.footer = page.getByRole('contentinfo');

    // Footer navigation links — inside contentinfo
    this.privacyPolicyLink = page.getByRole('contentinfo').getByRole('link', { name: /privacy policy/i });
    this.termsOfUseLink = page.getByRole('contentinfo').getByRole('link', { name: /terms of use/i });
    this.accessibilityLink = page.getByRole('contentinfo').getByRole('link', { name: /accessibility/i });
    this.doNotSellLink = page.getByRole('contentinfo').locator('a').filter({ hasText: /do not sell|privacy choices|your privacy/i }).first();
    this.contactUsLink = page.getByRole('contentinfo').getByRole('link', { name: /contact us/i });
    this.careersLink = page.getByRole('contentinfo').getByRole('link', { name: /careers/i });
    this.aboutUsLink = page.getByRole('contentinfo').getByRole('link', { name: /about us/i });

    // Social links by href (no accessible names on these links)
    this.facebookLink = page.locator('a[href*="facebook"]').first();
    this.instagramLink = page.locator('a[href*="instagram"]').first();
    this.youtubeLink = page.locator('a[href*="youtube"]').first();
    this.twitterLink = page.locator('a[href*="twitter"], a[href*="x.com"]').first();
    this.pinterestLink = page.locator('a[href*="pinterest"]').first();

    // Privacy policy page content
    this.legalHeading = page.getByRole('main').getByRole('heading').first();
    this.legalContentBody = page.getByRole('main');
    this.lastUpdatedText = page.getByText(/last updated|effective date|revised/i).first();
  }

  async navigate() {
    // Navigate to homepage which has the footer
    await this.page.goto('/');
  }

  async navigateToPrivacyPolicy() {
    await this.page.goto('/privacy-policy');
  }

  async clickPrivacyPolicy() {
    await this.privacyPolicyLink.click();
  }

  async clickTermsOfUse() {
    await this.termsOfUseLink.click();
  }

  async clickContactUs() {
    await this.contactUsLink.click();
  }
}
