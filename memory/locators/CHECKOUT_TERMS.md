# Locator History: /checkout/terms

## I agree to terms
- 2026-08-30: `page.getByRole('checkbox', { name: 'I agree to terms' })` → `page.getByRole('checkbox', { name: 'Accept Terms and Conditions' })` | reason: The checkbox label text changed from 'I agree to terms' to 'Accept Terms and Conditions' as shown in the DOM snapshot where the label element reads 'Accept Terms and Conditions' | success: no
- 2026-08-30: `page.getByRole('checkbox', { name: 'I agree to terms' })` → `page.getByRole('checkbox', { name: 'Accept Terms and Conditions' })` | reason: Checkbox label text changed from 'I agree to terms' to 'Accept Terms and Conditions' as confirmed by the current DOM snapshot showing <label for="terms">Accept Terms and Conditions</label>. Also fixed missing `this.page = page` assignment to prevent navigate() from failing. | success: no
