"""Order processing module."""

from dataclasses import dataclass


@dataclass
class Order:
    order_id: str
    customer_name: str
    items: list
    total: float


def validate_order(order):
    if not order.items:
        return False
    if order.total <= 0:
        return False
    return True


def apply_discount(order, code):
    discounts = {"SAVE10": 0.10, "SAVE20": 0.20, "VIP": 0.30}
    if code in discounts:
        new_total = order.total * (1 - discounts[code])
        return new_total
    return order.total


def format_receipt(order):
    lines = [f"Order: {order.order_id}", f"Customer: {order.customer_name}"]
    for item in order.items:
        lines.append(f"  - {item['name']}: ${item['price']:.2f}")
    lines.append(f"Total: ${order.total:.2f}")
    return "\n".join(lines)


def calculate_tax(subtotal, rate):
    return round(subtotal * rate, 2)
