import { test, expect } from './fixtures';
import { SignInPage } from '../page_objects/SignInPage';

test.describe('Sign In', () => {
  let signInPage: SignInPage;

  test.beforeEach(async ({ page }) => {
    signInPage = new SignInPage(page);
    await signInPage.navigate();
  });

  test('sign-in tab is selected by default', async () => {
    await expect(signInPage.signInTab).toHaveAttribute('aria-selected', 'true');
  });

  test('create account tab is visible', async () => {
    await expect(signInPage.createAccountTab).toBeVisible();
  });

  test('email input is visible', async () => {
    await expect(signInPage.emailInput).toBeVisible();
  });

  test('password input is visible', async () => {
    await expect(signInPage.passwordInput).toBeVisible();
  });

  test('sign in button is visible and enabled', async () => {
    await expect(signInPage.signInButton).toBeVisible();
    await expect(signInPage.signInButton).toBeEnabled();
  });

  test('forgot password link is visible', async () => {
    await expect(signInPage.forgotPasswordLink).toBeVisible();
  });

  test('keep me signed in checkbox is visible', async () => {
    await expect(signInPage.keepMeSignedInCheckbox).toBeVisible();
  });

  test('email input accepts text', async () => {
    await signInPage.emailInput.fill('test@example.com');
    await expect(signInPage.emailInput).toHaveValue('test@example.com');
  });

  test('password input accepts text', async () => {
    await signInPage.passwordInput.fill('TestPass123');
    await expect(signInPage.passwordInput).toHaveValue('TestPass123');
  });

  test('logo is visible', async () => {
    await expect(signInPage.logo).toBeVisible();
  });
});
