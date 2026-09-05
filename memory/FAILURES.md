# Failure Patterns

## FP-001: Locator not found: button 'Submit'
- **Signature:** `Locator not found: button 'Submit'`
- **Class:** locator_drift
- **Resolution:** healed:locator_update
- **Routes:** /
- **Occurrences:** 59
- **Last seen:** 2026-09-05
- **Stale after:** 2026-11-15

## FP-002: Locator not found
- **Signature:** `Locator not found`
- **Class:** locator_drift
- **Resolution:** healed:locator_update
- **Routes:** /
- **Occurrences:** 33
- **Last seen:** 2026-09-05
- **Stale after:** 2026-11-15

## FP-003: Login failed
- **Signature:** `Login failed`
- **Class:** app_defect
- **Resolution:** defect:QA-999
- **Routes:** /
- **Occurrences:** 66
- **Last seen:** 2026-09-05
- **Stale after:** 2026-11-15

## FP-004: TimeoutError: locator.click: Timeout Nms exceeded. - waiting for getByRole('butt
- **Signature:** `TimeoutError: locator.click: Timeout Nms exceeded. - waiting for getByRole('button', { name: 'Submit' })`
- **Class:** locator_drift
- **Resolution:** healed:locator_update
- **Routes:** /checkout
- **Occurrences:** 686
- **Last seen:** 2026-09-03
- **Stale after:** 2026-11-28

## FP-005: TimeoutError: locator.fill: Timeout Nms exceeded. Call log: - waiting for getByL
- **Signature:** `TimeoutError: locator.fill: Timeout Nms exceeded. Call log: - waiting for getByLabel('Quantity') - element is not stable`
- **Class:** test_flake
- **Resolution:** healed:timing_fix
- **Routes:** /product
- **Occurrences:** 50
- **Last seen:** 2026-09-03
- **Stale after:** 2026-11-28

## FP-006: Error: locator.click: element is outside of the viewport - getByRole('button', {
- **Signature:** `Error: locator.click: element is outside of the viewport - getByRole('button', { name: 'Load More' })`
- **Class:** test_flake
- **Resolution:** healed:timing_fix
- **Routes:** /search
- **Occurrences:** 50
- **Last seen:** 2026-09-03
- **Stale after:** 2026-11-28
