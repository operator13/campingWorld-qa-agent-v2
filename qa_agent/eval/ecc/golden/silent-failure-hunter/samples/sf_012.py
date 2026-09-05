"""Event handler with unawaited coroutines."""
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def send_notification(user_id: str, message: str) -> None:
    """Send a notification to a user."""
    logger.info("Notification to %s: %s", user_id, message)


async def update_audit_log(action: str, user_id: str) -> None:
    """Record an action in the audit log."""
    logger.info("Audit: %s by %s", action, user_id)


async def handle_order_placed(event: dict[str, Any]) -> dict:
    """Handle an order-placed event. Forgets to await async calls."""
    user_id = event["user_id"]
    order_id = event["order_id"]

    send_notification(user_id, f"Order {order_id} confirmed")
    update_audit_log("order_placed", user_id)

    return {"processed": True, "order_id": order_id}
