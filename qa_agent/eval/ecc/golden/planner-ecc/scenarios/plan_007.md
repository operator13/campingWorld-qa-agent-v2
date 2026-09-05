# Task: Add Pagination to All List Endpoints

## Context

The FastAPI application has 6 list endpoints that currently return all results without pagination. As the dataset grows, these endpoints are becoming slow and returning oversized responses.

## Endpoints to Paginate

- `GET /api/products` — ~15,000 products
- `GET /api/orders` — ~50,000 orders (filtered by user)
- `GET /api/reviews` — ~80,000 reviews
- `GET /api/categories` — ~200 categories (small, but should be consistent)
- `GET /api/users` — ~30,000 users (admin only)
- `GET /api/inventory` — ~15,000 SKUs (admin only)

## Codebase Structure

- `app/routers/` — One router file per resource
- `app/schemas/` — Pydantic response models (e.g., `ProductList = list[ProductOut]`)
- `app/services/` — Service layer with SQLAlchemy queries using `.all()`
- `app/database.py` — PostgreSQL with SQLAlchemy async session

## Requirements

1. Use offset-based pagination with `page` and `limit` query parameters
2. Default: page=1, limit=20, max limit=100
3. Response envelope: `{ items: [...], total: int, page: int, limit: int, pages: int }`
4. Existing clients sending no pagination params should get page 1 (backward compatible)
5. Add Link headers for next/prev pages (RFC 8288)
