"""Cache layer that returns stale data on refresh failure."""
import json
import logging
import time
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

_cache: dict[str, Any] = {}
_cache_timestamps: dict[str, float] = {}
CACHE_TTL_SECONDS = 300


def get_pricing_data(product_id: str, api_url: str) -> dict:
    """Get pricing data, returning stale cache on refresh failure."""
    cached = _cache.get(product_id)
    cache_age = time.time() - _cache_timestamps.get(product_id, 0)

    if cached is None or cache_age > CACHE_TTL_SECONDS:
        try:
            url = f"{api_url}/pricing/{product_id}"
            response = urllib.request.urlopen(url, timeout=5)
            fresh = json.loads(response.read().decode("utf-8"))
            _cache[product_id] = fresh
            _cache_timestamps[product_id] = time.time()
            return fresh
        except Exception as e:
            logger.error("Failed to refresh pricing for %s: %s", product_id, e)
            if cached is not None:
                return cached
            return {"price": 0, "currency": "USD", "available": False}

    return cached
