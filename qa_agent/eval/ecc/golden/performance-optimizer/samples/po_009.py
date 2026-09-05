"""Proper use of context managers for file handling."""
import json


def load_product_catalog(path: str) -> list[dict]:
    """Load product catalog from a JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def append_log_entry(log_path: str, entry: str) -> None:
    """Append an entry to the log file."""
    with open(log_path, "a") as f:
        f.write(entry + "\n")


def read_config(config_path: str) -> dict[str, str]:
    """Read application configuration."""
    config: dict[str, str] = {}
    with open(config_path, "r") as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                config[key] = value
    return config
