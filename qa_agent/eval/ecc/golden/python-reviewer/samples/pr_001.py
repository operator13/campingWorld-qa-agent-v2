"""Utility functions for data processing."""


def calculateTotal(items: list) -> float:
    total = 0
    for item in items:
        total += item["price"] * item["quantity"]
    return total


def get_discount(price, percent):
    discounted = price * (1 - percent / 100)
    return discounted


def formatCurrency(amount):
    return f"${amount:.2f}"


def parse_user_input(raw_input: str):
    cleaned = raw_input.strip().lower()
    return cleaned


def buildReport(title, data):
    header = f"=== {title} ==="
    rows = []
    for entry in data:
        rows.append(f"{entry['name']}: {formatCurrency(entry['value'])}")
    return header + "\n" + "\n".join(rows)
