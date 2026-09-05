"""FastAPI app with missing auth middleware on sensitive endpoints."""
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel

app = FastAPI()


class User(BaseModel):
    id: int
    name: str
    email: str
    role: str


def get_current_user(token: str) -> User:
    """Verify JWT and return user. Stub implementation."""
    if token == "valid":
        return User(id=1, name="Alice", email="alice@co.com", role="user")
    raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/api/users/me")
def get_me(user: User = Depends(get_current_user)):
    """Protected endpoint — requires authentication."""
    return user


@app.get("/api/admin/users")
def list_all_users():
    """List all users — MISSING auth dependency."""
    return [
        {"id": 1, "name": "Alice", "email": "alice@co.com", "role": "user"},
        {"id": 2, "name": "Bob", "email": "bob@co.com", "role": "admin"},
        {"id": 3, "name": "Charlie", "email": "charlie@co.com", "role": "user"},
    ]


@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: int):
    """Delete a user — MISSING auth dependency."""
    return {"status": "deleted", "user_id": user_id}
