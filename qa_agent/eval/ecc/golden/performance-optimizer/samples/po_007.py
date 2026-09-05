"""Subtle N+1 via ORM lazy-loading pattern."""
from dataclasses import dataclass, field


@dataclass
class ProductModel:
    id: int
    name: str
    category_id: int


@dataclass
class CategoryModel:
    id: int
    name: str


class FakeORM:
    """Simulates an ORM with lazy-loaded relationships."""

    def __init__(self) -> None:
        self._query_count = 0

    def all_products(self) -> list[ProductModel]:
        self._query_count += 1
        return [ProductModel(i, f"Product {i}", i % 5) for i in range(100)]

    def get_category(self, category_id: int) -> CategoryModel:
        """Each call simulates a separate DB round-trip."""
        self._query_count += 1
        return CategoryModel(category_id, f"Category {category_id}")


def build_product_report(orm: FakeORM) -> list[dict]:
    """Build a report joining products with their category names."""
    products = orm.all_products()  # 1 query
    report = []
    for product in products:
        # Lazy load triggers a query per product
        category = orm.get_category(product.category_id)
        report.append({
            "product": product.name,
            "category": category.name,
        })
    return report  # Total: 1 + N queries
