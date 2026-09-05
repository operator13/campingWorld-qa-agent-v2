"""Data parser that loses stack traces when re-raising."""
import json
from typing import Any


def parse_config_file(raw: str) -> dict[str, Any]:
    """Parse a JSON config string, losing context on error."""
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise TypeError("Config must be a JSON object")
        return data
    except json.JSONDecodeError:
        raise ValueError("Failed to parse configuration file")
    except TypeError:
        raise ValueError("Configuration has wrong structure")


def load_and_validate(raw: str, required_keys: list[str]) -> dict:
    """Load config and validate required keys are present."""
    config = parse_config_file(raw)
    missing = [k for k in required_keys if k not in config]
    if missing:
        raise KeyError(f"Missing required keys: {missing}")
    return config
