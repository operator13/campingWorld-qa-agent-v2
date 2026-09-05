# Task: Migrate from SQLite to PostgreSQL

## Context

The application started as a prototype using SQLite for simplicity. It has grown to serve 50K daily users and SQLite's write locking is causing performance bottlenecks. The team has decided to migrate to PostgreSQL.

## Codebase Structure

- `app/database.py` — SQLAlchemy engine with `sqlite:///./app.db` connection string
- `app/models/` — 12 SQLAlchemy models using some SQLite-specific features
- `app/services/` — 8 service modules, some with raw SQL queries using `GROUP_CONCAT` and `strftime`
- `alembic/` — Migration scripts (15 revisions targeting SQLite)
- `scripts/seed_data.py` — Seeds test data using SQLite `.import`
- `tests/conftest.py` — Creates in-memory SQLite for test isolation
- Production data: ~2GB across 12 tables, largest table has 4M rows

## Requirements

1. Zero data loss during migration
2. Maximum 30 minutes of downtime during cutover
3. All raw SQL must be converted to PostgreSQL-compatible syntax
4. Alembic migrations must target PostgreSQL going forward
5. Test suite must run against PostgreSQL (can use Docker for CI)
6. Rollback plan must exist for the first 48 hours after cutover
