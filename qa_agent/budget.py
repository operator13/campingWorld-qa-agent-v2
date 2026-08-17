"""Cost/load controls — concurrency caps and per-run token budget.

Tracks token usage across a run and enforces a budget ceiling to prevent
runaway costs from infinite healing loops or overly verbose LLM responses.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Default limits
DEFAULT_MAX_TOKENS_PER_RUN = 500_000   # ~$5 at typical Claude pricing
DEFAULT_MAX_CONCURRENT_NODES = 4       # max parallel LLM calls
DEFAULT_MAX_RETRIES_PER_NODE = 2       # LLM call retries within a single node


@dataclass
class TokenBudget:
    """Tracks token usage and enforces a per-run budget ceiling."""

    max_tokens: int = DEFAULT_MAX_TOKENS_PER_RUN
    input_tokens: int = field(default=0, init=False)
    output_tokens: int = field(default=0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def remaining(self) -> int:
        return max(0, self.max_tokens - self.total_tokens)

    @property
    def exhausted(self) -> bool:
        return self.total_tokens >= self.max_tokens

    def record(self, input_tokens: int, output_tokens: int) -> None:
        """Record token usage from a single LLM call."""
        with self._lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens

            if self.exhausted:
                logger.warning(
                    "Token budget EXHAUSTED: %d/%d tokens used",
                    self.total_tokens, self.max_tokens,
                )
            else:
                logger.debug(
                    "Token usage: +%d/%d (total: %d/%d, remaining: %d)",
                    input_tokens + output_tokens,
                    self.max_tokens,
                    self.total_tokens,
                    self.max_tokens,
                    self.remaining,
                )

    def check(self) -> None:
        """Raise if budget is exhausted."""
        if self.exhausted:
            raise BudgetExhaustedError(
                f"Token budget exhausted: {self.total_tokens}/{self.max_tokens} tokens used"
            )

    def summary(self) -> dict[str, int]:
        """Return a summary of token usage."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "max_tokens": self.max_tokens,
            "remaining": self.remaining,
        }


class BudgetExhaustedError(Exception):
    """Raised when the per-run token budget is exceeded."""


@dataclass
class ConcurrencyLimiter:
    """Limits concurrent LLM calls to prevent overload."""

    max_concurrent: int = DEFAULT_MAX_CONCURRENT_NODES
    _semaphore: threading.Semaphore = field(init=False)

    def __post_init__(self) -> None:
        self._semaphore = threading.Semaphore(self.max_concurrent)

    def acquire(self) -> bool:
        """Acquire a slot. Returns True if acquired, False if would block."""
        return self._semaphore.acquire(blocking=False)

    def release(self) -> None:
        """Release a slot."""
        self._semaphore.release()

    def __enter__(self) -> ConcurrencyLimiter:
        self._semaphore.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        self._semaphore.release()
