"""Product listing endpoint without response model."""
from fastapi import APIRouter

router = APIRouter()

PRODUCTS = [
    {"id": 1, "name": "Tent", "price": 199.99, "internal_cost": 85.00},
    {"id": 2, "name": "Sleeping Bag", "price": 79.99, "internal_cost": 32.00},
]


@router.get("/products")
async def list_products():
    return PRODUCTS


@router.get("/products/{product_id}")
async def get_product(product_id: int):
    for product in PRODUCTS:
        if product["id"] == product_id:
            return product
    return {"error": "Not found"}
