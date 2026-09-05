"""Event dispatcher with fire-and-forget asyncio tasks."""
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def send_webhook(url: str, payload: dict) -> None:
    """Send a webhook notification - may raise on network error."""
    await asyncio.sleep(0.1)  # simulate network call
    if not url.startswith("https://"):
        raise ValueError(f"Insecure webhook URL: {url}")
    logger.info("Webhook sent to %s", url)


async def dispatch_event(event: dict[str, Any], webhooks: list[str]) -> None:
    """Dispatch event to all webhooks. Tasks are fire-and-forget."""
    for url in webhooks:
        asyncio.create_task(send_webhook(url, event))
    logger.info("Dispatched event %s to %d webhooks", event.get("type"), len(webhooks))


async def process_events(events: list[dict], webhooks: list[str]) -> int:
    """Process a batch of events."""
    for event in events:
        await dispatch_event(event, webhooks)
    return len(events)
