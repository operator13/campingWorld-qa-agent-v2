# Locator History: /products

## Sort By
- 2026-08-30: `page.getByRole('combobox', { name: 'Sort By' })` → `page.getByRole('combobox', { name: 'Order By' })` | reason: The label and aria-label on the sort <select> element changed from 'Sort By' to 'Order By', so the accessible name used in getByRole must be updated to match. | success: no
- 2026-08-30: `page.getByRole('combobox', { name: 'Sort By' })` → `page.getByRole('combobox', { name: 'Order By' })` | reason: The aria-label on the <select> element changed from 'Sort By' to 'Order By', matching the updated <label> text in the DOM. | success: no
- 2026-08-30: `page.getByRole('combobox', { name: 'Sort By' })` → `page.getByRole('combobox', { name: 'Order By' })` | reason: The select element's aria-label changed from 'Sort By' to 'Order By', as confirmed by the DOM snapshot showing aria-label="Order By" and the associated label text 'Order By'. | success: no

## unknown
- 2026-08-30: `page.getByAltText('Product thumbnail')` → `page.getByAltText('Camping tent product image')` | reason: The alt text on the product image changed from 'Product thumbnail' to 'Camping tent product image' as seen in the current DOM snapshot. | success: no
