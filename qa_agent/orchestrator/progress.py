"""Progress tracker — JSON checkpoint for resumable crawls."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PROGRESS_FILE = _PROJECT_ROOT / "orchestrator_progress.json"


class ProgressTracker:
    """Tracks crawl progress with a JSON checkpoint file for resume support."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_PROGRESS_FILE
        self._state: dict[str, dict[str, str]] = self._load()

    def _load(self) -> dict[str, dict[str, str]]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning("ProgressTracker: corrupt progress file, starting fresh")
                return {}
        return {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._state, indent=2) + "\n")

    def is_done(self, page_name: str) -> bool:
        """Check if a page has been successfully completed."""
        entry = self._state.get(page_name)
        return entry is not None and entry.get("status") == "done"

    def mark_done(self, page_name: str) -> None:
        """Mark a page as successfully completed."""
        self._state[page_name] = {
            "status": "done",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._save()

    def mark_failed(self, page_name: str, error: str) -> None:
        """Mark a page as failed with an error message."""
        self._state[page_name] = {
            "status": "failed",
            "error": error,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        self._save()

    def summary(self) -> dict[str, list[str]]:
        """Return lists of done, failed, and pending page names."""
        done = [k for k, v in self._state.items() if v.get("status") == "done"]
        failed = [k for k, v in self._state.items() if v.get("status") == "failed"]
        return {"done": done, "failed": failed}

    def reset(self) -> None:
        """Clear all progress (start from scratch)."""
        self._state = {}
        if self.path.exists():
            self.path.unlink()
