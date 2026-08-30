import { test, expect } from './fixtures';
import { ProductPage } from '../page_objects/ProductPage';

// Use a stable product .html URL from campingworld.com
const PRODUCT_PATH = '/wenzel-bristlecone-8-person-dome-tent-761437.html';

test.describe('Product Detail Page', () => {
  let productPage: ProductPage;

  test.beforeEach(async ({ page }) => {
    productPage = new ProductPage(page);
    await productPage.navigate(PRODUCT_PATH);
  });

  test('product page loads with main content', async () => {
    await expect(productPage.mainContent).toBeVisible();
  });

  test('product title heading is visible', async () => {
    await productPage.productTitle.scrollIntoViewIfNeeded();
    await expect(productPage.productTitle).toBeVisible({ timeout: 15_000 });
  });

  test('product title is not empty', async () => {
    await productPage.productTitle.scrollIntoViewIfNeeded();
    const title = await productPage.getProductTitleText();
    expect(title.trim()).not.toBe('');
  });

  test('product price is displayed in main content', async () => {
    await expect(productPage.productPrice).toBeVisible();
  });

  test('product price matches dollar format', async () => {
    const priceText = await productPage.getPriceText();
    expect(priceText).toMatch(/\$[\d,]+\.\d{2}/);
  });

  test('add to cart button is visible', async () => {
    await productPage.addToCartButton.waitFor({ state: 'visible', timeout: 20_000 });
    await productPage.addToCartButton.scrollIntoViewIfNeeded();
    await expect(productPage.addToCartButton).toBeVisible();
  });

  test('add to cart button is enabled', async () => {
    await productPage.addToCartButton.waitFor({ state: 'visible', timeout: 20_000 });
    await productPage.addToCartButton.scrollIntoViewIfNeeded();
    await expect(productPage.addToCartButton).toBeEnabled();
  });

  test('primary product image is visible', async () => {
    await expect(productPage.primaryProductImage).toBeVisible();
  });

  test('product SKU reference is on the page', async () => {
    await expect(productPage.productSku).toBeVisible();
  });
});
