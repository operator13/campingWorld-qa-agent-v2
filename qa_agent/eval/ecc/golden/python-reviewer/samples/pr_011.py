"""Robust file reader with proper exception handling."""

import json
from pathlib import Path


class ConfigError(Exception):
    """Raised when configuration is invalid."""


class FileNotReadableError(Exception):
    """Raised when a file cannot be read."""


def load_json_config(path: Path) -> dict[str, str]:
    """Load and validate a JSON configuration file."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except PermissionError as exc:
        raise FileNotReadableError(f"Cannot read {path}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Expected dict, got {type(data).__name__}")

    return data


def safe_read_lines(path: Path) -> list[str]:
    """Read lines from a file, returning empty list on failure."""
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, PermissionError):
        return []
