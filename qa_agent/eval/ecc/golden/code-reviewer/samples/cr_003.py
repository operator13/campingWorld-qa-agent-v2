"""Order processor with 5-level deep nesting."""
from typing import Any


def process_orders(orders: list[dict[str, Any]], config: dict) -> list[dict]:
    """Process a batch of orders with deeply nested control flow."""
    results = []
    for order in orders:
        if order.get("status") == "pending":
            for item in order.get("items", []):
                if item.get("quantity", 0) > 0:
                    try:
                        if item.get("sku") in config.get("available_skus", []):
                            price = item["price"] * item["quantity"]
                            if config.get("tax_enabled"):
                                tax_rate = config.get("tax_rates", {}).get(
                                    order.get("state", ""), 0.0
                                )
                                price += price * tax_rate
                            results.append({
                                "order_id": order["id"],
                                "sku": item["sku"],
                                "total": round(price, 2),
                                "status": "processed",
                            })
                        else:
                            results.append({
                                "order_id": order["id"],
                                "sku": item.get("sku"),
                                "status": "unavailable",
                            })
                    except KeyError:
                        results.append({
                            "order_id": order.get("id"),
                            "sku": item.get("sku"),
                            "status": "error",
                        })
    return results
