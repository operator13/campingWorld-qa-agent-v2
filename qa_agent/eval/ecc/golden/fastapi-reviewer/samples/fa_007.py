"""Endpoint that manually instantiates a database connection instead of using Depends."""
from fastapi import APIRouter
from pydantic import BaseModel


class Database:
    def __init__(self) -> None:
        self.connection_string = "postgresql://localhost/campingworld"

    def get_reviews(self, product_id: int) -> list[dict]:
        return [{"id": 1, "rating": 5, "text": "Great product!"}]


class ReviewResponse(BaseModel):
    id: int
    rating: int
    text: str


router = APIRouter()


@router.get("/products/{product_id}/reviews", response_model=list[ReviewResponse])
async def get_product_reviews(product_id: int):
    db = Database()
    reviews = db.get_reviews(product_id)
    return reviews
