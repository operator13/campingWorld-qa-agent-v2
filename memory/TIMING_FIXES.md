# Known Timing Fixes

| Date | Route | Element | Error Pattern | Strategy | Fix | Success |
|------|-------|---------|--------------|----------|-----|---------|
| 2026-08-30 | /product | addToCartButton | scrollIntoViewIfNeeded_timeout | A | Added waitFor({ state: 'visible', timeout: 20000 }) before scrollIntoViewIfNeeded | no |
| 2026-08-30 | /checkout | checkoutBtn | click_timeout | A | Added waitFor({ state: 'visible', timeout: 20000 }) before click() | no |
| 2026-08-30 | /product | quantityInput | fill_timeout | A | Added waitFor({ state: 'stable', timeout: 20000 }) before fill() | no |
| 2026-08-30 | /search | loadMoreBtn | generic_timeout | C | Added waitFor({ state: 'visible', timeout: 20000 }) and scrollIntoViewIfNeeded() before click() | no |
| 2026-08-30 | /product | reviewsSection | scrollIntoViewIfNeeded_timeout | A | Added waitFor({ state: 'visible', timeout: 20000 }) before scrollIntoViewIfNeeded() | no |
| 2026-09-02 | /product | addToCartButton | scrollIntoViewIfNeeded_timeout | A | Added waitFor({ state: 'visible', timeout: 20000 }) before scrollIntoViewIfNeeded | no |
| 2026-09-02 | /checkout | checkoutBtn | click_timeout | A | Added waitFor({ state: 'visible', timeout: 20_000 }) before click() | no |
| 2026-09-02 | /search | loadMoreBtn | generic_timeout | C | Added waitFor({ state: 'visible', timeout: 20000 }) and scrollIntoViewIfNeeded() before click() | no |
| 2026-09-02 | /product | quantityInput | fill_timeout | A | Added waitFor({ state: 'stable', timeout: 20_000 }) before fill() | no |
| 2026-09-02 | /product | reviewsSection | scrollIntoViewIfNeeded_timeout | A | Added waitFor({ state: 'visible', timeout: 20_000 }) before scrollIntoViewIfNeeded() | no |
| 2026-09-03 | /product | addToCartButton | scrollIntoViewIfNeeded_timeout | A | Added waitFor({ state: 'visible', timeout: 20000 }) before scrollIntoViewIfNeeded | no |
| 2026-09-03 | /checkout | checkoutBtn | click_timeout | A | Added waitFor({ state: 'visible', timeout: 20000 }) before click() | no |
| 2026-09-03 | /product | quantityInput | fill_timeout | A | Added waitFor({ state: 'stable', timeout: 20_000 }) before fill() | no |
| 2026-09-03 | /product | reviewsSection | scrollIntoViewIfNeeded_timeout | A | Added waitFor({ state: 'visible', timeout: 20_000 }) before scrollIntoViewIfNeeded() | no |
| 2026-09-03 | /search | loadMoreBtn | generic_timeout | C | Added waitFor({ state: 'visible', timeout: 20000 }) and scrollIntoViewIfNeeded() before click() | no |
| 2026-09-05 | /checkout | checkoutBtn | click_timeout | A | Added waitFor({ state: 'visible', timeout: 20_000 }) before click() | no |
| 2026-09-05 | /product | addToCartButton | scrollIntoViewIfNeeded_timeout | A | Added waitFor({ state: 'visible', timeout: 20000 }) before scrollIntoViewIfNeeded | no |
| 2026-09-05 | /product | quantityInput | fill_timeout | A | Added waitFor({ state: 'stable', timeout: 20_000 }) before fill() | no |
| 2026-09-05 | /product | reviewsSection | scrollIntoViewIfNeeded_timeout | A | Added waitFor({ state: 'visible', timeout: 20_000 }) before scrollIntoViewIfNeeded() | no |
| 2026-09-05 | /search | loadMoreBtn | generic_timeout | C | Added waitFor({ state: 'visible', timeout: 20000 }) and scrollIntoViewIfNeeded() before click() | no |
