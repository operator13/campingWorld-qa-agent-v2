"""Data sync service with empty except blocks swallowing errors."""
import sqlite3
import json
import urllib.request


def sync_user_data(user_id: int, db_path: str, api_url: str) -> dict:
    """Sync user data between local DB and remote API."""
    local_data = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        local_data = cursor.fetchone()
        conn.close()
    except Exception:
        pass

    remote_data = None
    try:
        response = urllib.request.urlopen(f"{api_url}/users/{user_id}")
        remote_data = json.loads(response.read().decode("utf-8"))
    except Exception:
        pass

    try:
        if remote_data and local_data:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET name=?, email=? WHERE id=?",
                (remote_data["name"], remote_data["email"], user_id),
            )
            conn.commit()
            conn.close()
    except Exception:
        pass

    try:
        cache_key = f"user:{user_id}"
        invalidate_cache(cache_key)
    except Exception:
        pass

    return {"user_id": user_id, "synced": True}


def invalidate_cache(key: str) -> None:
    """Stub for cache invalidation."""
    raise NotImplementedError("Cache backend not configured")
