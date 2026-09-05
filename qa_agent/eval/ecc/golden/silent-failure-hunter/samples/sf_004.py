"""Search service that returns empty results on failure."""
import json
import urllib.request
from typing import Any


def search_products(query: str, api_url: str) -> list[dict[str, Any]]:
    """Search for products. Returns empty list on any error."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"{api_url}/search?q={encoded}&limit=50"
        response = urllib.request.urlopen(url, timeout=5)
        data = json.loads(response.read().decode("utf-8"))
        return data.get("results", [])
    except Exception:
        return []


def search_and_format(query: str, api_url: str) -> dict:
    """Search products and format for display."""
    results = search_products(query, api_url)
    return {
        "query": query,
        "count": len(results),
        "items": [
            {"name": r.get("name"), "price": r.get("price")}
            for r in results
        ],
    }
