"""Login endpoint without rate limiting."""
from hashlib import sha256

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

USERS_DB = {
    "admin": sha256(b"supersecret").hexdigest(),
    "user1": sha256(b"password123").hexdigest(),
}


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(payload: LoginRequest):
    stored_hash = USERS_DB.get(payload.username)
    if stored_hash is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    incoming_hash = sha256(payload.password.encode()).hexdigest()
    if incoming_hash != stored_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {"token": f"tok_{payload.username}_abc123", "expires_in": 3600}
