"""Repository with proper exception chaining using 'from e'."""
import json
import sqlite3
from typing import Any, Optional


class RepositoryError(Exception):
    """Base error for repository operations."""
    pass


class NotFoundError(RepositoryError):
    """Raised when an entity is not found."""
    pass


class ConnectionFailedError(RepositoryError):
    """Raised when database connection fails."""
    pass


def get_user(db_path: str, user_id: int) -> dict[str, Any]:
    """Fetch a user by ID with proper exception chaining."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
    except sqlite3.OperationalError as e:
        raise ConnectionFailedError(f"Cannot connect to database: {db_path}") from e

    if row is None:
        raise NotFoundError(f"User {user_id} not found")

    return {"id": row[0], "name": row[1], "email": row[2]}


def parse_user_json(raw: str) -> dict[str, Any]:
    """Parse user JSON with proper chaining."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid user JSON at position {e.pos}") from e

    if "id" not in data:
        raise KeyError("User JSON must contain 'id' field")

    return data
