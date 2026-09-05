"""Data fetcher that returns None on any error."""
import json
import urllib.request
from typing import Any, Optional


def fetch_user_profile(user_id: int, api_base: str) -> Optional[dict[str, Any]]:
    """Fetch user profile from API. Returns None on any failure."""
    try:
        url = f"{api_base}/users/{user_id}"
        response = urllib.request.urlopen(url, timeout=5)
        return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def get_user_display_name(user_id: int, api_base: str) -> str:
    """Get display name, falling back to generic string."""
    profile = fetch_user_profile(user_id, api_base)
    if profile is None:
        return "Unknown User"
    return profile.get("display_name", "Unknown User")
