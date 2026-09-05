# Task: Add Email Notification System

## Context

The application is a FastAPI backend for a camping gear e-commerce platform. Currently, order confirmations and shipping updates are only visible in the user's dashboard. Customers have requested email notifications for key events.

## Codebase Structure

- `app/main.py` — FastAPI app with existing middleware
- `app/routers/orders.py` — Order placement and status endpoints
- `app/services/order_service.py` — Order business logic (create, update status)
- `app/models/user.py` — User model with email field
- `app/config.py` — Configuration via environment variables
- `tests/` — pytest test suite with fixtures

## Requirements

1. Send emails on: order_confirmed, order_shipped, order_delivered, password_reset
2. Use HTML templates for email body (Jinja2)
3. Support both SMTP and AWS SES as delivery backends (configurable)
4. Include unsubscribe link per notification type
5. Log all sent emails with delivery status
6. Do not block the request/response cycle — send asynchronously
7. Retry failed sends up to 3 times with 30-second delay
