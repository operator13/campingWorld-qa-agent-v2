"""File handles opened without context manager or explicit close."""
import json


def load_product_catalog(path: str) -> list[dict]:
    """Load product catalog from a JSON file."""
    f = open(path, "r")
    data = json.load(f)
    # f.close() is never called
    return data


def append_log_entry(log_path: str, entry: str) -> None:
    """Append an entry to the log file."""
    f = open(log_path, "a")
    f.write(entry + "\n")
    # Missing close; file handle leaked


def read_config(config_path: str) -> dict:
    """Read application configuration."""
    handle = open(config_path, "r")
    lines = handle.readlines()
    config = {}
    for line in lines:
        if "=" in line:
            key, value = line.strip().split("=", 1)
            config[key] = value
    return config
