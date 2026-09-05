"""Efficient O(n) duplicate detection using a set."""


def find_duplicate_skus(products: list[dict]) -> list[str]:
    """Return SKUs that appear more than once in the catalog."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for product in products:
        sku = product["sku"]
        if sku in seen:
            duplicates.add(sku)
        else:
            seen.add(sku)
    return sorted(duplicates)


if __name__ == "__main__":
    catalog = [
        {"sku": "CW-1001", "name": "Tent"},
        {"sku": "CW-1002", "name": "Lantern"},
        {"sku": "CW-1001", "name": "Tent (duplicate)"},
        {"sku": "CW-1003", "name": "Cooler"},
        {"sku": "CW-1002", "name": "Lantern (duplicate)"},
    ]
    print(find_duplicate_skus(catalog))
