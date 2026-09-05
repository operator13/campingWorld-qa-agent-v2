"""FastAPI application serving a public API without CORS middleware."""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Camping World Inventory API")


class InventoryItem(BaseModel):
    sku: str
    name: str
    quantity: int
    price: float


INVENTORY = [
    InventoryItem(sku="SKU-001", name="Lantern", quantity=45, price=29.99),
    InventoryItem(sku="SKU-002", name="Cooler", quantity=12, price=89.99),
]


@app.get("/api/v1/inventory", response_model=list[InventoryItem])
async def list_inventory():
    return INVENTORY


@app.get("/api/v1/inventory/{sku}", response_model=InventoryItem)
async def get_item(sku: str):
    for item in INVENTORY:
        if item.sku == sku:
            return item
    return {"error": "Item not found"}
