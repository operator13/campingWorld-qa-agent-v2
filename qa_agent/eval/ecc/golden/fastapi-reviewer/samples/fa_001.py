"""Endpoint that fetches user profile from SQLite."""
import sqlite3

from fastapi import APIRouter

router = APIRouter()


@router.get("/users/{user_id}")
async def get_user(user_id: int):
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return {"error": "User not found"}
    return {"id": row[0], "name": row[1], "email": row[2]}
