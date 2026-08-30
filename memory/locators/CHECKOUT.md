# Locator History: /checkout

## Submit
- 2026-08-30: `page.getByRole('button', { name: 'Submit' })` → `page.getByRole('button', { name: 'Place Order' })` | reason: Button text changed from 'Submit' to 'Place Order' as seen in the current DOM snapshot. | success: no
- 2026-08-30: `page.getByRole('button', { name: 'Submit' })` → `page.getByRole('button', { name: 'Place Order' })` | reason: Button text changed from 'Submit' to 'Place Order' as confirmed by the current DOM snapshot showing <button>Place Order</button>. Also added missing `this.page = page` assignment to fix the navigate() method. | success: no
- 2026-08-30: `page.getByRole('button', { name: 'Submit' })` → `page.getByRole('button', { name: 'Place Order' })` | reason: Button text changed from 'Submit' to 'Place Order' as confirmed by current DOM snapshot showing <button>Place Order</button> | success: no
- 2026-08-30: `this.page (undefined reference in navigate())` → `this.page = page stored in constructor` | reason: The page parameter was not stored as a class property, causing navigate() to fail with 'Cannot read properties of undefined'. Added this.page = page in constructor. | success: no

## checkout-email
- 2026-08-30: `page.getByTestId('checkout-email')` → `page.getByTestId('email-field')` | reason: The data-testid attribute changed from 'checkout-email' to 'email-field' as seen in the current DOM snapshot. | success: no

## I agree to terms
- 2026-08-30: `page.getByRole('checkbox', { name: 'I agree to terms' })` → `page.getByRole('checkbox', { name: 'Accept Terms and Conditions' })` | reason: The checkbox label text changed from 'I agree to terms' to 'Accept Terms and Conditions' as shown in the DOM snapshot (<label for="terms">Accept Terms and Conditions</label>). Updated the accessible name to match the new label. | success: no
