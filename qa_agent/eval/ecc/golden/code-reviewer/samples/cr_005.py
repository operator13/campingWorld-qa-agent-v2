"""Product filters that mutate input lists in-place."""
from typing import Any


def filter_products(products: list[dict[str, Any]], min_price: float) -> list:
    """Remove products below min_price - mutates the original list."""
    i = 0
    while i < len(products):
        if products[i].get("price", 0) < min_price:
            products.pop(i)
        else:
            i += 1
    return products


def sort_and_tag_products(products: list[dict[str, Any]]) -> list:
    """Sort products by price and add a rank field - mutates each dict."""
    products.sort(key=lambda p: p.get("price", 0), reverse=True)
    for idx, product in enumerate(products):
        product["rank"] = idx + 1
        product["is_premium"] = product.get("price", 0) > 100
    return products


def deduplicate(items: list[str]) -> list[str]:
    """Remove duplicates from list - mutates original via slice assignment."""
    seen: set[str] = set()
    i = 0
    while i < len(items):
        if items[i] in seen:
            del items[i]
        else:
            seen.add(items[i])
            i += 1
    return items
