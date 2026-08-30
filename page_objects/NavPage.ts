import { type Page, type Locator } from '@playwright/test';

export class NavPage {
  readonly page: Page;

  // Header elements (from banner/navigation)
  readonly logo: Locator;
  readonly searchInput: Locator;
  readonly searchButton: Locator;
  readonly signInButton: Locator;
  readonly cartLink: Locator;
  readonly storeLocatorLink: Locator;
  readonly mainNav: Locator;

  // Top-level nav buttons that trigger mega menus
  readonly shopByCategoryButton: Locator;
  readonly dealsAndServicesButton: Locator;

  constructor(page: Page) {
    this.page = page;

    // Logo
    this.logo = page.getByRole('link', { name: /camping world home/i });

    // Search
    this.searchInput = page.getByRole('searchbox', { name: /submit/i });
    this.searchButton = page.getByRole('button', { name: /submit/i }).first();

    // Sign in button (not a link — opens modal)
    this.signInButton = page.getByRole('button', { name: /sign in/i });

    // Cart link
    this.cartLink = page.getByRole('link', { name: /cart/i });

    // Find a Store link
    this.storeLocatorLink = page.getByRole('link', { name: /find a store/i });

    // Navigation inside banner
    this.mainNav = page.getByRole('banner').getByRole('navigation').first();

    // Mega menu trigger buttons in nav
    this.shopByCategoryButton = page.getByRole('button', { name: /shop by category/i });
    this.dealsAndServicesButton = page.getByRole('button', { name: /deals & services/i });
  }

  async navigate() {
    await this.page.goto('/');
  }

  async search(query: string) {
    await this.searchInput.fill(query);
    await this.searchButton.click();
  }

  async openShopByCategory() {
    await this.shopByCategoryButton.click();
  }

  async openDealsAndServices() {
    await this.dealsAndServicesButton.click();
  }

  async navigateToCart() {
    await this.cartLink.click();
  }

  async navigateToStoreLocator() {
    await this.storeLocatorLink.click();
  }
}
