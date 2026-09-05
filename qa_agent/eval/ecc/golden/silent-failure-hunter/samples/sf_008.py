"""API client that wraps exceptions without chaining."""
import json
import urllib.request
from typing import Any


class ApiError(Exception):
    """Custom API error."""
    pass


class ApiClient:
    """HTTP API client that loses exception context on re-raise."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key

    def get(self, path: str) -> dict[str, Any]:
        """GET request, wrapping errors without chaining."""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self.api_key}"}
        )
        try:
            response = urllib.request.urlopen(req, timeout=10)
            return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ApiError(f"HTTP {e.code} from {path}")
        except urllib.error.URLError:
            raise ApiError(f"Connection failed for {path}")
        except json.JSONDecodeError:
            raise ApiError(f"Invalid JSON from {path}")

    def post(self, path: str, data: dict) -> dict[str, Any]:
        """POST request, also losing exception context."""
        url = f"{self.base_url}{path}"
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            response = urllib.request.urlopen(req, timeout=10)
            return json.loads(response.read().decode("utf-8"))
        except Exception:
            raise ApiError(f"POST to {path} failed")
