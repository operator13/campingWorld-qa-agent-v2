"""Config loader with no error handling on file and network operations."""
import json
import urllib.request


def load_config(path: str) -> dict:
    """Load configuration from a JSON file - no error handling."""
    fh = open(path, "r")
    raw = fh.read()
    fh.close()
    config = json.loads(raw)
    return config


def fetch_remote_config(url: str) -> dict:
    """Fetch remote JSON configuration - no error handling."""
    response = urllib.request.urlopen(url)
    body = response.read().decode("utf-8")
    data = json.loads(body)
    return data


def merge_configs(local_path: str, remote_url: str) -> dict:
    """Merge local and remote configs - no error handling."""
    local = load_config(local_path)
    remote = fetch_remote_config(remote_url)
    merged = {**local, **remote}
    output_fh = open("/tmp/merged_config.json", "w")
    output_fh.write(json.dumps(merged, indent=2))
    output_fh.close()
    return merged
