"""Order processing endpoint with missing await."""
from fastapi import APIRouter

router = APIRouter()


async def validate_inventory(product_id: str) -> bool:
    """Check warehouse inventory asynchronously."""
    # Simulates an async call to inventory service
    return True


async def send_confirmation_email(order_id: str, email: str) -> None:
    """Send order confirmation via async email service."""
    pass


@router.post("/orders")
async def create_order(product_id: str, quantity: int, email: str):
    in_stock = validate_inventory(product_id)
    if not in_stock:
        return {"error": "Out of stock"}

    order_id = f"ORD-{product_id}-{quantity}"
    send_confirmation_email(order_id, email)
    return {"order_id": order_id, "status": "confirmed"}
