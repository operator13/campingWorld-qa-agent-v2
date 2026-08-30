import { type Page, type Locator } from '@playwright/test';

export class HomepagePage {
  readonly page: Page;

  // Navigation
  readonly logo: Locator;
  readonly searchInput: Locator;
  readonly searchSubmitButton: Locator;
  readonly cartLink: Locator;
  readonly signInButton: Locator;
  readonly storeLocatorLink: Locator;
  readonly mainNav: Locator;
  readonly shopByCategoryButton: Locator;
  readonly dealsAndServicesButton: Locator;

  // Hero
  readonly heroBanner: Locator;
  readonly heroCtaButton: Locator;
  readonly heroHeading: Locator;

  // Main content
  readonly mainContent: Locator;
  readonly tabPanels: Locator;
  readonly shopAllLink: Locator;

  // Footer
  readonly footer: Locator;
  readonly footerLinks: Locator;
  readonly footerSocialLinks: Locator;

  constructor(page: Page) {
    this.page = page;

    // Navigation
    this.logo = page.getByRole('link', { name: /camping world home/i });
    this.searchInput = page.getByRole('searchbox', { name: /submit/i });
    this.searchSubmitButton = page.getByRole('button', { name: /submit/i }).first();
    this.cartLink = page.getByRole('link', { name: /cart/i });
    this.signInButton = page.getByRole('button', { name: /sign in/i });
    this.storeLocatorLink = page.getByRole('link', { name: /find a store/i });
    this.mainNav = page.getByRole('banner').getByRole('navigation').first();
    this.shopByCategoryButton = page.getByRole('button', { name: /shop by category/i });
    this.dealsAndServicesButton = page.getByRole('button', { name: /deals & services/i });

    // Hero
    this.heroBanner = page.getByRole('banner');
    this.heroCtaButton = page.getByRole('link', { name: /shop now/i });
    this.heroHeading = page.getByRole('heading', { level: 1 });

    // Main content
    this.mainContent = page.getByRole('main');
    this.tabPanels = page.getByRole('tabpanel');
    this.shopAllLink = page.getByRole('link', { name: /shop all/i }).first();

    // Footer
    this.footer = page.getByRole('contentinfo');
    this.footerLinks = page.getByRole('contentinfo').getByRole('link');
    this.footerSocialLinks = page.getByRole('contentinfo').locator('a[href*="facebook"], a[href*="twitter"], a[href*="youtube"], a[href*="instagram"], a[href*="tiktok"]');
  }

  async navigate() {
    await this.page.goto('/');
  }

  async search(query: string) {
    await this.searchInput.fill(query);
    await this.searchSubmitButton.click();
  }

  async searchAndPressEnter(query: string) {
    await this.searchInput.fill(query);
    await this.searchInput.press('Enter');
  }
}
