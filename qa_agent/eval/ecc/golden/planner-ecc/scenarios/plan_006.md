# Task: Implement SSO Across 3 Microservices

## Context

The company runs three customer-facing services that currently have independent authentication:
1. **storefront-api** — E-commerce (FastAPI, PostgreSQL, JWT auth)
2. **support-portal** — Customer support tickets (FastAPI, MongoDB, session-based auth)
3. **community-forum** — User forums (Django, PostgreSQL, Django auth)

Users must log in separately to each service, creating friction. Management wants single sign-on so one login grants access to all three.

## Current Auth State

- storefront-api: Issues its own JWTs, stores users in `auth_users` table
- support-portal: Uses Flask-Login with MongoDB session store
- community-forum: Uses Django's built-in auth with `auth_user` table
- No shared user directory; ~40% of users have accounts on multiple services with different passwords

## Requirements

1. Single login grants access to all three services
2. Use OpenID Connect (OIDC) as the protocol
3. Deploy Keycloak (or equivalent) as the identity provider
4. Migrate existing user accounts with minimal disruption (no forced password resets)
5. Support social login (Google, Apple) through the identity provider
6. Each service must be deployable independently with graceful fallback if IdP is down
7. Phased rollout: storefront first, then support, then forum
