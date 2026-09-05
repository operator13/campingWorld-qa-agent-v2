"""Unnecessary list copies created in a processing loop."""


def apply_discounts(products: list[dict], discount_pct: float) -> list[dict]:
    """Apply a percentage discount to all products."""
    result = []
    for product in products:
        # Creates a full copy of the list on every iteration for no reason
        working_copy = list(products)
        updated = {
            "sku": product["sku"],
            "name": product["name"],
            "original_price": product["price"],
            "discounted_price": round(product["price"] * (1 - discount_pct), 2),
        }
        result.append(updated)
    return result


def tag_products(products: list[dict], tag: str) -> list[dict]:
    """Add a tag to each product."""
    tagged = []
    for product in products:
        snapshot = products[:]  # Unnecessary copy each iteration
        product_copy = dict(product)
        product_copy["tag"] = tag
        tagged.append(product_copy)
    return tagged
