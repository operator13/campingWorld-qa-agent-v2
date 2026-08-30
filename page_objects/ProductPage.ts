import { type Page, type Locator } from '@playwright/test';

export class ProductPage {
  readonly page: Page;

  // Product Title
  readonly productTitle: Locator;

  // Pricing
  readonly productPrice: Locator;

  // Add to Cart
  readonly addToCartButton: Locator;

  // Image
  readonly primaryProductImage: Locator;

  // Reviews section
  readonly reviewsSection: Locator;
  readonly totalReviewCount: Locator;
  readonly writeReviewButton: Locator;

  // Availability / shipping
  readonly availabilityStatus: Locator;
  readonly shippingInfo: Locator;

  // SKU
  readonly productSku: Locator;

  // Main content
  readonly mainContent: Locator;

  constructor(page: Page) {
    this.page = page;

    // H1 product title — first h1 in main content (there's also a Q&A h1)
    this.productTitle = page.locator('h1.product-name').first();

    // Price text in main content
    this.productPrice = page.getByRole('main').getByText(/\$[\d,]+\.\d{2}/).first();

    // Add to cart button — the main one in the qty-cart-container (not related products)
    this.addToCartButton = page.locator('#qty-cart-container').getByRole('button', { name: /add to cart/i });

    // Primary product image
    this.primaryProductImage = page.getByRole('main').getByRole('img').first();

    // Reviews section — look for a region or section containing "reviews"
    this.reviewsSection = page.getByRole('region', { name: /reviews/i });
    this.totalReviewCount = page.getByText(/\d+\s+review/i).first();
    this.writeReviewButton = page.getByRole('button', { name: /write a review/i });

    // Availability and shipping
    this.availabilityStatus = page.getByText(/in stock|out of stock|available/i).first();
    this.shippingInfo = page.getByText(/free shipping|ships/i).first();

    // SKU — may be labeled as "SKU", "Item #", or "Item Number"
    this.productSku = page.getByText(/sku|item\s*#|item\s*number/i).first();

    // Main content
    this.mainContent = page.getByRole('main');
  }

  async navigate(productPath: string) {
    await this.page.goto(productPath);
  }

  async addToCart() {
    await this.addToCartButton.click();
  }

  async getProductTitleText(): Promise<string> {
    return (await this.productTitle.textContent()) ?? '';
  }

  async getPriceText(): Promise<string> {
    return (await this.productPrice.textContent()) ?? '';
  }

  async isAddToCartEnabled(): Promise<boolean> {
    return this.addToCartButton.isEnabled();
  }
}
