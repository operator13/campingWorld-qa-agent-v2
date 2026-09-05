"""Config loader using 'or' pattern to mask failures."""
import os
from typing import Optional


def load_from_vault(key: str) -> Optional[str]:
    """Simulate loading a secret from a vault service."""
    raise ConnectionError("Vault service unavailable")


def get_database_url() -> str:
    """Get database URL, silently falling back to default on any failure."""
    try:
        url = load_from_vault("DATABASE_URL") or "sqlite:///local.db"
    except Exception:
        url = "sqlite:///local.db"
    return url


def get_api_key() -> str:
    """Get API key with silent fallback to env var then empty string."""
    try:
        key = load_from_vault("API_KEY") or os.getenv("API_KEY") or ""
    except Exception:
        key = os.getenv("API_KEY") or ""
    return key


def get_config() -> dict:
    """Load full config with silent fallbacks everywhere."""
    return {
        "database_url": get_database_url(),
        "api_key": get_api_key(),
        "debug": os.getenv("DEBUG", "false").lower() == "true",
    }
