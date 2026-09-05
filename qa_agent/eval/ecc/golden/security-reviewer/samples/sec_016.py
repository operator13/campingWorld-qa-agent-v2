"""Secure FastAPI endpoint using parameterized SQL queries."""
from fastapi import FastAPI, HTTPException
import sqlite3

app = FastAPI()
DB_PATH = "app.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/users/{user_id}")
def get_user(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


@app.get("/users")
def search_users(name: str = ""):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, email FROM users WHERE name LIKE ?",
        (f"%{name}%",),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
