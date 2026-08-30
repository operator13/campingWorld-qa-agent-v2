# Lessons Learned

## Pattern Scoreboard

| Pattern | Occurrences | Success rate | Best strategy |
|---------|-------------|-------------|---------------|
| locator_drift (from failure patterns) | 58 | 0/58 (0%) | n/a |
| app_defect (from failure patterns) | 32 | 0/32 (0%) | n/a |
| Button/element text rename | 29 | 13/29 (44%) | getByRole |































































## Route Insights

### /checkout
- **2026-08-30:** **Stability:** HIGH — changes 0.0x/week
**Best locator strategy:** getByRole (names are stable here)
**Known testids:** search-input, search-input *(source: auto-generated)*
- **2026-08-30:** **Stability:** HIGH — changes 0.0x/week
**Known testids:** checkout-heading, checkout-email, cart-item-name, cart-item-price, cart-item-quantity *(source: auto-generated)*

### /search
- **2026-08-30:** **Stability:** HIGH — changes 0.0x/week
**Known testids:** product-card, product-card, product-card *(source: auto-generated)*

### /product
- **2026-08-30:** **Stability:** HIGH — changes 0.0x/week *(source: auto-generated)*

### /cart
- **2026-08-30:** **Stability:** HIGH — changes 0.0x/week
**Known testids:** cart-item, cart-item-name, cart-item-price, cart-item-quantity *(source: auto-generated)*

## Decision Reflections
