"""Well-structured FastAPI app with CORS, rate limiting, and dependency injection."""
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Camping World Store API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.campingworld.com"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


class Database:
    async def get_stores(self) -> list[dict]:
        return [{"id": 1, "name": "Austin Store", "state": "TX"}]


async def get_db() -> Database:
    return Database()


class StoreResponse(BaseModel):
    id: int
    name: str
    state: str


@app.get("/api/v1/stores", response_model=list[StoreResponse])
@limiter.limit("30/minute")
async def list_stores(request: Request, db: Database = Depends(get_db)):
    return await db.get_stores()
