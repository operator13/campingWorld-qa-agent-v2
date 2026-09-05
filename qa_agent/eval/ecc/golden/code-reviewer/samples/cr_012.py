"""File handler with proper error handling and context managers."""
import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def read_json_file(path: Path) -> Optional[dict[str, Any]]:
    """Read and parse a JSON file with proper error handling."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        logger.warning("Config file not found: %s", path)
        return None
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in %s: %s", path, e)
        return None
    except PermissionError:
        logger.error("Permission denied reading %s", path)
        return None


def write_json_file(path: Path, data: dict[str, Any]) -> bool:
    """Write data to a JSON file atomically using a temp file."""
    tmp_path = path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        tmp_path.rename(path)
        return True
    except OSError as e:
        logger.error("Failed to write %s: %s", path, e)
        if tmp_path.exists():
            tmp_path.unlink()
        return False


def ensure_directory(path: Path) -> bool:
    """Create directory if it does not exist."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        logger.error("Cannot create directory %s: %s", path, e)
        return False
