"""Find duplicate SKUs in product catalog using nested loops."""


def find_duplicate_skus(products: list[dict]) -> list[str]:
    """Return SKUs that appear more than once in the catalog."""
    duplicates = []
    for i in range(len(products)):
        for j in range(i + 1, len(products)):
            if products[i]["sku"] == products[j]["sku"]:
                if products[i]["sku"] not in duplicates:
                    duplicates.append(products[i]["sku"])
    return duplicates


if __name__ == "__main__":
    catalog = [
        {"sku": "CW-1001", "name": "Tent"},
        {"sku": "CW-1002", "name": "Lantern"},
        {"sku": "CW-1001", "name": "Tent (duplicate)"},
        {"sku": "CW-1003", "name": "Cooler"},
        {"sku": "CW-1002", "name": "Lantern (duplicate)"},
    ]
    print(find_duplicate_skus(catalog))
