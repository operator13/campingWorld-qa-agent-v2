# Task: Add Rate Limiting Middleware

## Context

The FastAPI application is publicly accessible and has experienced several abuse incidents: brute-force login attempts, scraping of product data, and API key exhaustion by misbehaving integrations. There is no rate limiting in place.

## Codebase Structure

- `app/main.py` — FastAPI app with CORS and auth middleware already configured
- `app/routers/auth.py` — Login, register, password reset endpoints
- `app/routers/products.py` — Product listing and detail endpoints
- `app/routers/orders.py` — Order CRUD (authenticated)
- `app/middleware/` — Directory with `cors.py` and `auth.py`
- `app/config.py` — Environment-based configuration
- `infrastructure/docker-compose.yml` — Redis already available on port 6379

## Requirements

1. Global default: 100 requests per minute per IP
2. Stricter limits for auth endpoints: 10 requests per minute per IP
3. Higher limits for authenticated API-key users: 500 requests per minute
4. Use Redis as the backend for distributed rate counting
5. Return 429 Too Many Requests with `Retry-After` header when limit exceeded
6. Include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` response headers
7. Rate limit configuration should be adjustable without code deployment
