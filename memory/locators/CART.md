# Locator History: /cart

## Shopping Cart
- 2026-08-30: `page.getByRole('heading', { name: 'Shopping Cart' })` → `page.getByRole('heading', { name: 'Your Cart' })` | reason: The heading text changed from 'Shopping Cart' to 'Your Cart' as seen in the current DOM snapshot (<h1>Your Cart</h1>). | success: no

## Remove item
- 2026-08-30: `page.getByRole('button', { name: 'Remove item' })` → `page.getByRole('link', { name: 'Delete item' })` | reason: Element changed from a <button> (role='button', name='Remove item') to an <a> tag (role='link', aria-label='Delete item', text='Delete item') | success: no
