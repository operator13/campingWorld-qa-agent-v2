# Locator History: /cart/items

## Remove item
- 2026-08-30: `page.getByRole('button', { name: 'Remove item' })` → `page.getByRole('link', { name: 'Delete item' })` | reason: Element changed from a <button> to an <a> tag with role='link', and the label changed from 'Remove item' to 'Delete item' (matching aria-label and text content in the DOM) | success: no
