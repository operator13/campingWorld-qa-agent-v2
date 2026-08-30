# Locator History: /login

## unknown
- 2026-08-30: `page.getByLabel('Email address')` → `page.getByLabel('Email')` | reason: Label text changed from 'Email address' to 'Email' as shown in the DOM snapshot: <label for="email">Email</label> | success: no
- 2026-08-30: `page.getByLabel('Email address')` → `page.getByLabel('Email')` | reason: The label text changed from 'Email address' to 'Email' as confirmed by the current DOM showing <label for="email">Email</label> | success: no
- 2026-08-30: `page.getByLabel('Email address')` → `page.getByLabel('Email')` | reason: The label text changed from 'Email address' to 'Email' as confirmed by the current DOM: <label for="email">Email</label>. Also fixed missing `this.page = page` assignment that would have caused navigate() to fail. | success: no
