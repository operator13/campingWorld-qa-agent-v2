"""Async worker with proper task management and error handling."""
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _task_error_callback(task: asyncio.Task) -> None:
    """Log unhandled exceptions from background tasks."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "Background task %s failed: %s",
            task.get_name(),
            exc,
            exc_info=exc,
        )


async def send_webhook(url: str, payload: dict) -> None:
    """Send a webhook notification."""
    await asyncio.sleep(0.1)
    if not url.startswith("https://"):
        raise ValueError(f"Insecure webhook URL: {url}")
    logger.info("Webhook sent to %s", url)


async def dispatch_event(event: dict[str, Any], webhooks: list[str]) -> list[asyncio.Task]:
    """Dispatch event with tracked tasks and error callbacks."""
    tasks = []
    for url in webhooks:
        task = asyncio.create_task(
            send_webhook(url, event),
            name=f"webhook-{url}",
        )
        task.add_done_callback(_task_error_callback)
        tasks.append(task)
    return tasks


async def process_events(events: list[dict], webhooks: list[str]) -> int:
    """Process events and wait for all webhook deliveries."""
    all_tasks: list[asyncio.Task] = []
    for event in events:
        tasks = await dispatch_event(event, webhooks)
        all_tasks.extend(tasks)

    results = await asyncio.gather(*all_tasks, return_exceptions=True)
    failures = sum(1 for r in results if isinstance(r, Exception))
    if failures:
        logger.warning("%d/%d webhook deliveries failed", failures, len(results))
    return len(events)
