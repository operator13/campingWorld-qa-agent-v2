import { test, expect } from './fixtures';
import { RegisterPage } from '../page_objects/RegisterPage';

test.describe('Registration', () => {
  let registerPage: RegisterPage;

  test.beforeEach(async ({ page }) => {
    registerPage = new RegisterPage(page);
    await registerPage.navigate();
  });

  test('account login page loads', async ({ page }) => {
    await expect(page).toHaveURL(/account-login/);
  });

  test('logo is visible', async () => {
    await expect(registerPage.logo).toBeVisible();
  });

  test('main content is visible', async () => {
    await expect(registerPage.mainContent).toBeVisible();
  });

  test('Sign In tab is visible', async () => {
    await expect(registerPage.signInTab).toBeVisible();
  });

  test('Create Account tab is visible', async () => {
    await expect(registerPage.createAccountTab).toBeVisible();
  });

  test('Create Account tab is clickable', async () => {
    await registerPage.switchToCreateAccount();
    await expect(registerPage.createAccountTab).toHaveAttribute('aria-selected', 'true');
  });
});
