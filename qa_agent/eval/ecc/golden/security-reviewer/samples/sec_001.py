"""FastAPI endpoint with SQL injection via f-string."""
from fastapi import FastAPI, HTTPException
import sqlite3

app = FastAPI()
DB_PATH = "app.db"


def get_db():
    return sqlite3.connect(DB_PATH)


@app.get("/users/{user_id}")
def get_user(user_id: str):
    conn = get_db()
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": row[0], "name": row[1], "email": row[2]}
