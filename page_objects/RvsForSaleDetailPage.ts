import { type Page, type Locator } from '@playwright/test';

export class RvsForSaleDetailPage {
  readonly page: Page;

  // RV Title
  readonly rvTitle: Locator;

  // Pricing
  readonly rvPrice: Locator;
  readonly msrpText: Locator;
  readonly monthlyPaymentText: Locator;

  // Specs text
  readonly rvCondition: Locator;
  readonly rvLength: Locator;
  readonly rvSleeps: Locator;
  readonly rvSlideouts: Locator;

  // Images
  readonly mainImage: Locator;

  // Dealer Info
  readonly dealerName: Locator;
  readonly dealerPhone: Locator;

  // Contact CTAs
  readonly requestMoreInfoButton: Locator;
  readonly getEQuoteButton: Locator;
  readonly applyForFinancingLink: Locator;

  // Contact form inputs
  readonly firstNameInput: Locator;
  readonly lastNameInput: Locator;
  readonly emailInput: Locator;
  readonly phoneInput: Locator;
  readonly submitContactButton: Locator;

  // Main content
  readonly mainContent: Locator;

  // RV subdomain header
  readonly searchRvsInput: Locator;
  readonly storeLocatorLink: Locator;

  constructor(page: Page) {
    this.page = page;

    // H1 RV title
    this.rvTitle = page.getByRole('heading', { level: 1 });

    // Pricing
    this.rvPrice = page.getByRole('main').locator(':visible').filter({ hasText: /\$[\d,]+/ }).first();
    this.msrpText = page.getByText(/msrp/i).first();
    this.monthlyPaymentText = page.getByText(/per month|\/mo/i).first();

    // Specs
    this.rvCondition = page.getByText(/condition|buy new|buy pre-owned|buy used/i).first();
    this.rvLength = page.getByText(/length/i).first();
    this.rvSleeps = page.getByText(/sleeps/i).first();
    this.rvSlideouts = page.getByText(/slideout/i).first();

    // Main image
    this.mainImage = page.getByRole('main').getByRole('img').first();

    // Dealer info
    this.dealerName = page.getByText(/camping world/i).first();
    this.dealerPhone = page.getByRole('link', { name: /\(\d{3}\)/i }).first();

    // CTA buttons
    this.requestMoreInfoButton = page.getByRole('button', { name: /request more info|get more info/i });
    this.getEQuoteButton = page.getByRole('button', { name: /e.quote|equote/i });
    this.applyForFinancingLink = page.getByRole('link', { name: /apply for financing/i });

    // Contact form
    this.firstNameInput = page.getByRole('textbox', { name: /first name/i });
    this.lastNameInput = page.getByRole('textbox', { name: /last name/i });
    this.emailInput = page.getByRole('textbox', { name: /email/i });
    this.phoneInput = page.getByRole('textbox', { name: /phone/i });
    this.submitContactButton = page.getByRole('button', { name: /submit|send/i });

    // Main content
    this.mainContent = page.getByRole('main');

    // RV subdomain header — broaden locators
    this.searchRvsInput = page.getByRole('searchbox').first();
    this.storeLocatorLink = page.getByText('Store Locator').first();
  }

  async navigate() {
    // Go to listings and click the first RV to get a valid detail page
    await this.page.goto('https://rv.campingworld.com/rvs-for-sale');
    const firstRvLink = this.page.locator('a[href*="/rv/"]').first();
    await firstRvLink.waitFor({ state: 'visible', timeout: 15_000 });
    await firstRvLink.click();
    await this.page.waitForURL(/\/rv\//, { timeout: 30_000 });
  }

  async navigateDirect(slug: string) {
    await this.page.goto(`https://rv.campingworld.com/rv/${slug}`);
  }
}
