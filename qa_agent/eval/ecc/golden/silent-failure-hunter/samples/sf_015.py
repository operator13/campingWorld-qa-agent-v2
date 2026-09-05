"""Feature flags with intentional fallback and explicit staleness tracking."""
import json
import logging
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlagResult:
    """Feature flag value with staleness metadata."""
    value: Any
    is_stale: bool
    fetched_at: float
    source: str


_flag_cache: dict[str, FlagResult] = {}
CACHE_TTL = 60


def get_feature_flag(flag_name: str, api_url: str, default: Any = False) -> FlagResult:
    """Get a feature flag with explicit fallback and staleness tracking."""
    cached = _flag_cache.get(flag_name)
    cache_age = time.time() - (cached.fetched_at if cached else 0)

    if cached and cache_age <= CACHE_TTL:
        return cached

    try:
        url = f"{api_url}/flags/{flag_name}"
        response = urllib.request.urlopen(url, timeout=3)
        data = json.loads(response.read().decode("utf-8"))
        result = FlagResult(
            value=data["value"],
            is_stale=False,
            fetched_at=time.time(),
            source="remote",
        )
        _flag_cache[flag_name] = result
        return result
    except Exception as e:
        logger.warning(
            "Failed to fetch flag %s, using %s: %s",
            flag_name,
            "stale cache" if cached else "default",
            e,
        )
        if cached is not None:
            stale = FlagResult(
                value=cached.value,
                is_stale=True,
                fetched_at=cached.fetched_at,
                source="stale_cache",
            )
            return stale
        return FlagResult(
            value=default,
            is_stale=True,
            fetched_at=0,
            source="default",
        )
