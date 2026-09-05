"""Payment processing with silently swallowed gateway errors."""
import json
import urllib.request
from decimal import Decimal


def charge_customer(
    customer_id: str, amount: Decimal, card_token: str, gateway_url: str
) -> dict:
    """Charge a customer's card. Silently ignores gateway failures."""
    payload = json.dumps({
        "customer_id": customer_id,
        "amount": str(amount),
        "card_token": card_token,
    }).encode()
    try:
        req = urllib.request.Request(
            f"{gateway_url}/charge",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        response = urllib.request.urlopen(req, timeout=10)
        result = json.loads(response.read().decode("utf-8"))
        return {"charged": True, "transaction_id": result["id"]}
    except Exception:
        pass

    return {"charged": False, "transaction_id": None}


def process_order(order: dict, gateway_url: str) -> dict:
    """Process an order by charging the customer."""
    result = charge_customer(
        order["customer_id"],
        Decimal(str(order["total"])),
        order["card_token"],
        gateway_url,
    )
    if not result["charged"]:
        return {"status": "pending", "order_id": order["id"]}
    return {"status": "completed", "order_id": order["id"]}
