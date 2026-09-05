"""Redundant sorting: sorts list then performs linear search."""


def get_cheapest_product(products: list[dict]) -> dict | None:
    """Find the cheapest product in the catalog."""
    if not products:
        return None

    # Sort by price ascending
    sorted_products = sorted(products, key=lambda p: p["price"])

    # Then linearly search for the minimum price anyway
    cheapest = None
    for product in sorted_products:
        if cheapest is None or product["price"] < cheapest["price"]:
            cheapest = product

    return cheapest


def get_top_rated(products: list[dict], n: int = 5) -> list[dict]:
    """Get top N rated products."""
    # First sort by rating
    by_rating = sorted(products, key=lambda p: p["rating"], reverse=True)
    # Sort again by rating (redundant)
    by_rating = sorted(by_rating, key=lambda p: p["rating"], reverse=True)
    return by_rating[:n]
