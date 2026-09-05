# Task: Extract Shared Utilities into a Reusable Package

## Context

The organization has three Python services (storefront-api, admin-api, analytics-api) that have independently implemented overlapping utility functions. Code drift between the copies is causing bugs — a fix applied in one service is not propagated to others.

## Duplicated Utilities

- `string_utils.py` — slug generation, sanitization, truncation (exists in all 3 services)
- `date_utils.py` — timezone conversion, business-day calculation (exists in storefront + admin)
- `currency_utils.py` — formatting, rounding, conversion (exists in all 3 services, diverged)
- `validation_utils.py` — email, phone, zip code validators (exists in storefront + analytics)
- `pagination.py` — cursor-based pagination helpers (exists in all 3, slightly different APIs)

## Codebase Structure (per service)

- `app/utils/` — Local utility modules
- `app/services/` — Business logic importing from `app/utils/`
- `tests/test_utils/` — Tests for utility functions
- `pyproject.toml` — Dependencies and build config

## Requirements

1. Create a shared `company-utils` package installable via pip
2. Unify divergent implementations (pick the best, add missing features)
3. Maintain backward compatibility — existing import paths should still work during transition
4. Package must have 90%+ test coverage
5. Publish to internal PyPI registry
6. Services should migrate to the shared package over 2 sprints
