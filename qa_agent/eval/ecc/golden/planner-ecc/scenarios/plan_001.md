# Task: Add User Preferences API Endpoint

## Context

The application is a FastAPI-based backend serving a camping gear e-commerce site. Users can currently browse products, add items to cart, and check out. There is no way for users to save preferences (favorite categories, notification settings, display preferences).

## Codebase Structure

- `app/main.py` — FastAPI app instance and router includes
- `app/routers/` — Route handlers (users.py, products.py, cart.py, orders.py)
- `app/models/` — SQLAlchemy models (user.py, product.py, order.py)
- `app/schemas/` — Pydantic request/response schemas
- `app/services/` — Business logic layer
- `app/database.py` — Database session and engine setup (PostgreSQL)
- `tests/` — pytest test suite

## Requirements

1. Users should be able to GET and PUT their preferences
2. Preferences include: favorite_categories (list of strings), email_notifications (bool), display_currency (enum: USD, EUR, GBP), items_per_page (int, 10-100)
3. Preferences should have sensible defaults for new users
4. Endpoint must require authentication (existing JWT middleware)
5. Changes should be validated with Pydantic and persisted to PostgreSQL
