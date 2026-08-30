import { test, expect } from './fixtures';
import { FooterPage } from '../page_objects/FooterPage';

test.describe('Footer & Legal Pages', () => {
  let footerPage: FooterPage;

  test.beforeEach(async ({ page }) => {
    footerPage = new FooterPage(page);
    await footerPage.navigate();
  });

  test('footer contentinfo landmark is visible', async () => {
    await expect(footerPage.footer).toBeVisible();
  });

  test('Privacy Policy link is present in the footer', async () => {
    await expect(footerPage.privacyPolicyLink).toBeVisible();
  });

  test('Terms of Use link is present in the footer', async () => {
    await expect(footerPage.termsOfUseLink).toBeVisible();
  });

  test('Accessibility link is present in the footer', async () => {
    await expect(footerPage.accessibilityLink).toBeVisible();
  });

  test('footer contains multiple navigation links', async () => {
    const linkCount = await footerPage.footer.getByRole('link').count();
    expect(linkCount).toBeGreaterThan(5);
  });

  test('Facebook social link has correct href', async () => {
    const href = await footerPage.facebookLink.getAttribute('href');
    expect(href).toMatch(/facebook\.com/i);
  });

  test('Instagram social link has correct href', async () => {
    const href = await footerPage.instagramLink.getAttribute('href');
    expect(href).toMatch(/instagram\.com/i);
  });

  test('YouTube social link has correct href', async () => {
    const href = await footerPage.youtubeLink.getAttribute('href');
    expect(href).toMatch(/youtube\.com/i);
  });

  test('Privacy Policy link has correct href', async () => {
    const href = await footerPage.privacyPolicyLink.getAttribute('href');
    expect(href).toMatch(/privacy/i);
  });

  test('Terms of Use link has correct href', async () => {
    const href = await footerPage.termsOfUseLink.getAttribute('href');
    expect(href).toMatch(/terms/i);
  });

  test('privacy policy page has a heading', async ({ page }) => {
    await footerPage.navigateToPrivacyPolicy();
    await expect(footerPage.legalHeading).toBeVisible();
  });

  test('privacy policy page has main content body', async ({ page }) => {
    await footerPage.navigateToPrivacyPolicy();
    await expect(footerPage.legalContentBody).toBeVisible();
  });

  test('privacy policy page shows main content', async ({ page }) => {
    await footerPage.navigateToPrivacyPolicy();
    await expect(footerPage.legalContentBody).toBeVisible();
  });
});
