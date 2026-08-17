"""Determinism cache — skip regeneration when inputs haven't changed.

Stores a hash of inputs alongside generated outputs. On subsequent runs,
if the input hash matches, the cached outputs are reused. Regeneration
is triggered only when the inputs (Figma version, AC, etc.) change.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parent.parent / ".qa_cache"


def _hash_inputs(inputs: dict[str, Any]) -> str:
    """Compute a stable SHA-256 hash of the input dict."""
    canonical = json.dumps(inputs, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:24]


def get_cached(
    stage: str,
    inputs: dict[str, Any],
) -> dict[str, Any] | None:
    """Return cached output for a stage if input hash matches, else None."""
    input_hash = _hash_inputs(inputs)
    cache_file = _CACHE_DIR / f"{stage}_{input_hash}.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            logger.info("Cache HIT for %s (hash=%s)", stage, input_hash)
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Cache read failed for %s: %s", stage, e)

    logger.debug("Cache MISS for %s (hash=%s)", stage, input_hash)
    return None


def set_cached(
    stage: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
) -> None:
    """Store outputs in the cache, keyed by stage + input hash."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    input_hash = _hash_inputs(inputs)
    cache_file = _CACHE_DIR / f"{stage}_{input_hash}.json"

    try:
        cache_file.write_text(json.dumps(outputs, indent=2, default=str))
        logger.info("Cache SET for %s (hash=%s)", stage, input_hash)
    except OSError as e:
        logger.warning("Cache write failed for %s: %s", stage, e)


def invalidate(stage: str | None = None) -> int:
    """Delete cached files. If stage is None, clear all. Returns count deleted."""
    if not _CACHE_DIR.exists():
        return 0

    count = 0
    pattern = f"{stage}_*.json" if stage else "*.json"
    for f in _CACHE_DIR.glob(pattern):
        f.unlink()
        count += 1

    logger.info("Cache invalidated: %d file(s) deleted (stage=%s)", count, stage or "all")
    return count
