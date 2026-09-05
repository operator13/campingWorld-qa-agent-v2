"""Authentication helpers using early-return guard clauses."""
import hashlib
import hmac
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

TOKEN_EXPIRY_SECONDS = 3600


def authenticate_request(
    headers: dict[str, str], secret: str, allowed_roles: list[str]
) -> Optional[dict[str, Any]]:
    """Validate a request's auth token and role. Returns user dict or None."""
    token = headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        logger.info("Missing authorization token")
        return None

    payload = decode_token(token, secret)
    if payload is None:
        logger.info("Invalid or expired token")
        return None

    if payload.get("role") not in allowed_roles:
        logger.info("Role %s not in allowed roles", payload.get("role"))
        return None

    return payload


def decode_token(token: str, secret: str) -> Optional[dict[str, Any]]:
    """Decode and verify a simple HMAC token. Returns payload or None."""
    parts = token.split(".")
    if len(parts) != 2:
        return None

    encoded_payload, signature = parts
    expected_sig = hmac.new(
        secret.encode(), encoded_payload.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_sig):
        return None

    try:
        import json, base64
        payload = json.loads(base64.b64decode(encoded_payload))
    except Exception:
        return None

    if payload.get("exp", 0) < time.time():
        return None

    return payload
