# Task: Add Webhook Delivery System with Retry Queue

## Context

The platform allows third-party integrations (inventory systems, accounting tools, CRM). Currently, integrations poll our API for changes. Partners have requested real-time webhook notifications to reduce polling load and latency.

## Codebase Structure

- `app/main.py` — FastAPI application
- `app/routers/integrations.py` — Partner integration management endpoints
- `app/models/integration.py` — Integration model with partner_id and config
- `app/services/` — Business logic for orders, inventory, customers
- `app/events/` — Internal event bus (in-process, synchronous)
- `infrastructure/docker-compose.yml` — Redis already running for cache
- `tests/` — pytest suite

## Requirements

1. Partners register webhook URLs with event subscriptions (order.created, inventory.updated, etc.)
2. Deliver webhook payloads within 5 seconds of event occurrence
3. Sign payloads with HMAC-SHA256 using per-partner secrets
4. Retry failed deliveries: 3 attempts with exponential backoff (10s, 60s, 300s)
5. Dead letter queue for deliveries that fail all retries
6. Dashboard showing delivery status, latency, and failure rate per partner
7. Support at least 500 webhook deliveries per minute at launch
8. Admin endpoint to replay failed webhooks
