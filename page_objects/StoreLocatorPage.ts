import { type Page, type Locator } from '@playwright/test';

export class StoreLocatorPage {
  readonly page: Page;

  // Page heading
  readonly pageHeading: Locator;

  // Location search
  readonly locationInput: Locator;

  // Controls
  readonly viewFiltersButton: Locator;
  readonly viewStateDirectoryLink: Locator;

  // Map
  readonly mapRegion: Locator;

  // Featured dealerships
  readonly featuredHeading: Locator;

  // RV site header
  readonly searchRvsInput: Locator;
  readonly storeLocatorLink: Locator;

  constructor(page: Page) {
    this.page = page;

    this.pageHeading = page.getByRole('heading', { name: /find a rv dealership location/i, level: 1 });

    // The location input — second combobox on the page (first is the label wrapper)
    this.locationInput = page.getByRole('combobox').nth(1);

    this.viewFiltersButton = page.getByRole('button', { name: /view filters/i });
    this.viewStateDirectoryLink = page.getByRole('link', { name: /view state directory/i });

    this.mapRegion = page.getByRole('region', { name: /map/i });

    this.featuredHeading = page.getByText(/featured dealership/i);

    // RV subdomain header
    this.searchRvsInput = page.getByRole('searchbox', { name: /search rvs/i });
    this.storeLocatorLink = page.getByText('Store Locator').first();
  }

  async navigate() {
    await this.page.goto('https://rv.campingworld.com/locations');
  }
}
