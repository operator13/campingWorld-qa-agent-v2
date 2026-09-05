"""Well-structured product catalog module."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price: float
    category: str
    tags: tuple[str, ...] = field(default_factory=tuple)


def find_by_category(
    products: list[Product], category: str
) -> list[Product]:
    """Return products matching the given category."""
    return [p for p in products if p.category == category]


def apply_bulk_discount(
    products: list[Product], discount_rate: float
) -> list[Product]:
    """Return new products with discounted prices."""
    return [
        Product(
            sku=p.sku,
            name=p.name,
            price=round(p.price * (1 - discount_rate), 2),
            category=p.category,
            tags=p.tags,
        )
        for p in products
    ]


def format_price_list(products: list[Product]) -> str:
    """Format products into a readable price list."""
    lines = [f"{p.name} ({p.sku}): ${p.price:.2f}" for p in products]
    return "\n".join(lines)
