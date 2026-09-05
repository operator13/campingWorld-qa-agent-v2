"""FastAPI app with auth middleware properly applied to all endpoints."""
from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel

app = FastAPI()


class User(BaseModel):
    id: int
    name: str
    email: str
    role: str


def get_current_user(authorization: str = Header(...)) -> User:
    """Verify JWT token and return authenticated user."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    token = authorization.removeprefix("Bearer ")
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def verify_token(token: str) -> User | None:
    """Stub JWT verification."""
    return User(id=1, name="Alice", email="alice@co.com", role="admin")


@app.get("/api/users/me")
def get_me(user: User = Depends(get_current_user)):
    return user


@app.get("/api/admin/users")
def list_all_users(admin: User = Depends(require_admin)):
    return [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]


@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin)):
    return {"status": "deleted", "user_id": user_id}
