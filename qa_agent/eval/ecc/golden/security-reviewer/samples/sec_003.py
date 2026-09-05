"""FastAPI analytics endpoint with SQL injection via dynamic table name."""
from fastapi import FastAPI, Query
import asyncpg

app = FastAPI()
DATABASE_URL = "postgresql://app:password@localhost/analytics"


async def get_pool():
    return await asyncpg.create_pool(DATABASE_URL)


@app.get("/api/analytics/{table_name}")
async def get_analytics(
    table_name: str,
    start_date: str = Query(...),
    end_date: str = Query(...),
):
    """Fetch analytics data from a user-specified table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        query = f"SELECT date, value FROM {table_name} WHERE date BETWEEN $1 AND $2 ORDER BY date"
        rows = await conn.fetch(query, start_date, end_date)
    return {"data": [dict(r) for r in rows]}


ALLOWED_TABLES = {"page_views", "sessions", "conversions"}


@app.get("/api/analytics/safe/{table_name}")
async def get_analytics_safe(table_name: str):
    """This endpoint validates the table name but is not the one under test."""
    if table_name not in ALLOWED_TABLES:
        return {"error": "Invalid table"}
    return {"status": "ok"}
