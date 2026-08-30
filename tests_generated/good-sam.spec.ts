import { test, expect } from './fixtures';
import { GoodSamPage } from '../page_objects/GoodSamPage';

test.describe('Good Sam Club', () => {
  let goodSamPage: GoodSamPage;

  test.beforeEach(async ({ page }) => {
    goodSamPage = new GoodSamPage(page);
    await goodSamPage.navigate();
  });

  test('Good Sam page loads at /good-sam URL', async ({ page }) => {
    await expect(page).toHaveURL(/\/good-sam/i);
  });

  test('main content area is visible', async () => {
    await expect(goodSamPage.mainContent).toBeVisible();
  });

  test('page has a heading', async () => {
    await expect(goodSamPage.pageHeading).toBeVisible();
  });

  test('heading contains Good Sam', async () => {
    await expect(goodSamPage.pageHeading).toContainText(/good sam/i);
  });

  test('breadcrumb navigation is visible', async () => {
    await expect(goodSamPage.breadcrumb).toBeVisible();
  });

  test('footer is visible', async () => {
    await expect(goodSamPage.footer).toBeVisible();
  });
});
