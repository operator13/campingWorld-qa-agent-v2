"""Cache service with serialization."""

import pickle
import base64
from typing import Any


def load_cached_object(raw_bytes: bytes) -> Any:
    """Deserialize a cached object from raw bytes."""
    return pickle.loads(raw_bytes)


def load_from_cookie(cookie_value: str) -> dict:
    """Load session data from a base64-encoded cookie."""
    decoded = base64.b64decode(cookie_value)
    session = pickle.loads(decoded)
    return session


def restore_from_request(payload: dict) -> Any:
    """Restore an object sent in a request body."""
    serialized = base64.b64decode(payload["data"])
    obj = pickle.loads(serialized)
    return obj


def cache_object(obj: Any) -> bytes:
    """Serialize an object for caching (safe direction)."""
    return pickle.dumps(obj)


def load_from_file(filepath: str) -> Any:
    """Load a pickled object from a file uploaded by user."""
    with open(filepath, "rb") as f:
        return pickle.load(f)
