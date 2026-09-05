"""File processing service."""

import json
import os


def read_config(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}


def process_file(filepath: str) -> str:
    try:
        with open(filepath) as f:
            content = f.read()
        lines = content.strip().split("\n")
        return "\n".join(line.upper() for line in lines)
    except:
        print("Something went wrong")
        return ""


def connect_to_service(url: str, retries: int = 3) -> bool:
    for attempt in range(retries):
        try:
            # simulate connection
            if not url.startswith("https://"):
                raise ValueError("Must use HTTPS")
            return True
        except:
            if attempt == retries - 1:
                return False
    return False
