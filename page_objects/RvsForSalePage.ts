import { type Page, type Locator } from '@playwright/test';

export class RvsForSalePage {
  readonly page: Page;

  // Page heading
  readonly pageHeading: Locator;

  // Main content / results area
  readonly mainContent: Locator;

  // Listing cards — RV listings on rv.campingworld.com/rvs-for-sale
  readonly listingCards: Locator;

  // Results count text
  readonly resultsCount: Locator;

  // Listing card elements
  readonly listingCardPrices: Locator;
  readonly listingCardTitles: Locator;
  readonly listingCardImages: Locator;

  // Navigation header elements on rv subdomain
  readonly searchRvsInput: Locator;
  readonly shopRvsButton: Locator;
  readonly storeLocatorLink: Locator;

  // Pagination
  readonly nextPageButton: Locator;
  readonly previousPageButton: Locator;

  // Sort
  readonly sortBySelect: Locator;

  constructor(page: Page) {
    this.page = page;

    this.pageHeading = page.getByRole('heading').first();
    this.mainContent = page.getByRole('main');

    // RV listing cards — use links to RV detail pages as the card proxy
    this.listingCards = page.locator('a[href*="/rv/"]');

    // Results count
    this.resultsCount = page.getByText(/\d+\s*(rv|result|listing)/i).first();

    // Prices inside listing area
    this.listingCardPrices = page.getByRole('main').locator(':visible').filter({ hasText: /\$[\d,]+/ }).first();

    // Headings inside listing area (RV titles)
    this.listingCardTitles = page.getByRole('main').getByRole('heading').first();

    // Images inside listing area
    this.listingCardImages = page.getByRole('main').getByRole('img').first();

    // RV subdomain header — broaden locators
    this.searchRvsInput = page.getByRole('searchbox').first();
    this.shopRvsButton = page.getByRole('button', { name: /shop rvs/i });
    this.storeLocatorLink = page.getByText('Store Locator').first();

    // Pagination
    this.nextPageButton = page.getByRole('button', { name: /next/i });
    this.previousPageButton = page.getByRole('button', { name: /previous|prev/i });

    // Sort
    this.sortBySelect = page.getByRole('combobox', { name: /sort/i });
  }

  async navigate() {
    await this.page.goto('https://rv.campingworld.com/rvs-for-sale');
  }

  async getListingCount(): Promise<number> {
    return await this.listingCards.count();
  }

  async clickFirstListing() {
    await this.listingCards.first().click();
  }
}
