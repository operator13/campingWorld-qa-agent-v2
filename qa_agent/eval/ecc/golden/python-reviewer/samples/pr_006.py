"""Inventory management with generic types."""

from typing import Optional


def get_product_names(products: list) -> list:
    return [p["name"] for p in products]


def merge_inventories(inv_a: dict, inv_b: dict) -> dict:
    merged = dict(inv_a)
    for key, val in inv_b.items():
        merged[key] = merged.get(key, 0) + val
    return merged


def find_low_stock(inventory: dict, threshold: int = 5) -> list:
    return [item for item, qty in inventory.items() if qty < threshold]


def categorize_items(items: list) -> dict:
    categories: dict = {}
    for item in items:
        cat = item.get("category", "uncategorized")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item["name"])
    return categories


def get_price_range(prices: list) -> tuple:
    if not prices:
        return (0.0, 0.0)
    return (min(prices), max(prices))
