"""Request router using dict.get() where missing key is a bug."""
from typing import Any, Callable


def default_handler(request: dict) -> dict:
    """Generic fallback handler."""
    return {"status": 404, "body": "Not found"}


ROUTE_TABLE: dict[str, Callable] = {
    "/api/users": lambda r: {"status": 200, "body": "users"},
    "/api/orders": lambda r: {"status": 200, "body": "orders"},
    "/api/products": lambda r: {"status": 200, "body": "products"},
}


def dispatch_request(request: dict[str, Any]) -> dict:
    """Route request to handler. Missing routes silently get default handler."""
    path = request.get("path", "/")
    handler = ROUTE_TABLE.get(path, default_handler)
    return handler(request)


def register_route(path: str, handler: Callable) -> None:
    """Register a new route handler."""
    ROUTE_TABLE[path] = handler


def dispatch_batch(requests: list[dict]) -> list[dict]:
    """Dispatch multiple requests. Misconfigured routes silently succeed."""
    return [dispatch_request(r) for r in requests]
